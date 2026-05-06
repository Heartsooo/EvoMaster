"""VASP Wiki Index — pre-built navigational index mimicking wiki structure.

Builds once on first import, then provides O(1) lookups:
  - page_by_title:  exact title → page path
  - pages_by_category:  category name → list of member page paths
  - related_links:  page title → list of related page titles
  - all_titles:  sorted list for fuzzy matching
"""

import os
import re
from pathlib import Path

_WIKI_DIR = Path(__file__).resolve().parent.parent / "pages"

# ── Singleton index ────────────────────────────────────────────────────

_index_built = False

# title (lowercase) → Path
page_by_title: dict[str, Path] = {}
# original-case title → Path (for display)
page_by_title_orig: dict[str, Path] = {}
# filename stem (lowercase, underscores→spaces) → Path
page_by_filename: dict[str, Path] = {}
# category name (lowercase) → [page Paths]
pages_by_category: dict[str, list[Path]] = {}
# title (lowercase) → [related title strings]
related_links: dict[str, list[str]] = {}
# sorted list of all titles (lowercase)
all_titles: list[str] = []


def _extract_title(content: str) -> str:
    first_line = content.split("\n", 1)[0]
    return first_line.replace("Title: ", "").strip()


def _extract_related(content: str) -> list[str]:
    """Extract 'Related tags and articles' section."""
    m = re.search(r"Related tags and articles\n(.+?)(?:\n(?:Examples|Retrieved|$))", content, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    # Related items are comma-or-newline separated, often with wiki markup artifacts
    items = re.split(r"[,\n]", block)
    cleaned = []
    for item in items:
        item = item.strip().strip(",").strip()
        # Remove wiki cruft like "— theory background"
        item = re.split(r"\s*[—–\-]\s", item)[0].strip()
        if item and len(item) > 1 and not item.startswith("Retrieved") and not item.startswith("Examples"):
            cleaned.append(item)
    return cleaned


def build_index():
    global _index_built
    if _index_built:
        return

    if not _WIKI_DIR.exists():
        _index_built = True
        return

    for txt_file in _WIKI_DIR.glob("*.txt"):
        try:
            content = txt_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        title = _extract_title(content)
        title_lower = title.lower()
        fname_key = txt_file.stem.lower().replace("_", " ")

        page_by_title[title_lower] = txt_file
        page_by_title_orig[title] = txt_file
        page_by_filename[fname_key] = txt_file

        # Category membership
        if fname_key.startswith("category ") or fname_key.startswith("category:"):
            cat_name = fname_key.replace("category ", "").replace("category:", "").strip()
            if cat_name not in pages_by_category:
                pages_by_category[cat_name] = []
            # Parse member pages from category content (lines that look like page titles)
            for line in content.split("\n"):
                line = line.strip()
                if (
                    line
                    and not line.startswith("Title:")
                    and not line.startswith("URL:")
                    and not line.startswith("===")
                    and not line.startswith("Pages in category")
                    and not line.startswith("The following")
                    and not line.startswith("Retrieved")
                    and len(line) > 2
                    and len(line) < 120
                    and not line.startswith("http")
                ):
                    # Single-letter lines are section headers (A, B, C...)
                    if len(line) == 1 and line.isalpha():
                        continue
                    pages_by_category[cat_name].append(line)

        # Related links
        rels = _extract_related(content)
        if rels:
            related_links[title_lower] = rels

    all_titles.extend(sorted(page_by_title.keys()))
    _index_built = True


def lookup_page(name: str) -> tuple[Path | None, str | None]:
    """Try to find a page by exact title, filename, or case-insensitive match.

    Returns (path, matched_title) or (None, None).
    """
    build_index()
    key = name.strip().lower()

    # 1. Exact title match
    if key in page_by_title:
        return page_by_title[key], key

    # 2. Filename match (underscores as spaces)
    fname_key = key.replace("_", " ")
    if fname_key in page_by_filename:
        return page_by_filename[fname_key], fname_key

    # 3. Try with "Category " prefix
    cat_key = "category " + key
    if cat_key in page_by_filename:
        return page_by_filename[cat_key], cat_key

    return None, None


def get_category_members(category: str) -> list[str]:
    """Get all page titles in a category."""
    build_index()
    key = category.strip().lower()
    return pages_by_category.get(key, [])


def get_related(title: str) -> list[str]:
    """Get related pages for a given page title."""
    build_index()
    return related_links.get(title.strip().lower(), [])


def fuzzy_title_matches(query: str, limit: int = 10) -> list[str]:
    """Find titles containing the query as a substring."""
    build_index()
    q = query.strip().lower()
    matches = [t for t in all_titles if q in t]
    return matches[:limit]
