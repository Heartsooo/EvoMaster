from __future__ import annotations

import json
import tarfile
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

from evomaster.utils.types import AssistantMessage, Dialog, StepRecord, SystemMessage, TaskInstance, ToolMessage, UserMessage
from evomaster.utils import LLMConfig, create_llm
from playground.materials_playground.core.playground import MaterialsPlayground


def _restore_dialog(messages: list[dict[str, Any]], *, system_prompt: str, tools: list) -> Dialog:
    restored = [SystemMessage(content=system_prompt)]
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content')
        if content is None:
            content = ''
        if role == 'user':
            restored.append(UserMessage(content=content))
        elif role == 'assistant':
            restored.append(AssistantMessage(content=content))
    return Dialog(messages=restored, tools=tools)


def _step_to_events(step: StepRecord, step_no: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    events.append({
        'type': 'system',
        'label': f'Step {step_no}',
        'content': f'Agent step {step_no} started',
        'step_id': step.step_id,
        'timestamp': step.timestamp.isoformat(),
    })

    if step.assistant_message and getattr(step.assistant_message, 'reasoning_content', None):
        events.append({
            'type': 'assistant',
            'label': 'Thinking',
            'content': str(step.assistant_message.reasoning_content),
            'step_id': step.step_id,
            'timestamp': step.timestamp.isoformat(),
            'is_reasoning': True,
        })

    if step.assistant_message and step.assistant_message.content:
        events.append({
            'type': 'assistant',
            'label': 'Assistant',
            'content': str(step.assistant_message.content),
            'step_id': step.step_id,
            'timestamp': step.timestamp.isoformat(),
        })

    tool_call_map = {}
    if step.assistant_message and step.assistant_message.tool_calls:
        for tc in step.assistant_message.tool_calls:
            call_id = tc.id or f'{tc.function.name}_{step.step_id}'
            tool_call_map[call_id] = tc.function.name
            events.append({
                'type': 'tool_call',
                'label': tc.function.name,
                'tool_name': tc.function.name,
                'call_id': call_id,
                'arguments': tc.function.arguments,
                'content': tc.function.arguments,
                'step_id': step.step_id,
                'timestamp': step.timestamp.isoformat(),
            })

    for tr in step.tool_responses:
        result_text = str(tr.content or '')
        call_id = tr.tool_call_id
        tool_name = tr.name
        status = tr.meta.get('status', 'success') if isinstance(tr.meta, dict) else 'success'
        payload = tr.meta if isinstance(tr.meta, dict) else {}

        if tool_name == 'execute_bash' and result_text:
            chunks = []
            lines = result_text.splitlines()
            chunk_size = 20
            for i in range(0, len(lines), chunk_size):
                chunk = '\n'.join(lines[i:i+chunk_size]).strip()
                if chunk:
                    chunks.append(chunk)
            if len(chunks) > 1:
                for idx, chunk in enumerate(chunks[:-1], start=1):
                    events.append({
                        'type': 'tool_progress',
                        'label': tool_name,
                        'tool_name': tool_name,
                        'call_id': call_id,
                        'content': chunk,
                        'progress_index': idx,
                        'step_id': step.step_id,
                        'timestamp': step.timestamp.isoformat(),
                    })
                result_text = chunks[-1]

        events.append({
            'type': 'tool_result',
            'label': tool_name,
            'tool_name': tool_name,
            'call_id': call_id,
            'status': status,
            'payload': payload,
            'result': result_text,
            'content': result_text,
            'step_id': step.step_id,
            'timestamp': step.timestamp.isoformat(),
        })
    return events


def _dict_step_to_events(step: dict[str, Any], step_no: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    step_id = step.get('step_id', step_no)
    assistant = step.get('assistant_message') or {}
    tool_responses = step.get('tool_responses') or []

    events.append({
        'type': 'system',
        'label': f'Step {step_no}',
        'content': f'Agent step {step_no} started',
        'step_id': step_id,
        'timestamp': '',
    })

    content = assistant.get('content') if isinstance(assistant, dict) else None
    reasoning = assistant.get('reasoning_content') if isinstance(assistant, dict) else None
    if reasoning:
        events.append({
            'type': 'assistant',
            'label': 'Thinking',
            'content': str(reasoning),
            'step_id': step_id,
            'timestamp': '',
            'is_reasoning': True,
        })

    if content:
        events.append({
            'type': 'assistant',
            'label': 'Assistant',
            'content': str(content),
            'step_id': step_id,
            'timestamp': '',
        })

    tool_calls = assistant.get('tool_calls') or [] if isinstance(assistant, dict) else []
    for tc in tool_calls:
        fn = ((tc or {}).get('function') or {}) if isinstance(tc, dict) else {}
        name = fn.get('name', 'tool')
        args = fn.get('arguments', '')
        call_id = (tc or {}).get('id') or f'{name}_{step_id}'
        events.append({
            'type': 'tool_call',
            'label': name,
            'tool_name': name,
            'call_id': call_id,
            'arguments': args,
            'content': args,
            'step_id': step_id,
            'timestamp': '',
        })

    for tr in tool_responses:
        if not isinstance(tr, dict):
            continue
        result_text = str(tr.get('content') or '')
        tool_name = tr.get('name') or 'tool'
        call_id = tr.get('tool_call_id')
        payload = tr.get('meta') if isinstance(tr.get('meta'), dict) else {}
        status = payload.get('status', 'success') if isinstance(payload, dict) else 'success'
        events.append({
            'type': 'tool_result',
            'label': tool_name,
            'tool_name': tool_name,
            'call_id': call_id,
            'status': status,
            'payload': payload,
            'result': result_text,
            'content': result_text,
            'step_id': step_id,
            'timestamp': '',
        })
    return events



def _load_events_from_saved_trajectory(run_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(run_dir) / 'trajectories' / 'task_0' / 'trajectory.json'
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []

    records = data if isinstance(data, list) else [data]
    events: list[dict[str, Any]] = []
    for record in records:
        trajectory = record.get('trajectory') if isinstance(record, dict) else None
        steps = trajectory.get('steps', []) if isinstance(trajectory, dict) else []
        for idx, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                events.extend(_dict_step_to_events(step, idx))
    return events


def _safe_download(url: str, target: Path) -> bool:
    if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
        return False
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return True
    except Exception:
        return False


def _short_artifact_name(value: str) -> str:
    if not isinstance(value, str) or not value:
        return 'artifact'
    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        name = Path(parsed.path).name
        return name or 'artifact'
    if value.startswith('local://'):
        value = value[len('local://'):]
    return Path(value).name or 'artifact'


def _collect_struct_db_artifact_refs(payload: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {
        'http_files': [],
        'local_files': [],
        'http_structures': [],
        'local_structures': [],
    }

    for item in payload.get('files') or []:
        if not isinstance(item, str):
            continue
        if item.startswith(('http://', 'https://')):
            refs['http_files'].append(item)
        elif item.startswith('local://'):
            refs['local_files'].append(item)

    for result in payload.get('results') or []:
        if not isinstance(result, dict):
            continue
        structure_file = result.get('structure_file')
        if not isinstance(structure_file, str):
            continue
        if structure_file.startswith(('http://', 'https://')):
            refs['http_structures'].append(structure_file)
        else:
            refs['local_structures'].append(structure_file)

    return refs


def _materialize_struct_db_artifacts(events: list[dict[str, Any]], workspace: Path) -> list[dict[str, Any]]:
    extra_events: list[dict[str, Any]] = []
    downloads_dir = workspace / 'downloads' / 'mat_struct_db'
    downloads_dir.mkdir(parents=True, exist_ok=True)

    for event in events:
        if event.get('type') != 'tool_result':
            continue
        if event.get('tool_name') != 'mat_struct_db_fetch_structures_from_db':
            continue

        payload = None
        info = ((event.get('payload') or {}).get('info') or {}) if isinstance(event.get('payload'), dict) else {}
        parsed = info.get('parsed_result') if isinstance(info, dict) else None
        if isinstance(parsed, dict):
            payload = parsed
        if payload is None:
            try:
                payload = json.loads(event.get('content') or '{}')
            except Exception:
                continue

        refs = _collect_struct_db_artifact_refs(payload)

        downloaded = []
        for file_url in [*refs['http_files'], *refs['http_structures']]:
            if not isinstance(file_url, str):
                continue
            name = _short_artifact_name(file_url)
            target = downloads_dir / name
            if _safe_download(str(file_url), target):
                downloaded.append(str(target.relative_to(workspace)))

        output_dir_url = payload.get('output_dir') or ''
        if not downloaded and isinstance(output_dir_url, str) and output_dir_url.startswith('http') and output_dir_url.endswith('.tgz'):
            archive_path = downloads_dir / Path(output_dir_url.split('?', 1)[0]).name
            if _safe_download(output_dir_url, archive_path):
                extract_dir = downloads_dir / archive_path.stem.replace('.tar', '')
                extract_dir.mkdir(parents=True, exist_ok=True)
                try:
                    with tarfile.open(archive_path, 'r:gz') as tar:
                        tar.extractall(extract_dir)
                    downloaded.append(str(extract_dir.relative_to(workspace)))
                except Exception:
                    pass

        if downloaded:
            extra_events.append({
                'type': 'system',
                'label': 'artifacts_downloaded',
                'content': 'Downloaded struct-db artifacts to: ' + ', '.join(downloaded),
                'created_at': event.get('timestamp', ''),
            })
        else:
            local_file_count = len(refs['local_files']) + len(refs['local_structures'])
            local_only = isinstance(output_dir_url, str) and output_dir_url.startswith('local://')
            detail = 'Struct-db returned no downloadable OSS file list; only remote/local paths were available.'
            if local_file_count or local_only:
                detail = f'Struct-db returned local-only artifacts ({local_file_count} local file entries); no HTTP/OSS download URL was available.'
            extra_events.append({
                'type': 'system',
                'label': 'artifacts_not_downloaded',
                'content': detail,
                'created_at': event.get('timestamp', ''),
            })

        summary_bits = []
        if refs['http_files'] or refs['http_structures']:
            http_names = [_short_artifact_name(x) for x in [*refs['http_files'], *refs['http_structures']][:6]]
            summary_bits.append('HTTP/OSS: ' + ', '.join(http_names))
        if refs['local_files'] or refs['local_structures']:
            local_names = [_short_artifact_name(x) for x in [*refs['local_files'], *refs['local_structures']][:6]]
            summary_bits.append('Remote-local: ' + ', '.join(local_names))
        if isinstance(output_dir_url, str) and output_dir_url:
            summary_bits.append('output_dir=' + _short_artifact_name(output_dir_url))

        if summary_bits:
            extra_events.append({
                'type': 'system',
                'label': 'artifacts_summary',
                'content': 'Struct-db artifacts summary — ' + ' | '.join(summary_bits),
                'created_at': event.get('timestamp', ''),
            })

    return extra_events



def run_session_messages(
    *,
    config_path: str | Path,
    run_dir: str | Path,
    session_id: str,
    history_messages: list[dict[str, Any]],
    new_user_message: Any,
    retry_callback=None,
    llm_event_callback=None,
    llm_name: str | None = None,
    should_cancel=None,
) -> dict[str, Any]:
    pg = MaterialsPlayground(config_path=Path(config_path))
    pg.set_run_dir(Path(run_dir), task_id='task_0')
    try:
        pg.setup()
        pg._setup_trajectory_file()
        agent = pg.agent
        llm_section = getattr(pg.config, 'llm', None)
        llm_cfg = None
        if llm_name and llm_section is not None:
            if hasattr(llm_section, 'model_dump'):
                llm_map = llm_section.model_dump()
            elif isinstance(llm_section, dict):
                llm_map = llm_section
            else:
                llm_map = getattr(llm_section, '__dict__', {}) or {}
            llm_cfg = llm_map.get(llm_name)
        if llm_cfg:
            output_config = getattr(agent, 'output_config', None)
            agent.llm = create_llm(LLMConfig(**llm_cfg), output_config=output_config)
            agent.context_manager.set_summary_llm(agent.llm)
        if getattr(agent, "llm", None) is not None:
            setattr(agent.llm, "retry_callback", retry_callback)
            setattr(agent.llm, "_materials_retry_callback", retry_callback)
            setattr(agent.llm, "_materials_event_callback", llm_event_callback)

        bootstrap_task = TaskInstance(task_id=session_id, task_type='session', description='session bootstrap')
        agent._initialize(bootstrap_task)
        assert agent.current_dialog is not None
        system_prompt = str(agent.current_dialog.messages[0].content or '')
        agent.current_dialog = _restore_dialog(history_messages, system_prompt=system_prompt, tools=agent._get_tool_specs())

        collected_events: list[dict[str, Any]] = []

        def on_step(step: StepRecord, step_number: int, max_steps: int):
            if callable(should_cancel) and should_cancel():
                raise RuntimeError('session_cancelled')
            collected_events.extend(_step_to_events(step, step_number))

        if callable(should_cancel) and should_cancel():
            raise RuntimeError('session_cancelled')
        trajectory = agent.continue_run(new_user_message, on_step=on_step)

        if not collected_events:
            collected_events = _load_events_from_saved_trajectory(run_dir)

        collected_events.extend(_materialize_struct_db_artifacts(collected_events, Path(run_dir) / 'workspaces' / 'task_0'))

        assistant_messages = []
        for msg in agent.get_conversation_history():
            if isinstance(msg, AssistantMessage) and msg.content:
                assistant_messages.append(str(msg.content))
        assistant_text = assistant_messages[-1] if assistant_messages else ''

        step_count = len(getattr(trajectory, 'steps', []) or [])
        if not step_count:
            step_count = len({ev.get('step_id') for ev in collected_events if ev.get('step_id') is not None})

        return {
            'status': trajectory.status,
            'steps': step_count,
            'assistant_text': assistant_text,
            'events': collected_events,
            'history_message_count': len(agent.get_conversation_history()),
        }
    finally:
        pg.cleanup()
