"""Reformat VASP wiki pages — re-extract text with better formatting.

Re-processes each .txt file: reads raw text, applies smarter formatting
that joins inline elements with spaces and separates block elements with newlines.

Usage: python reformat_pages.py
"""

import re
from pathlib import Path

PAGES_DIR = Path(__file__).parent / "pages"


def reformat_body(raw_body: str) -> str:
    """Reformat raw body text extracted with get_text(separator='\\n')."""

    lines = raw_body.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines (we'll add our own)
        if not line:
            # Preserve paragraph breaks (multiple empty lines → one blank line)
            if result and result[-1] != "":
                result.append("")
            i += 1
            continue

        # Check if this line is a standalone tag name that should be joined with next line
        # Pattern: short uppercase line (INCAR tag) followed by = or description
        if re.match(r'^[A-Z][A-Z0-9_]{1,25}$', line):
            # Look ahead to see if next non-empty line starts with = or is a value/description
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                next_line = lines[j].strip()
                # Join: TAG + = value
                if next_line.startswith("="):
                    merged = line + " " + next_line
                    # Keep consuming continuation lines
                    k = j + 1
                    while k < len(lines):
                        cont = lines[k].strip()
                        if not cont:
                            break
                        # If next line is another tag name or section header, stop
                        if re.match(r'^[A-Z][A-Z0-9_]{1,25}$', cont) and k + 1 < len(lines) and lines[k+1].strip().startswith("="):
                            break
                        if cont.startswith("# ") or cont.startswith("== "):
                            break
                        merged += " " + cont
                        k += 1
                    result.append(merged)
                    i = k
                    continue

                # Join: TAG + description (e.g., "ISMEAR" + "determines how...")
                elif next_line and next_line[0].islower():
                    result.append(line + " " + next_line)
                    i = j + 1
                    continue

                # Join: TAG + > or < (comparison)
                elif next_line.startswith(">") or next_line.startswith("<"):
                    merged = line + " " + next_line
                    k = j + 1
                    while k < len(lines) and lines[k].strip() and not re.match(r'^[A-Z][A-Z0-9_]{1,25}$', lines[k].strip()):
                        merged += " " + lines[k].strip()
                        k += 1
                    result.append(merged)
                    i = k
                    continue

        # Check for orphaned "= value" lines
        if line.startswith("= ") and result:
            # Append to previous line
            if result[-1]:
                result[-1] = result[-1] + " " + line
            else:
                result.append(line)
            i += 1
            continue

        # Check for short fragments that should be joined (like "f", "n", "k" on separate lines)
        if len(line) <= 2 and line.isalpha():
            # Likely a subscript/variable split across lines, join with previous
            if result and result[-1]:
                result[-1] = result[-1] + " " + line
            i += 1
            continue

        # Section headers (keep as-is with blank line before)
        if line.startswith("Description:") or line.startswith("Default:") or line.startswith("Tag options") or line.startswith("Mind:") or line.startswith("Tip:") or line.startswith("Related tags"):
            if result and result[-1] != "":
                result.append("")
            result.append(line)
            i += 1
            continue

        # Normal line
        result.append(line)
        i += 1

    text = "\n".join(result)

    # Post-processing cleanup

    # Fix "TAG = value" where TAG got separated: common patterns
    # e.g., "ISMEAR = 0 : Gaussian" should stay on one line
    text = re.sub(r'\n([A-Z][A-Z0-9_]+)\n(= [^\n]+)', r'\n\1 \2', text)

    # Remove [math] remnants
    text = re.sub(r'\[math\].*?\[/math\]', '', text)

    # Clean LaTeX
    for old, new in [
        ('\\mathbf', ''), ('\\mathrm', ''), ('\\text', ''),
        ('\\frac', ''), ('\\left', ''), ('\\right', ''),
        ('\\begin{pmatrix}', ''), ('\\end{pmatrix}', ''),
        ('\\displaystyle', ''), ('\\qquad', '  '), ('\\quad', ' '),
        ('\\times', '×'), ('\\cdot', '·'), ('\\sum', 'Σ'),
        ('\\int', '∫'), ('\\infty', '∞'), ('\\omega', 'ω'),
        ('\\sigma', 'σ'), ('\\epsilon', 'ε'), ('\\alpha', 'α'),
        ('\\beta', 'β'), ('\\gamma', 'γ'), ('\\delta', 'δ'),
        ('\\Delta', 'Δ'), ('\\pi', 'π'), ('\\mu', 'μ'),
        ('\\nu', 'ν'), ('\\eta', 'η'), ('\\Phi', 'Φ'),
        ('\\phi', 'φ'), ('\\chi', 'χ'), ('\\Gamma', 'Γ'),
        ('\\ge', '≥'), ('\\le', '≤'), ('\\approx', '≈'),
    ]:
        text = text.replace(old, new)

    # Remove remaining \command{...} → keep content
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)

    # Remove [N] citation refs
    text = re.sub(r'\[\d+\]', '', text)

    # Remove "Retrieved from" footer
    text = re.sub(r'\nRetrieved from\s*"[^"]*".*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\nExamples that use this tag\s*$', '', text, flags=re.DOTALL)

    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Clean multiple spaces
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def main():
    if not PAGES_DIR.exists():
        print(f"Not found: {PAGES_DIR}")
        return

    files = list(PAGES_DIR.glob("*.txt"))
    print(f"Reformatting {len(files)} pages...")

    for txt_file in files:
        try:
            content = txt_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            # Preserve header (Title, URL, separator)
            if len(lines) < 4:
                continue
            header = "\n".join(lines[:3])
            body = "\n".join(lines[3:])

            new_body = reformat_body(body)
            txt_file.write_text(header + "\n" + new_body + "\n", encoding="utf-8")
        except Exception as e:
            print(f"  Error: {txt_file.name}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
