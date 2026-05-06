"""Clean VASP wiki pages — remove MediaWiki rendering artifacts.

Processes all .txt files in vasp_wiki/pages/, producing cleaner text
that's more useful for LLM consumption.

Usage: python clean_pages.py
"""

import re
from pathlib import Path

PAGES_DIR = Path(__file__).parent / "pages"


def clean_content(text: str) -> str:
    """Clean wiki page content."""
    lines = text.split("\n")
    if len(lines) < 4:
        return text

    # Keep header (Title + URL + separator)
    header = "\n".join(lines[:3])
    body = "\n".join(lines[3:])

    # Remove [math]\displaystyle{ ... }[/math] → keep inner content simplified
    body = re.sub(r'\[math\]\\displaystyle\{\s*', '', body)
    body = re.sub(r'\s*\}\[/math\]', '', body)
    body = re.sub(r'\[math\].*?\[/math\]', '', body)

    # Remove wiki citation refs like [1], [2]
    body = re.sub(r'\[\d+\]', '', body)

    # Remove "Retrieved from" footer
    body = re.sub(r'Retrieved from\s*"[^"]*".*$', '', body, flags=re.DOTALL)

    # Remove "Examples that use this tag" trailing section (usually empty)
    body = re.sub(r'\nExamples that use this tag\s*$', '', body, flags=re.DOTALL)

    # Collapse repeated blank lines (3+ → 2)
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Remove lines that are just a single INCAR tag name repeated (rendering artifact)
    # e.g. standalone "ISMEAR" or "ALGO" lines that are just link text
    # We keep them if they're part of tag=value or have other content
    tag_pattern = re.compile(r'^([A-Z][A-Z0-9_]{1,25})$')
    cleaned_lines = []
    prev_was_tag = False
    for line in body.split("\n"):
        stripped = line.strip()
        if tag_pattern.match(stripped):
            # Skip if previous line was also a bare tag (dedup)
            if prev_was_tag:
                continue
            prev_was_tag = True
        else:
            prev_was_tag = False
        cleaned_lines.append(line)

    body = "\n".join(cleaned_lines)

    # Clean up LaTeX remnants
    body = body.replace('\\mathbf', '')
    body = body.replace('\\mathrm', '')
    body = body.replace('\\text', '')
    body = body.replace('\\frac', '')
    body = body.replace('\\left', '')
    body = body.replace('\\right', '')
    body = body.replace('\\begin{pmatrix}', '')
    body = body.replace('\\end{pmatrix}', '')
    body = body.replace('\\qquad', '  ')
    body = body.replace('\\quad', ' ')
    body = body.replace('\\times', '×')
    body = body.replace('\\cdot', '·')
    body = body.replace('\\sum', 'Σ')
    body = body.replace('\\int', '∫')
    body = body.replace('\\infty', '∞')
    body = body.replace('\\omega', 'ω')
    body = body.replace('\\sigma', 'σ')
    body = body.replace('\\epsilon', 'ε')
    body = body.replace('\\alpha', 'α')
    body = body.replace('\\beta', 'β')
    body = body.replace('\\gamma', 'γ')
    body = body.replace('\\delta', 'δ')
    body = body.replace('\\Delta', 'Δ')
    body = body.replace('\\pi', 'π')
    body = body.replace('\\mu', 'μ')
    body = body.replace('\\nu', 'ν')
    body = body.replace('\\eta', 'η')
    body = body.replace('\\Phi', 'Φ')
    body = body.replace('\\phi', 'φ')
    body = body.replace('\\chi', 'χ')
    body = body.replace('\\Gamma', 'Γ')
    body = body.replace('\\ge', '≥')
    body = body.replace('\\le', '≤')
    body = body.replace('\\approx', '≈')
    body = body.replace('\\neq', '≠')

    # Remove remaining backslash-commands
    body = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', body)
    body = re.sub(r'\\[a-zA-Z]+', '', body)

    # Clean up extra spaces
    body = re.sub(r'  +', ' ', body)
    body = re.sub(r'\n {2,}', '\n', body)

    # Final collapse of blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    return header + "\n" + body.strip()


def main():
    if not PAGES_DIR.exists():
        print(f"Pages directory not found: {PAGES_DIR}")
        return

    files = list(PAGES_DIR.glob("*.txt"))
    print(f"Cleaning {len(files)} pages...")

    for txt_file in files:
        try:
            content = txt_file.read_text(encoding="utf-8", errors="ignore")
            cleaned = clean_content(content)
            txt_file.write_text(cleaned, encoding="utf-8")
        except Exception as e:
            print(f"  Error cleaning {txt_file.name}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
