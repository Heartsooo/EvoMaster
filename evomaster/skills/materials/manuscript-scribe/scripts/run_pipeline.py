"""Resumable manuscript pipeline orchestrator.

This script manages high-level pipeline state and can proxy validation/assembly
stages while preserving a durable state contract.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_common'))
from longtask_runtime import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_FATAL_ERROR,
    STATUS_RUNNING,
    append_event,
    build_result,
    emit_result,
    init_or_load_state,
    parse_prefixed_result_line,
    read_json,
    write_json,
)


def _run_child(script_name: str, args: list[str]) -> tuple[int, str]:
    cmd = [sys.executable, str(Path(__file__).resolve().parent / script_name), *args]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        encoding='utf-8',
    )
    if proc.stdout:
        print(proc.stdout.rstrip('\n'))
    if proc.stderr:
        print(proc.stderr.rstrip('\n'), file=sys.stderr)
    combined = (proc.stdout or '') + '\n' + (proc.stderr or '')
    return proc.returncode, combined


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Run resumable manuscript pipeline stages.'
    )
    ap.add_argument(
        '--stage',
        required=True,
        choices=[
            'init',
            'checkpoint',
            'status',
            'validate',
            'assemble',
            'complete',
        ],
        help='Pipeline stage action to run.',
    )
    ap.add_argument(
        '--state',
        default='_tmp/manuscript/state.json',
        help='State file path.',
    )
    ap.add_argument(
        '--resume', action='store_true', help='Resume existing pipeline state.'
    )
    ap.add_argument('--title', default='', help='Document title for init stage.')
    ap.add_argument('--profile', default='', help='Format profile.')
    ap.add_argument('--draft', default='', help='Draft markdown file.')
    ap.add_argument('--sections_dir', default='', help='Sections directory.')
    ap.add_argument(
        '--output', default='', help='Output markdown file for assemble stage.'
    )
    ap.add_argument('--export', default='all', choices=['all', 'md', 'docx', 'latex'])
    ap.add_argument(
        '--planner_mode',
        action='store_true',
        help='Use planner-mode validation thresholds.',
    )
    ap.add_argument(
        '--next_stage', default='', help='Target stage for checkpoint action.'
    )
    ap.add_argument('--note', default='', help='Optional note for checkpoint/status.')
    args = ap.parse_args()

    state_path = Path(args.state)
    events_path = state_path.parent / 'events.jsonl'
    result_path = state_path.parent / 'result.json'

    state = init_or_load_state(
        state_path=state_path,
        task_type='manuscript',
        stage=args.stage,
        resume=args.resume,
    )

    if args.stage == 'init':
        if not args.title:
            emit_result(
                build_result(
                    status=STATUS_FATAL_ERROR,
                    stage='init',
                    message='--title is required for init stage.',
                    result_path=result_path,
                )
            )
            sys.exit(1)
        state.update(
            {
                'title': args.title,
                'profile': args.profile or state.get('profile', ''),
                'draft': args.draft or state.get('draft', ''),
                'sections_dir': args.sections_dir or state.get('sections_dir', ''),
                'output': args.output or state.get('output', ''),
                'current_stage': 'retrieve',
                'pipeline_status': STATUS_RUNNING,
            }
        )
        write_json(state_path, state)
        append_event(
            events_path=events_path,
            status=STATUS_RUNNING,
            stage='init',
            message='Pipeline initialized.',
            payload={'title': args.title, 'profile': state.get('profile', '')},
        )
        emit_result(
            build_result(
                status=STATUS_RUNNING,
                stage='init',
                message='Pipeline initialized. Next stage: retrieve.',
                result_path=result_path,
                payload={'next_stage': 'retrieve'},
            )
        )
        return

    if args.stage == 'checkpoint':
        next_stage = args.next_stage or state.get('current_stage', '')
        if not next_stage:
            emit_result(
                build_result(
                    status=STATUS_FATAL_ERROR,
                    stage='checkpoint',
                    message='Checkpoint requires --next_stage or existing current_stage in state.',
                    result_path=result_path,
                )
            )
            sys.exit(1)
        state['current_stage'] = next_stage
        if args.note:
            state['last_note'] = args.note
        state['pipeline_status'] = STATUS_RUNNING
        write_json(state_path, state)
        append_event(
            events_path=events_path,
            status=STATUS_RUNNING,
            stage='checkpoint',
            message=f"Checkpoint updated: {next_stage}",
            payload={'note': args.note},
        )
        emit_result(
            build_result(
                status=STATUS_RUNNING,
                stage='checkpoint',
                message=f"Checkpoint saved. Current stage: {next_stage}",
                result_path=result_path,
                payload={'current_stage': next_stage},
            )
        )
        return

    if args.stage == 'status':
        latest = read_json(state_path, default={})
        emit_result(
            build_result(
                status=str(latest.get('pipeline_status') or STATUS_RUNNING),
                stage='status',
                message='Pipeline status loaded.',
                result_path=result_path,
                payload={'state': latest, 'note': args.note},
            )
        )
        return

    if args.stage == 'validate':
        child_args: list[str] = ['--profile', args.profile or state.get('profile', '')]
        if args.draft or state.get('draft'):
            child_args += ['--draft', args.draft or state.get('draft', '')]
        elif args.sections_dir or state.get('sections_dir'):
            child_args += [
                '--sections_dir',
                args.sections_dir or state.get('sections_dir', ''),
            ]
        else:
            emit_result(
                build_result(
                    status=STATUS_FATAL_ERROR,
                    stage='validate',
                    message='validate stage requires draft or sections_dir (args or state).',
                    result_path=result_path,
                )
            )
            sys.exit(1)
        if args.planner_mode:
            child_args.append('--planner_mode')
        child_args += ['--state', str(state_path), '--resume']
        code, combined = _run_child('validate_content.py', child_args)
        parsed = parse_prefixed_result_line(combined) or {}
        status = str(
            parsed.get('status')
            or (STATUS_COMPLETED if code == 0 else STATUS_FATAL_ERROR)
        )
        state['current_stage'] = 'assemble' if status == STATUS_COMPLETED else 'fix'
        state['pipeline_status'] = status
        write_json(state_path, state)
        append_event(
            events_path=events_path,
            status=status if status in {STATUS_COMPLETED, STATUS_RUNNING} else status,
            stage='validate',
            message=str(parsed.get('message') or 'Validate stage finished.'),
            payload={'child_exit_code': code},
        )
        emit_result(
            build_result(
                status=status,
                stage='validate',
                message=str(parsed.get('message') or 'Validate stage finished.'),
                result_path=result_path,
                payload={'next_stage': state['current_stage']},
            )
        )
        return

    if args.stage == 'assemble':
        out = args.output or state.get('output', '')
        if not out:
            emit_result(
                build_result(
                    status=STATUS_FATAL_ERROR,
                    stage='assemble',
                    message='assemble stage requires --output (or output in state).',
                    result_path=result_path,
                )
            )
            sys.exit(1)
        child_args = [
            '--output',
            out,
            '--profile',
            args.profile or state.get('profile', ''),
            '--check_length',
        ]
        if args.draft or state.get('draft'):
            child_args += ['--draft', args.draft or state.get('draft', '')]
        elif args.sections_dir or state.get('sections_dir'):
            child_args += [
                '--sections_dir',
                args.sections_dir or state.get('sections_dir', ''),
            ]
        else:
            emit_result(
                build_result(
                    status=STATUS_FATAL_ERROR,
                    stage='assemble',
                    message='assemble stage requires draft or sections_dir (args or state).',
                    result_path=result_path,
                )
            )
            sys.exit(1)
        child_args += ['--export', args.export, '--state', str(state_path), '--resume']
        code, combined = _run_child('assemble_manuscript.py', child_args)
        parsed = parse_prefixed_result_line(combined) or {}
        status = str(
            parsed.get('status')
            or (STATUS_COMPLETED if code == 0 else STATUS_FATAL_ERROR)
        )
        state['output'] = out
        state['current_stage'] = 'polish' if status == STATUS_COMPLETED else 'fix'
        state['pipeline_status'] = status
        write_json(state_path, state)
        append_event(
            events_path=events_path,
            status=status if status in {STATUS_COMPLETED, STATUS_RUNNING} else status,
            stage='assemble',
            message=str(parsed.get('message') or 'Assemble stage finished.'),
            payload={'child_exit_code': code, 'output': out},
        )
        emit_result(
            build_result(
                status=status,
                stage='assemble',
                message=str(parsed.get('message') or 'Assemble stage finished.'),
                result_path=result_path,
                payload={'next_stage': state['current_stage'], 'output': out},
            )
        )
        return

    if args.stage == 'complete':
        state['current_stage'] = 'done'
        state['pipeline_status'] = STATUS_COMPLETED
        if args.note:
            state['completion_note'] = args.note
        write_json(state_path, state)
        append_event(
            events_path=events_path,
            status=STATUS_COMPLETED,
            stage='complete',
            message='Pipeline completed.',
            payload={'note': args.note},
        )
        emit_result(
            build_result(
                status=STATUS_COMPLETED,
                stage='complete',
                message='Pipeline completed.',
                result_path=result_path,
                payload={'state_file': str(state_path)},
            )
        )
        return


if __name__ == '__main__':
    main()
