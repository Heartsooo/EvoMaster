"""
Write or update one section of a manuscript from raw notes or data. Supports chunked writing:
use once to create the section, then --append to add more paragraphs (avoids generating whole section in one go).
Citations: [n](URL) or [n](#ref-n); References section must list same [n]. See reference/citation_and_references.md.

With --profile, prints a word-count warning if the section is below the profile's minimum.
With --min_words, uses an explicit floor instead.

When --profile is given the section name is resolved through ``format_profiles.resolve_section()``
so common aliases (e.g. "Computational Methods" → "Methods") work transparently and strict
profiles reject unknown section names with exit-code 2.

Usage:
  python write_section.py --section "Methods" --content_file "methods_notes.txt" --draft "draft_manuscript.md"
  python write_section.py --section "Introduction" --content "First paragraph..." --output "sections/Introduction.md"
  python write_section.py --section "Introduction" --append --content "Second paragraph..." --draft "draft_manuscript.md"
  python write_section.py --section "Methods" --content_file m.txt --draft d.md --profile computational_report

Output: Updates the draft file or writes to --output; with --append, appends to existing section body.
"""

import argparse
import re
import sys
from pathlib import Path

# Allow importing sibling modules when script is run from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_utils import find_section as _find_section  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
from longtask_runtime import (  # noqa: E402
    STATUS_COMPLETED,
    append_event,
    build_result,
    emit_result,
    init_or_load_state,
)
from longtask_runtime import read_json as _read_state_json  # noqa: E402

try:
    from format_profiles import get_profile as _get_profile
    from format_profiles import resolve_section as _resolve_section
except ImportError:
    _get_profile = None  # type: ignore[assignment]
    _resolve_section = None  # type: ignore[assignment]


def _word_count(text: str) -> int:
    """Count words (handles mixed CJK and Latin text)."""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))
    return cjk + latin


def _check_word_count(
    section_name: str,
    body: str,
    profile_name: str | None,
    min_words_override: int | None,
) -> tuple[int, int, bool]:
    """Print word count and warn if below minimum.

    Returns: (word_count, min_words, is_under_minimum)
    """
    wc = _word_count(body)
    min_w = min_words_override or 0

    if not min_w and profile_name and _get_profile is not None:
        try:
            profile = _get_profile(profile_name)
            meta = profile.get("section_meta", {}).get(section_name, {})
            min_w = meta.get("min_words", 0)
        except KeyError:
            pass

    if min_w and wc < min_w:
        print(
            f"WARNING: {section_name} has {wc} words (minimum {min_w}). "
            f"Consider adding more content with --append or --content_file.",
            flush=True,
        )
        return wc, min_w, True
    else:
        print(f"Section {section_name}: {wc} words.", flush=True)
    return wc, min_w, False


def _default_state_path() -> Path:
    return Path("_tmp/manuscript/state.json")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Write or append to one section of a manuscript."
    )
    ap.add_argument(
        "--section", required=True, help="Section name (e.g. Methods, Introduction)"
    )
    ap.add_argument(
        "--content_file", default=None, help="Path to file with raw notes or JSON"
    )
    ap.add_argument(
        "--content", default=None, help="Inline content (paragraph or chunk)"
    )
    ap.add_argument(
        "--append",
        action="store_true",
        help="Append to existing section body instead of replacing",
    )
    ap.add_argument(
        "--tone", default="formal", choices=["formal", "neutral"], help="Writing tone"
    )
    ap.add_argument(
        "--draft", default=None, help="Path to draft file (to update one section)"
    )
    ap.add_argument(
        "--output",
        default=None,
        help="Write section to this file (e.g. sections/Introduction.md)",
    )
    ap.add_argument(
        "--profile",
        default=None,
        help="Format profile name (e.g. research_paper, computational_report). "
        "Used for section-name validation and word-count minimums.",
    )
    ap.add_argument(
        "--min_words",
        type=int,
        default=None,
        help="Explicit minimum word count (overrides profile setting).",
    )
    ap.add_argument(
        "--state",
        default=None,
        help="Optional long-task state file path (default: _tmp/manuscript/state.json).",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Resume and update existing state file when available.",
    )
    args = ap.parse_args()

    # ── 3a: Auto-detect profile from state.json when --profile not given ──
    # This allows write_section to inherit the profile set by init_manuscript
    # without requiring the agent to pass --profile on every call.
    if args.profile is None:
        try:
            _st = _read_state_json(_default_state_path(), default={})
            args.profile = _st.get("profile") or None
        except Exception:
            pass

    # ── Section-name resolution via format_profiles ──────────────────
    if args.profile and _resolve_section is not None:
        try:
            args.section = _resolve_section(args.profile, args.section)
        except (ValueError, KeyError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)

    if not args.draft and not args.output:
        args.draft = "draft_manuscript.md"
    if args.draft and args.output:
        print("Use either --draft or --output, not both.", file=sys.stderr)
        sys.exit(1)

    draft_path = Path(args.draft or args.output)
    raw = ""
    if args.content_file:
        p = Path(args.content_file)
        if p.exists():
            raw = p.read_text(encoding="utf-8")
    if args.content:
        raw = (raw + "\n" + args.content).strip()

    new_body = raw.strip() or "(Section content not provided.)"
    new_section = f"## {args.section}\n\n{new_body}\n\n"

    # --- Determine the final body text for word-count reporting ---
    final_body = new_body

    if args.output:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(new_section.strip(), encoding="utf-8")
        print(f"Section {args.section} written to {draft_path}.")
        wc, min_w, is_under = _check_word_count(
            args.section,
            final_body,
            args.profile,
            args.min_words,
        )
        state_path = Path(args.state) if args.state else _default_state_path()
        result_path = state_path.parent / "result.json"
        events_path = state_path.parent / "events.jsonl"
        _extra: dict = {
            "section": args.section,
            "draft_path": str(draft_path),
            "warnings": ["under_minimum_words"] if is_under else [],
        }
        if args.profile is not None:
            _extra["profile"] = args.profile
        init_or_load_state(
            state_path=state_path,
            task_type="manuscript",
            stage="write_section",
            resume=args.resume,
            extra=_extra,
        )
        append_event(
            events_path=events_path,
            status=STATUS_COMPLETED,
            stage="write_section",
            message=f"Section {args.section} updated.",
            payload={
                "section": args.section,
                "word_count": wc,
                "min_words": min_w,
                "under_minimum_words": is_under,
                "draft_path": str(draft_path),
            },
        )
        emit_result(
            build_result(
                status=STATUS_COMPLETED,
                stage="write_section",
                message=f"Section {args.section} updated.",
                result_path=result_path,
                payload={
                    "section": args.section,
                    "word_count": wc,
                    "min_words": min_w,
                    "under_minimum_words": is_under,
                    "draft_path": str(draft_path),
                },
            )
        )
        return

    if not draft_path.exists():
        draft_path.write_text(f"# Draft\n\n{new_section}", encoding="utf-8")
        print(f"Section {args.section} written to {draft_path}.")
        wc, min_w, is_under = _check_word_count(
            args.section,
            final_body,
            args.profile,
            args.min_words,
        )
        state_path = Path(args.state) if args.state else _default_state_path()
        result_path = state_path.parent / "result.json"
        events_path = state_path.parent / "events.jsonl"
        _extra2: dict = {
            "section": args.section,
            "draft_path": str(draft_path),
            "warnings": ["under_minimum_words"] if is_under else [],
        }
        if args.profile is not None:
            _extra2["profile"] = args.profile
        init_or_load_state(
            state_path=state_path,
            task_type="manuscript",
            stage="write_section",
            resume=args.resume,
            extra=_extra2,
        )
        append_event(
            events_path=events_path,
            status=STATUS_COMPLETED,
            stage="write_section",
            message=f"Section {args.section} created.",
            payload={
                "section": args.section,
                "word_count": wc,
                "min_words": min_w,
                "under_minimum_words": is_under,
                "draft_path": str(draft_path),
            },
        )
        emit_result(
            build_result(
                status=STATUS_COMPLETED,
                stage="write_section",
                message=f"Section {args.section} created.",
                result_path=result_path,
                payload={
                    "section": args.section,
                    "word_count": wc,
                    "min_words": min_w,
                    "under_minimum_words": is_under,
                    "draft_path": str(draft_path),
                },
            )
        )
        return

    content = draft_path.read_text(encoding="utf-8")
    span = _find_section(content, args.section, include_text=True)
    if span is None:
        if "## References" in content:
            content = content.replace("## References", new_section + "## References")
        else:
            content = content.rstrip() + "\n\n" + new_section
        draft_path.write_text(content, encoding="utf-8")
        print(f"Section {args.section} written to {draft_path}.")
        _check_word_count(args.section, final_body, args.profile, args.min_words)
        return

    start, end, existing = span
    if args.append:
        # Append new_body to existing section (after header, before next ##)
        lines = existing.splitlines()
        header = lines[0] if lines else f"## {args.section}"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        combined = f"{body}\n\n{new_body}".strip() if body else new_body
        replacement = f"{header}\n\n{combined}\n\n"
        final_body = combined
    else:
        replacement = new_section
    content = content[:start] + replacement + content[end:].lstrip()
    draft_path.write_text(content, encoding="utf-8")
    print(f"Section {args.section} written to {draft_path}.")
    wc, min_w, is_under = _check_word_count(
        args.section,
        final_body,
        args.profile,
        args.min_words,
    )
    state_path = Path(args.state) if args.state else _default_state_path()
    result_path = state_path.parent / "result.json"
    events_path = state_path.parent / "events.jsonl"
    _extra3: dict = {
        "section": args.section,
        "draft_path": str(draft_path),
        "warnings": ["under_minimum_words"] if is_under else [],
    }
    if args.profile is not None:
        _extra3["profile"] = args.profile
    init_or_load_state(
        state_path=state_path,
        task_type="manuscript",
        stage="write_section",
        resume=args.resume,
        extra=_extra3,
    )
    append_event(
        events_path=events_path,
        status=STATUS_COMPLETED,
        stage="write_section",
        message=f"Section {args.section} updated.",
        payload={
            "section": args.section,
            "word_count": wc,
            "min_words": min_w,
            "under_minimum_words": is_under,
            "draft_path": str(draft_path),
        },
    )
    emit_result(
        build_result(
            status=STATUS_COMPLETED,
            stage="write_section",
            message=f"Section {args.section} updated.",
            result_path=result_path,
            payload={
                "section": args.section,
                "word_count": wc,
                "min_words": min_w,
                "under_minimum_words": is_under,
                "draft_path": str(draft_path),
            },
        )
    )


if __name__ == "__main__":
    main()
