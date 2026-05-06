"""
Append a chunk of text to a file (e.g. temp file for section drafting).
Use after each "search -> agent LLM summarize" cycle: append the summary to a temp file,
then later use that file as --content_file for write_section or as input to assemble.

Usage:
  python append_chunk.py --path "_tmp/section_Introduction.md" --content "First paragraph..."
  python append_chunk.py --path "_tmp/section_Introduction.md" --content_file "notes.txt"
  python append_chunk.py --path "_tmp/chunks.md" --content "Next paragraph..." --separator "\\n\\n"

Output: Appends to the file (creating parent dirs and file if missing). Prints the path and new line count.
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Append a chunk to a file (e.g. temp file for search-summarize cycles)."
    )
    ap.add_argument(
        "--path",
        required=True,
        help="File to append to (e.g. _tmp/section_Introduction.md)",
    )
    ap.add_argument("--content", default=None, help="Inline text to append")
    ap.add_argument(
        "--content_file", default=None, help="Path to file whose content to append"
    )
    ap.add_argument(
        "--separator",
        default="\n\n",
        help="String to add before this chunk (default: double newline)",
    )
    args = ap.parse_args()

    raw = ""
    if args.content_file:
        p = Path(args.content_file)
        if p.exists():
            raw = p.read_text(encoding="utf-8").strip()
    if args.content:
        raw = (raw + "\n" + args.content).strip() if raw else args.content.strip()

    if not raw:
        print(
            "No content to append (provide --content or --content_file).",
            file=sys.stderr,
        )
        sys.exit(1)

    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith(("\n", "\r")):
            existing = existing.rstrip() + args.separator
        new_content = existing + raw
    else:
        new_content = raw

    path.write_text(new_content, encoding="utf-8")
    lines = len(new_content.splitlines())
    print(f"Appended to {path} ({lines} lines total).", flush=True)


if __name__ == "__main__":
    main()
