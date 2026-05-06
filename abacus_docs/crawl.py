"""
ABACUS Documentation Crawler
Crawls http://abacus.deepmodeling.com/en/latest/ (Sphinx docs)

Usage: python crawl.py
Output: abacus_docs/pages/ directory with .txt files
"""

import re
import time
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://abacus.deepmodeling.com/en/latest/"
OUTPUT_DIR = Path(__file__).parent / "pages"
INDEX_FILE = Path(__file__).parent / "index.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}

visited = set()
results = []
failed = []


def url_to_filename(url: str) -> str:
    path = urlparse(url).path.strip("/")
    path = path.removeprefix("en/latest/")
    path = unquote(path)
    path = path.replace(".html", "").replace("/", "__")
    path = re.sub(r'[^\w\-.]', '_', path)
    return path or "index"


def extract_text(soup: BeautifulSoup) -> str:
    """Extract main content from Sphinx page with better formatting."""
    # Remove navigation, footer, sidebar
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    for cls in ["sphinxsidebar", "related", "footer", "headerlink"]:
        for el in soup.find_all(class_=cls):
            el.decompose()
    for cls in ["sphinxsidebarwrapper"]:
        for el in soup.find_all(id=cls):
            el.decompose()

    # Find main content area (Sphinx uses div.body or div.document)
    content = (
        soup.find("div", class_="body")
        or soup.find("div", {"role": "main"})
        or soup.find("div", class_="document")
        or soup.find("main")
        or soup.body
    )
    if not content:
        return ""

    # Better text extraction: preserve block structure
    lines = []
    for element in content.descendants:
        if element.name in ("h1", "h2", "h3", "h4"):
            text = element.get_text(strip=True)
            if text:
                level = int(element.name[1])
                prefix = "#" * level
                lines.append(f"\n{prefix} {text}\n")
        elif element.name == "p":
            text = element.get_text(separator=" ", strip=True)
            if text:
                lines.append(text)
                lines.append("")
        elif element.name == "li":
            text = element.get_text(separator=" ", strip=True)
            if text:
                lines.append(f"  - {text}")
        elif element.name == "pre":
            # Code blocks — preserve as-is
            text = element.get_text()
            if text:
                lines.append(f"```\n{text.strip()}\n```")
                lines.append("")
        elif element.name == "dt":
            text = element.get_text(separator=" ", strip=True)
            if text:
                lines.append(f"\n**{text}**")
        elif element.name == "dd":
            text = element.get_text(separator=" ", strip=True)
            if text:
                lines.append(f"  {text}")
        elif element.name in ("table",):
            # Simple table extraction
            rows = element.find_all("tr")
            for row in rows:
                cells = [c.get_text(separator=" ", strip=True) for c in row.find_all(["th", "td"])]
                if any(cells):
                    lines.append(" | ".join(cells))
            lines.append("")

    # Deduplicate consecutive identical lines and clean up
    cleaned = []
    prev = None
    for line in lines:
        if line != prev or line == "":
            cleaned.append(line)
        prev = line

    text = "\n".join(cleaned)
    # Collapse 3+ blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        # Remove ¶ headerlink
        for a in h1.find_all("a", class_="headerlink"):
            a.decompose()
        return h1.get_text(strip=True)
    title = soup.find("title")
    return title.get_text(strip=True) if title else ""


def crawl(url: str):
    url = url.split("#")[0]
    # Normalize: strip trailing slash for dedup, but keep BASE_URL matching flexible
    url_clean = url.rstrip("/")
    if url_clean in visited:
        return
    base_clean = BASE_URL.rstrip("/")
    if not url_clean.startswith(base_clean):
        return
    visited.add(url_clean)
    # Skip non-html
    path = urlparse(url).path
    if path and not path.endswith("/") and not path.endswith(".html"):
        return

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  FAIL: {url} - {e}")
        failed.append({"url": url, "error": str(e)})
        return

    if "text/html" not in resp.headers.get("Content-Type", ""):
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    title = get_title(soup)
    text = extract_text(soup)

    if text.strip():
        fname = url_to_filename(url)
        fpath = OUTPUT_DIR / f"{fname}.txt"

        # Avoid duplicate content for same file
        if not fpath.exists():
            fpath.write_text(
                f"Title: {title}\nURL: {url}\n{'='*60}\n\n{text}",
                encoding="utf-8",
            )
            results.append({"url": url, "title": title, "file": fname, "chars": len(text)})
            print(f"[{len(results):4d}] {title} ({len(text)} chars)")

    # Follow links
    for a in soup.find_all("a", href=True):
        next_url = urljoin(url, a["href"]).split("#")[0]
        next_clean = next_url.rstrip("/")
        if next_clean not in visited and next_clean.startswith(base_clean):
            crawl(next_url)

    time.sleep(0.2)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Starting crawl from {BASE_URL}")
    print(f"Output: {OUTPUT_DIR}\n")

    import sys
    sys.setrecursionlimit(5000)

    crawl(BASE_URL)

    # Save index
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_pages": len(results),
            "total_failed": len(failed),
            "pages": results,
            "failed": failed,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(results)} pages saved to {OUTPUT_DIR}")
    if failed:
        print(f"{len(failed)} pages failed (see {INDEX_FILE})")


if __name__ == "__main__":
    main()
