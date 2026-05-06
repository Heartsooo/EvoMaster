"""
Create a new manuscript draft with a standard outline driven by format profiles.

Available profiles (use --list_formats to see all):
  research_paper, grant, computational_report, patent, review,
  technical_report, thesis_section

With --sections_dir, creates one file per section for later assembly and writes
a _profile.json so downstream scripts can auto-detect the profile.

Usage:
  python init_manuscript.py --title "My Paper" --template "research_paper"
  python init_manuscript.py --title "My Paper" --template "research_paper" --sections_dir sections/
  python init_manuscript.py --title "Computation Report" --template "computational_report"
  python init_manuscript.py --list_formats

Output: Creates draft_manuscript.md (or --output path), or section files under sections_dir.
"""

import argparse
import json
import sys
from pathlib import Path

# Allow importing format_profiles when script is run from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
from format_profiles import (  # noqa: E402
    FORMAT_PROFILES,
    all_profiles_summary,
    get_profile,
)
from longtask_runtime import now_iso, write_json  # noqa: E402


def _build_outline(title: str, profile: dict) -> str:
    """Generate a Markdown outline from a format profile."""
    parts = [f"# {title}\n"]
    for section_name in profile["sections"]:
        meta = profile["section_meta"].get(section_name, {})
        hint = meta.get("writing_hint", "")
        min_w = meta.get("min_words", 0)
        max_w = meta.get("max_words")
        elems = meta.get("required_elements", [])

        parts.append(f"## {section_name}\n")
        # Add writing guidance as HTML comment (visible in editor, invisible in render)
        hints = []
        if min_w:
            hints.append(f"min_words: {min_w}")
        if max_w:
            hints.append(f"max_words: {max_w}")
        if elems:
            hints.append(f"include: {', '.join(elems)}")
        if hint:
            hints.append(hint)
        if hints:
            parts.append(f"<!-- {'; '.join(hints)} -->\n")
        parts.append("(TBD)\n")
    return "\n".join(parts)


def _build_section_file(title: str, section_name: str, meta: dict) -> str:
    """Generate content for a single section file."""
    hint = meta.get("writing_hint", "")
    min_w = meta.get("min_words", 0)
    max_w = meta.get("max_words")
    elems = meta.get("required_elements", [])

    parts = [f"# {title}\n", f"## {section_name}\n"]
    hints = []
    if min_w:
        hints.append(f"min_words: {min_w}")
    if max_w:
        hints.append(f"max_words: {max_w}")
    if elems:
        hints.append(f"include: {', '.join(elems)}")
    if hint:
        hints.append(hint)
    if hints:
        parts.append(f"<!-- {'; '.join(hints)} -->\n")

    if section_name == "References":
        parts.append("[1] Author. Title. *Journal* Year. https://doi.org/...\n")
    else:
        parts.append("(TBD)\n")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Initialize a manuscript draft with outline from a format profile."
    )
    ap.add_argument(
        "--title",
        default=None,
        help="Paper or grant title (required unless --list_formats)",
    )
    ap.add_argument(
        "--template",
        default="research_paper",
        choices=list(FORMAT_PROFILES),
        help=f"Format profile (choices: {', '.join(sorted(FORMAT_PROFILES))})",
    )
    ap.add_argument(
        "--output", default=None, help="Output path (default: draft_manuscript.md)"
    )
    ap.add_argument(
        "--sections_dir",
        default=None,
        help="Create one .md file per section in this directory for later assembly",
    )
    ap.add_argument(
        "--list_formats",
        action="store_true",
        help="List all available format profiles and exit",
    )
    args = ap.parse_args()

    # ── List formats and exit ──────────────────────────────────────────
    if args.list_formats:
        print("Available format profiles:\n")
        print(all_profiles_summary())
        return

    # ── Title is required for actual initialization ────────────────────
    if not args.title:
        print(
            "Error: --title is required (unless using --list_formats).", file=sys.stderr
        )
        sys.exit(1)

    profile = get_profile(args.template)

    # ── Sections directory mode ────────────────────────────────────────
    if args.sections_dir:
        sections_dir = Path(args.sections_dir)
        sections_dir.mkdir(parents=True, exist_ok=True)
        for name in profile["sections"]:
            meta = profile["section_meta"].get(name, {})
            path = sections_dir / f"{name}.md"
            content = _build_section_file(args.title, name, meta)
            path.write_text(content, encoding="utf-8")

        # Write profile metadata for downstream scripts
        profile_path = sections_dir / "_profile.json"
        profile_path.write_text(
            json.dumps(
                {"template": args.template, "title": args.title, **profile},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(
            f"Section files created in {sections_dir} (template: {args.template}). "
            f"Run write_section for each, then assemble_manuscript."
        )
        return

    # ── Single draft file mode ─────────────────────────────────────────
    out_path = Path(args.output or "draft_manuscript.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = _build_outline(args.title, profile)
    out_path.write_text(body, encoding="utf-8")
    print(f"Manuscript initialized: {out_path} (template: {args.template})")

    # Persist profile to state.json so downstream write_section / assemble_manuscript
    # can auto-detect it without requiring --profile on every call.
    state_path = Path("_tmp/manuscript/state.json")
    write_json(
        state_path,
        {
            "task_type": "manuscript",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "stage": "init_manuscript",
            "profile": args.template,
            "draft": str(out_path),
            "attempts": 1,
        },
    )
    print(f"Profile '{args.template}' persisted to {state_path}.")


if __name__ == "__main__":
    main()
