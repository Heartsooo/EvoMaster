from __future__ import annotations

import mimetypes
import json
import os
import shutil
import base64
import binascii
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
CONFIG = PROJECT_ROOT / 'configs' / 'materials_playground' / 'config.yaml'
AGENT = 'materials_playground'
SESSIONS_DIR = ROOT / '.sessions'
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SESSIONS_DIR.mkdir(exist_ok=True)

sessions: dict[str, dict] = {}
jobs: dict[str, dict] = {}
session_versions: dict[str, int] = {}
token_usage_cache: dict[str, dict] = {}
AVAILABLE_MODELS = [
    {'key': 'openai', 'label': 'Kimi K2.5', 'model': 'Vendor2/Kimi-k2.5'},
    {'key': 'claude_opus', 'label': 'Claude 4.6 Opus', 'model': 'Vendor2/Claude-4.6-opus'},
    {'key': 'gpugeek_gpt54', 'label': 'GPT-5.4', 'model': 'Vendor2/GPT-5.4'},
    {'key': 'litellm_cds_claude46_opus', 'label': 'LiteLLM · cds Claude 4.6 Opus', 'model': 'cds/Claude-4.6-opus'},
    {'key': 'litellm_ez_claude_opus', 'label': 'LiteLLM · ez Claude Opus 4.6', 'model': 'ez/claude-opus-4-6'},
    {'key': 'litellm_cds_gpt54', 'label': 'LiteLLM · GPT-5.4', 'model': 'cds/GPT-5.4'},
]


def _default_runtime() -> dict:
    return {
        'phase': 'idle',
        'retry': None,
        'last_error': '',
        'started_at': '',
        'updated_at': '',
    }


def _ensure_runtime(session: dict) -> dict:
    runtime = session.get('runtime') or {}
    merged = _default_runtime()
    merged.update(runtime)
    if not merged.get('phase'):
        merged['phase'] = 'idle'
    session['runtime'] = merged
    return merged


def _touch_session(session_id: str) -> None:
    session_versions[session_id] = session_versions.get(session_id, 0) + 1


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f'{session_id}.json'


def _is_job_running(session: dict) -> bool:
    job_id = str(session.get('last_job_id') or '').strip()
    if not job_id:
        return False
    job = jobs.get(job_id)
    if not isinstance(job, dict):
        return False
    return str(job.get('status') or '') == 'running'


def _heal_stale_running_session(session_id: str, session: dict) -> bool:
    """Normalize stale `running` sessions after force-exit/restart."""
    if str(session.get('status') or '') != 'running':
        return False
    if _is_job_running(session):
        return False

    now = datetime.now().isoformat(timespec='seconds')
    runtime = _ensure_runtime(session)
    session['status'] = 'failed'
    runtime['phase'] = 'failed'
    if not runtime.get('last_error'):
        runtime['last_error'] = 'session interrupted or worker exited unexpectedly'
    runtime['updated_at'] = now
    _save_session(session_id)
    return True


def _save_session(session_id: str) -> None:
    session = sessions[session_id].copy()
    _session_file(session_id).write_text(json.dumps(session, ensure_ascii=False, indent=2))
    _touch_session(session_id)


def _load_sessions() -> None:
    for path in SESSIONS_DIR.glob('*.json'):
        try:
            data = json.loads(path.read_text())
            session_id = data.get('id')
            if not session_id:
                continue
            # Avoid overwriting in-memory session state while workers are running.
            # Handler.__init__ calls _load_sessions() per request, so clobbering here
            # can drop freshly appended history messages used for next-turn context.
            if session_id in sessions:
                continue
            sessions[session_id] = data
        except Exception:
            continue


def _resolve_workspace_path(session_id: str, relative_path: str = '') -> Path:
    session = sessions[session_id]
    root = Path(session['workspace']).resolve()
    target = (root / relative_path).resolve()
    if root not in [target, *target.parents]:
        raise ValueError('path escapes workspace')
    return target


def _list_tree(base: Path) -> list[dict]:
    items = []
    if not base.exists():
        return items
    for child in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        items.append({
            'name': child.name,
            'path': str(child.relative_to(base)),
            'is_dir': child.is_dir(),
            'size': child.stat().st_size if child.is_file() else None,
        })
    return items




def _clip(text: str, limit: int = 600) -> str:
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '\\n…'


def _normalize_message_payload(raw):
    """Normalize incoming message payload to str or multimodal block list."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        blocks = []
        seen_image_urls: set[str] = set()

        def _is_image_placeholder_text(value: str) -> bool:
            normalized = ' '.join(str(value or '').strip().lower().split())
            return normalized in {
                '[image]',
                '[img]',
                '[图片]',
                'image',
                'img',
                '图片',
            }

        for item in raw:
            if not isinstance(item, dict):
                continue
            block_type = item.get('type')
            if block_type == 'text':
                text = str(item.get('text') or '').strip()
                if text and not _is_image_placeholder_text(text):
                    blocks.append({'type': 'text', 'text': text})
            elif block_type == 'image_url':
                image_url = item.get('image_url')
                if isinstance(image_url, dict) and isinstance(image_url.get('url'), str) and image_url.get('url').strip():
                    url = image_url.get('url').strip()
                    if url in seen_image_urls:
                        continue
                    seen_image_urls.add(url)
                    blocks.append({'type': 'image_url', 'image_url': {'url': url}})
        return blocks
    return str(raw).strip()


def _message_has_content(content) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return len(content) > 0
    return False


def _message_to_event_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_blocks = [str(x.get('text') or '').strip() for x in content if isinstance(x, dict) and x.get('type') == 'text']
        text_blocks = [x for x in text_blocks if x]
        image_count = sum(1 for x in content if isinstance(x, dict) and x.get('type') == 'image_url')
        text_part = text_blocks[0] if text_blocks else ''
        if image_count:
            if text_part:
                return f"{text_part}\n[附加图片 {image_count} 张]"
            return f"[附加图片 {image_count} 张]"
        return text_part
    return str(content or '').strip()



def _collect_artifacts(session_id: str) -> dict:
    root = Path(sessions[session_id]['workspace'])
    recent = []
    if root.exists():
        files = []
        for path in root.rglob('*'):
            if path.is_file():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files.append((stat.st_mtime, path, stat.st_size))
        files.sort(reverse=True, key=lambda x: x[0])
        for mtime, path, size in files[:12]:
            try:
                rel = str(path.relative_to(root))
            except Exception:
                rel = path.name
            recent.append({'path': rel, 'size': size})
    return {
        'workspace_root': str(root),
        'recent_files': recent,
    }


def _collect_api_usage_stats(session_id: str, session: dict) -> dict:
    """Collect real token usage from trajectory (deduplicated by response_id)."""
    default = {
        'current_prompt_tokens': 0,
        'current_total_tokens': 0,
        'peak_prompt_tokens': 0,
        'cumulative_prompt_tokens': 0,
        'cumulative_completion_tokens': 0,
        'cumulative_total_tokens': 0,
        'response_count': 0,
    }
    run_dir = str(session.get('run_dir') or '').strip()
    if not run_dir:
        return default
    trajectory_file = Path(run_dir) / 'trajectories' / 'task_0' / 'trajectory.json'
    if not trajectory_file.exists():
        return default
    try:
        stat = trajectory_file.stat()
    except OSError:
        return default
    signature = f'{stat.st_mtime_ns}:{stat.st_size}'
    cached = token_usage_cache.get(session_id)
    if cached and cached.get('signature') == signature:
        return dict(cached.get('stats') or default)

    try:
        payload = json.loads(trajectory_file.read_text(encoding='utf-8'))
    except Exception:
        return default

    seen_keys: set[str] = set()
    ordered_usage: list[tuple[int, int, int]] = []
    fallback_index = 0

    def _walk(item) -> None:
        nonlocal fallback_index
        if isinstance(item, dict):
            meta = item.get('meta')
            if isinstance(meta, dict):
                usage = meta.get('usage')
                if isinstance(usage, dict):
                    prompt = int(usage.get('prompt_tokens') or 0)
                    completion = int(usage.get('completion_tokens') or 0)
                    total = int(usage.get('total_tokens') or (prompt + completion))
                    if prompt > 0 or completion > 0 or total > 0:
                        response_id = str(meta.get('response_id') or '').strip()
                        if response_id:
                            key = response_id
                        else:
                            fallback_index += 1
                            key = f'fallback:{prompt}:{completion}:{total}:{fallback_index}'
                        if key not in seen_keys:
                            seen_keys.add(key)
                            ordered_usage.append((prompt, completion, total))
            for value in item.values():
                _walk(value)
        elif isinstance(item, list):
            for value in item:
                _walk(value)

    _walk(payload)

    if not ordered_usage:
        return default

    cumulative_prompt = sum(x[0] for x in ordered_usage)
    cumulative_completion = sum(x[1] for x in ordered_usage)
    cumulative_total = sum(x[2] for x in ordered_usage)
    peak_prompt = max(x[0] for x in ordered_usage)
    current_prompt, current_completion, current_total = ordered_usage[-1]

    stats = {
        'current_prompt_tokens': current_prompt,
        'current_total_tokens': current_total or (current_prompt + current_completion),
        'peak_prompt_tokens': peak_prompt,
        'cumulative_prompt_tokens': cumulative_prompt,
        'cumulative_completion_tokens': cumulative_completion,
        'cumulative_total_tokens': cumulative_total or (cumulative_prompt + cumulative_completion),
        'response_count': len(ordered_usage),
    }
    token_usage_cache[session_id] = {'signature': signature, 'stats': stats}
    return stats


def _build_flow_events(events: list[dict]) -> list[dict]:
    flow: list[dict] = []
    tool_names: dict[str, str] = {}

    for ev in events or []:
        et = ev.get('type')
        if et == 'assistant':
            content = (ev.get('content') or '').strip()
            if content:
                flow.append({
                    'type': 'thought',
                    'label': 'Thinking' if ev.get('is_reasoning') else 'Assistant',
                    'is_reasoning': bool(ev.get('is_reasoning')),
                    'step_id': ev.get('step_id'),
                    'content': _clip(content, 1200),
                    'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
                })
        elif et == 'tool_call':
            call_id = ev.get('call_id') or f"tool-{len(flow)+1}"
            tool_name = ev.get('label') or ev.get('tool_name') or 'tool'
            tool_names[call_id] = tool_name
            flow.append({
                'type': 'tool_call',
                'step_id': ev.get('step_id'),
                'call_id': call_id,
                'tool_name': tool_name,
                'content': _clip(ev.get('content', ''), 1000),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et == 'tool_progress':
            call_id = ev.get('call_id') or f"tool-{len(flow)+1}"
            flow.append({
                'type': 'tool_progress',
                'step_id': ev.get('step_id'),
                'call_id': call_id,
                'tool_name': tool_names.get(call_id, ev.get('label') or ev.get('tool_name') or 'tool'),
                'content': _clip(ev.get('content', ''), 1000),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et == 'tool_result':
            call_id = ev.get('call_id') or f"tool-{len(flow)+1}"
            flow.append({
                'type': 'tool_result',
                'step_id': ev.get('step_id'),
                'call_id': call_id,
                'tool_name': tool_names.get(call_id, ev.get('label') or ev.get('tool_name') or 'tool'),
                'status': ev.get('status', 'success'),
                'content': _clip(ev.get('content', ''), 1400),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et in {'retry', 'llm_retry'}:
            retry_index = ev.get('attempt') or ev.get('retry_index') or 0
            wait_seconds = ev.get('wait_seconds') or 0
            flow.append({
                'type': 'retry',
                'step_id': ev.get('step_id'),
                'label': ev.get('label') or 'LLM retry',
                'retry_index': retry_index,
                'wait_seconds': wait_seconds,
                'content': _clip(ev.get('content', ''), 800),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et == 'llm_request_started':
            flow.append({
                'type': 'llm_request_started',
                'label': 'LLM started',
                'content': _clip(f"model={ev.get('model')} timeout={ev.get('timeout')}s max_attempts={ev.get('max_attempts')}", 800),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et == 'llm_request_succeeded':
            flow.append({
                'type': 'llm_request_succeeded',
                'label': 'LLM succeeded',
                'content': _clip(f"model={ev.get('model')} attempt={ev.get('attempt')}", 800),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et == 'llm_request_failed':
            flow.append({
                'type': 'llm_request_failed',
                'label': 'LLM failed',
                'content': _clip(ev.get('content') or ev.get('error', ''), 800),
                'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
            })
        elif et in {'system', 'error'}:
            content = (ev.get('content') or '').strip()
            if content and not content.startswith('Agent step'):
                flow.append({
                    'type': 'system' if et == 'system' else 'error',
                    'step_id': ev.get('step_id'),
                    'label': ev.get('label', et),
                    'content': _clip(content, 800),
                    'timestamp': ev.get('timestamp') or ev.get('created_at') or '',
                })

    return flow


def _build_finish_summary(session: dict, trajectory: list[dict], last_job: dict) -> dict | None:
    status = session.get('status', 'idle')
    if status not in {'completed', 'failed', 'cancelled'}:
        return None
    tool_count = 0
    step_count = len(trajectory or [])
    last_assistant = ''
    for step in trajectory or []:
        tool_count += len(step.get('tool_groups', []) or [])
        if step.get('assistant_summary'):
            last_assistant = step.get('assistant_summary') or last_assistant
    if not last_assistant:
        for msg in reversed(session.get('messages', [])):
            if msg.get('role') == 'assistant' and (msg.get('content') or '').strip():
                last_assistant = msg.get('content', '').strip()
                break
    return {
        'type': 'finish',
        'status': status,
        'summary': _clip(last_assistant, 1000),
        'step_count': step_count,
        'tool_count': tool_count,
        'job_id': session.get('last_job_id'),
        'log_size': len(''.join((last_job or {}).get('logs', []))),
    }


def _recover_messages_from_events(session: dict) -> bool:
    """Rebuild/repair user+assistant history from events when persisted messages are stale."""
    events = session.get('events') or []
    recovered: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        et = ev.get('type')
        content = str(ev.get('content') or '').strip()
        if not content:
            continue
        ts = ev.get('timestamp') or ev.get('created_at') or datetime.now().isoformat(timespec='seconds')
        if et == 'user':
            recovered.append({
                'role': 'user',
                'content': content,
                'created_at': ts,
            })
        elif et == 'assistant':
            recovered.append({
                'role': 'assistant',
                'content': content,
                'created_at': ts,
                'kind': 'reasoning' if ev.get('is_reasoning') else 'assistant_step',
            })
        elif et in {'tool_call', 'tool_progress', 'tool_result'}:
            tool_name = ev.get('tool_name') or ev.get('label') or 'tool'
            recovered.append({
                'role': 'assistant',
                'content': f'[{et}:{tool_name}]\n{content}',
                'created_at': ts,
                'kind': et,
                'tool_name': tool_name,
                'call_id': ev.get('call_id'),
            })
    if not recovered:
        return False
    existing = session.get('messages') or []
    if not existing:
        session['messages'] = recovered
        return True

    def _msg_sig(msg: dict[str, Any]) -> tuple[str, str]:
        role = str(msg.get('role') or '')
        content = msg.get('content')
        if isinstance(content, str):
            norm = content.strip()
        elif isinstance(content, list):
            norm = json.dumps(content, ensure_ascii=False, sort_keys=True)
        else:
            norm = str(content or '').strip()
        return role, norm

    prefix_len = min(len(existing), len(recovered))
    prefix_match = all(_msg_sig(existing[i]) == _msg_sig(recovered[i]) for i in range(prefix_len))
    if prefix_match and len(recovered) > len(existing):
        session['messages'] = [*existing, *recovered[len(existing):]]
        return True

    existing_has_assistant = any(
        isinstance(msg, dict) and msg.get('role') == 'assistant' and str(msg.get('content') or '').strip()
        for msg in existing
    )
    recovered_has_assistant = any(
        isinstance(msg, dict) and msg.get('role') == 'assistant' and str(msg.get('content') or '').strip()
        for msg in recovered
    )
    existing_tool_kinds = sum(
        1
        for msg in existing
        if isinstance(msg, dict) and msg.get('kind') in {'tool_call', 'tool_progress', 'tool_result'}
    )
    recovered_tool_kinds = sum(
        1
        for msg in recovered
        if isinstance(msg, dict) and msg.get('kind') in {'tool_call', 'tool_progress', 'tool_result'}
    )

    # Legacy sessions may keep only assistant summaries in messages while full tool traces
    # are present in events. If recovered history is much richer, prefer recovered.
    if recovered_tool_kinds > max(3, existing_tool_kinds * 2):
        session['messages'] = recovered
        return True

    # Fallback for interrupted sessions: if existing history has no assistant but events do,
    # trust the event-derived timeline so next turn can recover context.
    if recovered_has_assistant and not existing_has_assistant:
        session['messages'] = recovered
        return True
    return False


def _append_history_memory(session: dict, *, pending, result: dict[str, Any]) -> None:
    history = session.setdefault('messages', [])
    now = datetime.now().isoformat(timespec='seconds')

    if _message_has_content(pending):
        history.append({
            'role': 'user',
            'content': pending,
            'created_at': now,
        })

    for event in result.get('events', []) or []:
        if not isinstance(event, dict):
            continue
        et = event.get('type')
        content = str(event.get('content') or '').strip()
        if not content:
            continue
        if et == 'assistant':
            history.append({
                'role': 'assistant',
                'content': content,
                'created_at': event.get('timestamp') or event.get('created_at') or now,
                'kind': 'reasoning' if event.get('is_reasoning') else 'assistant_step',
            })
        elif et in {'tool_call', 'tool_progress', 'tool_result'}:
            tool_name = event.get('tool_name') or event.get('label') or 'tool'
            history.append({
                'role': 'assistant',
                'content': f'[{et}:{tool_name}]\n{content}',
                'created_at': event.get('timestamp') or event.get('created_at') or now,
                'kind': et,
                'tool_name': tool_name,
                'call_id': event.get('call_id'),
            })

    assistant_text = (result.get('assistant_text') or '').strip()
    if assistant_text:
        history.append({
            'role': 'assistant',
            'content': assistant_text,
            'created_at': now,
            'kind': 'assistant_final',
        })


def _merge_saved_trajectory_events(session_id: str, session: dict) -> None:
    try:
        from playground.materials_playground.web.session_runner import _load_events_from_saved_trajectory
    except Exception:
        return

    fallback_events = _load_events_from_saved_trajectory(session['run_dir'])
    if not fallback_events:
        return

    events = session.setdefault('events', [])
    event_keys = {
        (
            ev.get('type'),
            ev.get('label'),
            ev.get('content'),
            ev.get('step_id'),
            ev.get('call_id'),
            ev.get('timestamp') or ev.get('created_at') or '',
        )
        for ev in events
        if isinstance(ev, dict)
    }

    added = 0
    for ev in fallback_events:
        if not isinstance(ev, dict):
            continue
        key = (
            ev.get('type'),
            ev.get('label'),
            ev.get('content'),
            ev.get('step_id'),
            ev.get('call_id'),
            ev.get('timestamp') or ev.get('created_at') or '',
        )
        if key in event_keys:
            continue
        events.append(ev)
        event_keys.add(key)
        added += 1

    if added:
        _save_session(session_id)


def _build_trajectory(events: list[dict]) -> list[dict]:
    steps: dict[int, dict] = {}
    ordered: list[dict] = []

    def _ensure(step_id: int) -> dict:
        if step_id not in steps:
            steps[step_id] = {
                'step_id': step_id,
                'assistant_summary': '',
                'tool_groups': [],
                'system_events': [],
                'tool_count': 0,
                'thought_count': 0,
                'timestamp': '',
            }
            ordered.append(steps[step_id])
        return steps[step_id]

    def _ensure_group(step: dict, call_id: str | None, tool_name: str | None = None) -> dict:
        if not call_id:
            call_id = f'ungrouped-{len(step["tool_groups"]) + 1}'
        for group in step['tool_groups']:
            if group['call_id'] == call_id:
                if tool_name and not group.get('tool_name'):
                    group['tool_name'] = tool_name
                return group
        group = {
            'call_id': call_id,
            'tool_name': tool_name or 'tool',
            'tool_label': '',
            'tool_input': '',
            'progress': [],
            'result': '',
            'result_label': '',
            'status': 'pending',
            'started_at': '',
            'finished_at': '',
        }
        step['tool_groups'].append(group)
        return group

    for ev in events or []:
        step_id = ev.get('step_id')
        if step_id is None:
            continue
        step = _ensure(int(step_id))
        event_time = ev.get('timestamp') or ev.get('created_at') or ''
        if event_time and not step['timestamp']:
            step['timestamp'] = event_time
        et = ev.get('type')
        if et == 'assistant':
            content = (ev.get('content') or '').strip()
            if content:
                step['assistant_summary'] = content
                step['thought_count'] += 1
        elif et == 'tool_call':
            group = _ensure_group(step, ev.get('call_id'), ev.get('label'))
            group['tool_name'] = ev.get('label') or group['tool_name']
            group['tool_label'] = ev.get('label') or group['tool_label']
            group['tool_input'] = _clip(ev.get('content', ''), 800)
            group['started_at'] = event_time or group['started_at']
            group['status'] = 'running'
        elif et == 'tool_progress':
            group = _ensure_group(step, ev.get('call_id'))
            progress = _clip(ev.get('content', ''), 400)
            if progress:
                group['progress'].append(progress)
            group['status'] = 'running'
        elif et == 'tool_result':
            group = _ensure_group(step, ev.get('call_id'), ev.get('label'))
            group['result'] = _clip(ev.get('content', ''), 1200)
            group['result_label'] = ev.get('label', '')
            group['finished_at'] = event_time or group['finished_at']
            lower = (group['result'] or '').lower()
            if 'error' in lower or 'failed' in lower or 'traceback' in lower:
                group['status'] = 'failed'
            else:
                group['status'] = 'completed'
        elif et in {'system', 'error'}:
            step['system_events'].append({
                'type': et,
                'label': ev.get('label', et),
                'content': _clip(ev.get('content', ''), 500),
                'timestamp': event_time,
            })

    for step in ordered:
        step['tool_count'] = len(step['tool_groups'])
    return ordered

def _run_session_worker(job_id: str, session_id: str):
    from contextlib import redirect_stderr, redirect_stdout
    from playground.materials_playground.web.session_runner import run_session_messages

    class _LogSink:
        def write(self, data):
            if data:
                jobs[job_id]['logs'].append(str(data))
        def flush(self):
            pass

    try:
        session = sessions[session_id]
        runtime = _ensure_runtime(session)
        now = datetime.now().isoformat(timespec='seconds')
        runtime.update({
            'phase': 'requesting_llm',
            'retry': None,
            'last_error': '',
            'started_at': now,
            'updated_at': now,
        })
        session['status'] = 'running'
        session.setdefault('events', []).append({
            'type': 'system',
            'label': 'session_started',
            'content': 'Agent run started',
            'created_at': now,
        })
        _save_session(session_id)
        pending = session.get('pending_user_message', '')
        session['cancel_requested'] = False

        def _retry_callback(info):
            session = sessions[session_id]
            if session.get('cancel_requested'):
                raise RuntimeError('session_cancelled')
            runtime = _ensure_runtime(session)
            runtime['phase'] = 'retrying_llm'
            runtime['retry'] = info
            runtime['last_error'] = info.get('error', '')
            runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
            session.setdefault('events', []).append({
                'type': 'retry',
                'label': 'LLM retry',
                'attempt': info.get('attempt'),
                'wait_seconds': info.get('wait_seconds'),
                'content': info.get('error', ''),
                'created_at': datetime.now().isoformat(timespec='seconds'),
            })
            _save_session(session_id)

        def _llm_event_callback(info):
            session = sessions[session_id]
            if session.get('cancel_requested'):
                raise RuntimeError('session_cancelled')
            runtime = _ensure_runtime(session)
            event_type = info.get('type')
            if event_type == 'llm_request_started':
                runtime['phase'] = 'requesting_llm'
            elif event_type == 'llm_retry':
                runtime['phase'] = 'retrying_llm'
                runtime['retry'] = info
                runtime['last_error'] = info.get('error', '')
            elif event_type == 'llm_request_failed':
                runtime['phase'] = 'failed'
                runtime['last_error'] = info.get('error', '')
            elif event_type == 'llm_request_succeeded':
                runtime['phase'] = 'llm_responded'
                runtime['retry'] = None
            runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
            payload = dict(info)
            payload['created_at'] = datetime.now().isoformat(timespec='seconds')
            if 'error' in payload and 'content' not in payload:
                payload['content'] = payload['error']
            session.setdefault('events', []).append(payload)
            _save_session(session_id)

        sink = _LogSink()
        with redirect_stdout(sink), redirect_stderr(sink):
            result = run_session_messages(
                config_path=CONFIG,
                run_dir=session['run_dir'],
                session_id=session_id,
                history_messages=session['messages'],
                new_user_message=pending,
                retry_callback=_retry_callback if '_retry_callback' in locals() else None,
                llm_event_callback=_llm_event_callback,
                llm_name=session.get('selected_model', 'openai'),
                should_cancel=lambda: bool(sessions.get(session_id, {}).get('cancel_requested')),
            )
        jobs[job_id]['result'] = result
        jobs[job_id]['status'] = result.get('status', 'completed')
        # Re-fetch live session to avoid stale references after _load_sessions() refresh.
        live_session = sessions.get(session_id, session)
        _append_history_memory(live_session, pending=pending, result=result)
        live_session['pending_user_message'] = ''
        live_session.setdefault('events', []).extend(result.get('events', []))
        runtime = _ensure_runtime(live_session)
        runtime['phase'] = 'completed' if jobs[job_id]['status'] == 'completed' else jobs[job_id]['status']
        runtime['retry'] = None
        runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
    except Exception as exc:
        session = sessions[session_id]
        cancelled = bool(session.get('cancel_requested')) or str(exc) == 'session_cancelled'
        jobs[job_id]['status'] = 'cancelled' if cancelled else 'failed'
        if cancelled:
            jobs[job_id]['logs'].append("\n[session_runner] session cancelled by user\n")
            runtime = _ensure_runtime(session)
            runtime['phase'] = 'cancelled'
            runtime['last_error'] = ''
            runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
            session.setdefault('events', []).append({
                'type': 'system',
                'label': 'session_cancelled',
                'content': 'Session cancelled by user',
                'created_at': datetime.now().isoformat(timespec='seconds'),
            })
        else:
            jobs[job_id]['logs'].append(f"\n[session_runner_error] {type(exc).__name__}: {exc}\n")
            runtime = _ensure_runtime(session)
            runtime['phase'] = 'failed'
            runtime['last_error'] = str(exc)
            runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
            session.setdefault('events', []).append({
                'type': 'error',
                'label': type(exc).__name__,
                'content': str(exc),
                'created_at': datetime.now().isoformat(timespec='seconds'),
            })
    finally:
        sessions[session_id]['last_job_id'] = job_id
        sessions[session_id]['status'] = jobs[job_id].get('status', 'failed')
        runtime = _ensure_runtime(sessions[session_id])
        if sessions[session_id]['status'] == 'running':
            runtime['phase'] = 'requesting_llm'
        elif sessions[session_id]['status'] == 'completed':
            runtime['phase'] = 'completed'
        elif sessions[session_id]['status'] == 'cancelling':
            runtime['phase'] = 'cancelling'
        elif sessions[session_id]['status'] == 'cancelled':
            runtime['phase'] = 'cancelled'
        elif sessions[session_id]['status'] == 'failed':
            runtime['phase'] = 'failed'
        sessions[session_id]['cancel_requested'] = False
        runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
        _save_session(session_id)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        _load_sessions()
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/sessions':
            items = []
            for session_id, session in sessions.items():
                _heal_stale_running_session(session_id, session)
                items.append({
                    'id': session_id,
                    'title': session['title'],
                    'status': session.get('status', 'idle'),
                    'created_at': session['created_at'],
                    'workspace': session['workspace'],
                    'message_count': len(session['messages']),
                })
            return self._json({'sessions': list(reversed(items))})

        if parsed.path == '/api/session/stream':
            session_id = parse_qs(parsed.query).get('id', [''])[0]
            if not session_id or session_id not in sessions:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            last_version = -1
            try:
                while True:
                    version = session_versions.get(session_id, 0)
                    if version != last_version:
                        payload = {'session_id': session_id, 'version': version, 'status': sessions.get(session_id, {}).get('status', 'idle')}
                        self.wfile.write(f"event: session\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                        last_version = version
                    else:
                        self.wfile.write(b': keep-alive\n\n')
                        self.wfile.flush()
                    time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                return

        if parsed.path == '/api/session':
            session_id = parse_qs(parsed.query).get('id', [''])[0]
            session = sessions.get(session_id)
            if not session:
                return self._json({'error': 'session_not_found'}, 404)
            _heal_stale_running_session(session_id, session)
            if _recover_messages_from_events(session):
                _save_session(session_id)
            runtime = _ensure_runtime(session)
            usage_stats = _collect_api_usage_stats(session_id, session)
            runtime['context_prompt_tokens'] = usage_stats.get('current_prompt_tokens', 0)
            runtime['api_cumulative_tokens'] = usage_stats.get('cumulative_total_tokens', 0)
            last_job = jobs.get(session.get('last_job_id', ''), {})
            _merge_saved_trajectory_events(session_id, session)
            events = session.get('events', [])
            trajectory = _build_trajectory(events)
            finish = _build_finish_summary(session, trajectory, last_job)
            return self._json({
                'id': session_id,
                'title': session['title'],
                'status': session.get('status', 'idle'),
                'created_at': session['created_at'],
                'workspace': session['workspace'],
                'run_dir': session['run_dir'],
                'messages': session['messages'],
                'selected_model': session.get('selected_model', 'openai'),
                'available_models': AVAILABLE_MODELS,
                'runtime': runtime,
                'api_usage': usage_stats,
                'artifacts': _collect_artifacts(session_id),
                'events': events,
                'trajectory': trajectory,
                'flow': _build_flow_events(events),
                'finish': finish,
                'logs': ''.join(last_job.get('logs', []))[-120000:],
                'last_job_id': session.get('last_job_id'),
            })
        if parsed.path == '/api/workspace/list':
            session_id = parse_qs(parsed.query).get('session_id', [''])[0]
            rel = parse_qs(parsed.query).get('path', [''])[0]
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            target = _resolve_workspace_path(session_id, unquote(rel))
            if not target.exists():
                return self._json({'items': [], 'path': str(rel)})
            if not target.is_dir():
                return self._json({'error': 'not_a_directory'}, 400)
            items = []
            for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                items.append({
                    'name': child.name,
                    'path': str((Path(rel) / child.name).as_posix()).lstrip('.'),
                    'is_dir': child.is_dir(),
                    'size': child.stat().st_size if child.is_file() else None,
                })
            return self._json({'path': rel, 'items': items})
        if parsed.path == '/api/workspace/read':
            session_id = parse_qs(parsed.query).get('session_id', [''])[0]
            rel = parse_qs(parsed.query).get('path', [''])[0]
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            target = _resolve_workspace_path(session_id, unquote(rel))
            if not target.exists() or not target.is_file():
                return self._json({'error': 'file_not_found'}, 404)
            try:
                content = target.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                return self._json({'error': 'binary_file'}, 400)
            return self._json({'path': rel, 'content': content})
        if parsed.path == '/api/workspace/raw':
            session_id = parse_qs(parsed.query).get('session_id', [''])[0]
            rel = parse_qs(parsed.query).get('path', [''])[0]
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            target = _resolve_workspace_path(session_id, unquote(rel))
            if not target.exists() or not target.is_file():
                return self._json({'error': 'file_not_found'}, 404)
            try:
                data = target.read_bytes()
            except OSError:
                return self._json({'error': 'file_read_failed'}, 500)
            mime_type, _ = mimetypes.guess_type(target.name)
            self.send_response(200)
            self.send_header('Content-Type', mime_type or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length) or b'{}')

        if parsed.path == '/api/session/create':
            first_message = _normalize_message_payload(payload.get('message'))
            session_id = uuid.uuid4().hex[:10]
            run_dir = PROJECT_ROOT / 'runs' / f'session_{session_id}'
            workspace = run_dir / 'workspaces' / 'task_0'
            title_text = _message_to_event_text(first_message)
            title = title_text[:48] if title_text else f'新会话 {session_id}'
            initial_events = []
            if _message_has_content(first_message):
                initial_events.append({
                    'type': 'user',
                    'label': 'User',
                    'content': title_text,
                    'created_at': datetime.now().isoformat(timespec='seconds')
                })
            sessions[session_id] = {
                'id': session_id,
                'title': title,
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'run_dir': str(run_dir),
                'workspace': str(workspace),
                'messages': [],
                'pending_user_message': first_message,
                'events': initial_events,
                'selected_model': str(payload.get('model') or 'openai'),
                'status': 'idle',
                'last_job_id': None,
                'cancel_requested': False,
            }
            _save_session(session_id)
            return self._json({'session_id': session_id})

        if parsed.path == '/api/session/message':
            session_id = str(payload.get('session_id') or '').strip()
            content = _normalize_message_payload(payload.get('message'))
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            if not _message_has_content(content):
                return self._json({'error': 'message_required'}, 400)
            session = sessions[session_id]
            session['pending_user_message'] = content
            session['status'] = 'queued'
            session.setdefault('events', []).append({
                'type': 'user',
                'label': 'User',
                'content': _message_to_event_text(content),
                'created_at': datetime.now().isoformat(timespec='seconds')
            })
            _save_session(session_id)
            return self._json({'ok': True})

        if parsed.path == '/api/session/model':
            session_id = str(payload.get('session_id') or '').strip()
            model = str(payload.get('model') or '').strip()
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            valid_keys = {item['key'] for item in AVAILABLE_MODELS}
            if model not in valid_keys:
                return self._json({'error': 'invalid_model'}, 400)
            sessions[session_id]['selected_model'] = model
            _save_session(session_id)
            return self._json({'session_id': session_id, 'selected_model': model})

        if parsed.path == '/api/session/run':
            session_id = str(payload.get('session_id') or '').strip()
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            session = sessions[session_id]
            _heal_stale_running_session(session_id, session)
            if _recover_messages_from_events(session):
                _save_session(session_id)
            if not _message_has_content(session.get('pending_user_message')) and not session.get('messages'):
                return self._json({'error': 'message_required'}, 400)
            job_id = uuid.uuid4().hex
            jobs[job_id] = {'id': job_id, 'session_id': session_id, 'task': 'message-history-session-run', 'status': 'running', 'created_at': datetime.now().isoformat(timespec='seconds'), 'logs': []}
            session['status'] = 'running'
            session['cancel_requested'] = False
            session['last_job_id'] = job_id
            _save_session(session_id)
            threading.Thread(target=_run_session_worker, args=(job_id, session_id), daemon=True).start()
            return self._json({'job_id': job_id, 'session_id': session_id, 'status': 'running'})

        if parsed.path == '/api/session/terminate':
            session_id = str(payload.get('session_id') or '').strip()
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            session = sessions[session_id]
            if session.get('status') != 'running':
                return self._json({'error': 'session_not_running'}, 409)
            session['cancel_requested'] = True
            session['status'] = 'cancelling'
            runtime = _ensure_runtime(session)
            runtime['phase'] = 'cancelling'
            runtime['updated_at'] = datetime.now().isoformat(timespec='seconds')
            session.setdefault('events', []).append({
                'type': 'system',
                'label': 'session_terminating',
                'content': 'Terminate requested by user',
                'created_at': datetime.now().isoformat(timespec='seconds'),
            })
            job_id = str(session.get('last_job_id') or '').strip()
            if job_id in jobs and jobs[job_id].get('status') == 'running':
                jobs[job_id]['status'] = 'cancelling'
            _save_session(session_id)
            return self._json({'ok': True, 'session_id': session_id, 'status': 'cancelling'})

        if parsed.path == '/api/session/delete':
            session_id = str(payload.get('session_id') or '').strip()
            remove_workspace = bool(payload.get('remove_workspace', True))
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)

            session = sessions[session_id]
            _heal_stale_running_session(session_id, session)
            if _is_job_running(session):
                return self._json({'error': 'session_running'}, 409)

            run_dir = Path(str(session.get('run_dir') or '')).resolve()
            session_file = _session_file(session_id)

            sessions.pop(session_id, None)
            session_versions.pop(session_id, None)
            if session_file.exists():
                try:
                    session_file.unlink()
                except OSError:
                    return self._json({'error': 'session_file_delete_failed'}, 500)

            # Keep in-memory jobs for debugging unless explicitly needed.
            if remove_workspace and run_dir.exists():
                try:
                    shutil.rmtree(run_dir)
                except OSError:
                    return self._json({'error': 'workspace_delete_failed'}, 500)

            return self._json({'ok': True, 'session_id': session_id, 'workspace_removed': remove_workspace})

        if parsed.path == '/api/workspace/write':
            session_id = str(payload.get('session_id') or '').strip()
            rel = str(payload.get('path') or '').strip()
            content = payload.get('content')
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            if not rel:
                return self._json({'error': 'path_required'}, 400)
            target = _resolve_workspace_path(session_id, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content or ''), encoding='utf-8')
            sessions[session_id].setdefault('events', []).append({'type': 'tool_result', 'label': 'workspace_write', 'content': f'Wrote {rel}', 'created_at': datetime.now().isoformat(timespec='seconds')})
            _save_session(session_id)
            return self._json({'ok': True, 'path': rel})

        if parsed.path == '/api/workspace/mkdir':
            session_id = str(payload.get('session_id') or '').strip()
            rel = str(payload.get('path') or '').strip()
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            if not rel:
                return self._json({'error': 'path_required'}, 400)
            target = _resolve_workspace_path(session_id, rel)
            target.mkdir(parents=True, exist_ok=True)
            sessions[session_id].setdefault('events', []).append({'type': 'tool_result', 'label': 'workspace_mkdir', 'content': f'Created dir {rel}', 'created_at': datetime.now().isoformat(timespec='seconds')})
            _save_session(session_id)
            return self._json({'ok': True, 'path': rel})

        if parsed.path == '/api/workspace/upload':
            session_id = str(payload.get('session_id') or '').strip()
            rel = str(payload.get('path') or '').strip()
            filename = str(payload.get('filename') or '').strip()
            content_base64 = str(payload.get('content_base64') or '')
            if not session_id or session_id not in sessions:
                return self._json({'error': 'session_not_found'}, 404)
            if not filename:
                return self._json({'error': 'filename_required'}, 400)
            if not content_base64:
                return self._json({'error': 'content_required'}, 400)
            try:
                data = base64.b64decode(content_base64, validate=True)
            except (binascii.Error, ValueError):
                return self._json({'error': 'invalid_base64'}, 400)
            target_rel = str((Path(rel) / filename).as_posix()).lstrip('./')
            target = _resolve_workspace_path(session_id, target_rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            sessions[session_id].setdefault('events', []).append({
                'type': 'tool_result',
                'label': 'workspace_upload',
                'content': f'Uploaded {target_rel} ({len(data)} bytes)',
                'created_at': datetime.now().isoformat(timespec='seconds')
            })
            _save_session(session_id)
            return self._json({'ok': True, 'path': target_rel, 'size': len(data)})

        return self._json({'error': 'not_found'}, 404)


def main():
    _load_sessions()
    server = ThreadingHTTPServer(('127.0.0.1', 8787), Handler)
    print('Materials playground web UI: http://127.0.0.1:8787')
    server.serve_forever()


if __name__ == '__main__':
    main()
