"""
VASP Wiki Crawler - 爬取 https://vasp.at/wiki/ 所有页面的文字内容
用法: python crawl.py
输出: vasp_wiki/pages/ 目录下的 .txt 文件
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import time
import os
import re
import json

BASE_URL = "https://vasp.at/wiki/"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "pages")
INDEX_FILE = os.path.join(os.path.dirname(__file__), "index.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

visited = set()
results = []
failed = []


def url_to_filename(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path or path == "wiki":
        return "index"
    path = path.removeprefix("wiki/")
    path = unquote(path)
    path = re.sub(r'[^\w\-.]', '_', path)
    return path or "index"


def extract_text(soup: BeautifulSoup) -> str:
    # 移除 script, style, nav 等无关元素
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # 尝试找主要内容区域 (MediaWiki 常见结构)
    content = (
        soup.find("div", {"id": "mw-content-text"})
        or soup.find("div", {"id": "content"})
        or soup.find("div", {"id": "bodyContent"})
        or soup.find("main")
        or soup.body
    )
    if not content:
        return ""
    return content.get_text(separator="\n", strip=True)


def get_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1", {"id": "firstHeading"}) or soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    title = soup.find("title")
    return title.get_text(strip=True) if title else ""


def crawl(url: str):
    # 规范化 URL
    url = url.split("#")[0].rstrip("/")
    if url in visited:
        return
    if not url.startswith(BASE_URL):
        return
    # 跳过特殊页面
    skip_prefixes = [
        "Special:", "Talk:", "User:", "User_talk:",
        "File:", "MediaWiki:", "Template:", "Help:",
        "Category_talk:", "Template_talk:",
    ]
    path = unquote(urlparse(url).path)
    for prefix in skip_prefixes:
        if prefix in path:
            return
    # 跳过操作页面
    if any(p in url for p in ["action=edit", "action=history", "oldid=", "printable=yes"]):
        return

    visited.add(url)

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
        results.append({"url": url, "title": title, "chars": len(text)})
        fname = url_to_filename(url)
        fpath = os.path.join(OUTPUT_DIR, f"{fname}.txt")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(f"Title: {title}\nURL: {url}\n{'=' * 60}\n\n{text}")
        print(f"[{len(results):4d}] {title or url} ({len(text)} chars)")

    # 提取页面中的链接继续爬取
    for a in soup.find_all("a", href=True):
        next_url = urljoin(url, a["href"]).split("#")[0].rstrip("/")
        if next_url not in visited and next_url.startswith(BASE_URL):
            crawl(next_url)

    time.sleep(0.3)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Starting crawl from {BASE_URL}")
    print(f"Output: {OUTPUT_DIR}\n")

    # 先尝试从 "All pages" 获取完整页面列表
    all_pages_url = BASE_URL + "index.php?title=Special:AllPages"
    try:
        resp = requests.get(all_pages_url, headers=HEADERS, timeout=15)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(BASE_URL, a["href"]).split("#")[0].rstrip("/")
                if link.startswith(BASE_URL) and link not in visited:
                    crawl(link)
    except Exception:
        pass

    # 从首页开始爬（会补充上面没覆盖到的）
    crawl(BASE_URL)

    # 保存索引
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
    import sys
    sys.setrecursionlimit(10000)
    main()
