"""ABACUS Docs Index — navigational index for documentation pages."""

import re
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent.parent / "pages"

_index_built = False
page_by_title: dict[str, Path] = {}
page_by_filename: dict[str, Path] = {}
all_titles: list[str] = []


def build_index():
    global _index_built
    if _index_built:
        return
    if not _DOCS_DIR.exists():
        _index_built = True
        return

    for txt_file in _DOCS_DIR.glob("*.txt"):
        try:
            first_line = txt_file.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
        except Exception:
            continue
        title = first_line.replace("Title: ", "").strip()
        page_by_title[title.lower()] = txt_file
        page_by_filename[txt_file.stem.lower().replace("__", " ").replace("_", " ")] = txt_file

    all_titles.extend(sorted(page_by_title.keys()))
    _index_built = True


def lookup_page(name: str):
    build_index()
    key = name.strip().lower()
    if key in page_by_title:
        return page_by_title[key]
    for k, v in page_by_filename.items():
        if key in k:
            return v
    return None


def fuzzy_title_matches(query: str, limit: int = 10) -> list[str]:
    build_index()
    q = query.strip().lower()
    return [t for t in all_titles if q in t][:limit]
