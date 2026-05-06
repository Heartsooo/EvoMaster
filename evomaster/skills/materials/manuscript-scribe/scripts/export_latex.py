"""
Export an assembled Markdown manuscript to LaTeX (.tex) format.

Pure string conversion — no external dependencies required.

Features:
  - Heading mapping: # -> \\title, ## -> \\section, ### -> \\subsection
  - Inline formatting: **bold** -> \\textbf, *italic* -> \\textit, `code` -> \\texttt
  - Citations: [n](url) -> \\href{url}{[n]} (with hyperref)
  - Bullet lists -> itemize, numbered lists -> enumerate
  - Markdown pipe tables -> tabular
  - Math: $...$ and $$...$$ preserved as-is (LaTeX native)
  - Generates companion .bib file from References section
  - Configurable document class and packages

Usage:
  python export_latex.py --input final.md --output manuscript.tex
  python export_latex.py --input final.md --output manuscript.tex --documentclass article --bibfile refs.bib

Output: Creates a .tex file (and optionally a .bib file) at --output path.
"""

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# LaTeX escaping
# ---------------------------------------------------------------------------

# Characters that need escaping in LaTeX (order matters: & before others)
_LATEX_SPECIAL = [
    ('\\', r'\textbackslash{}'),
    ('{', r'\{'),
    ('}', r'\}'),
    ('&', r'\&'),
    ('%', r'\%'),
    ('$', r'\$'),
    ('#', r'\#'),
    ('_', r'\_'),
    ('~', r'\textasciitilde{}'),
    ('^', r'\textasciicircum{}'),
]


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text.

    Does NOT escape text inside math delimiters ($...$) or already-converted
    LaTeX commands.  Call this only on plain text segments.
    """
    for char, replacement in _LATEX_SPECIAL:
        text = text.replace(char, replacement)
    return text


def _safe_escape(text: str) -> str:
    """Escape text while preserving math ($...$, $$...$$) and LaTeX commands."""
    # Split on math delimiters, escape only non-math parts
    parts = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside math — keep as-is
            result.append(part)
        else:
            result.append(_escape_latex(part))
    return ''.join(result)


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

# Common element symbols for chemical formula detection
_ELEMENTS = {
    'H',
    'He',
    'Li',
    'Be',
    'B',
    'C',
    'N',
    'O',
    'F',
    'Ne',
    'Na',
    'Mg',
    'Al',
    'Si',
    'P',
    'S',
    'Cl',
    'Ar',
    'K',
    'Ca',
    'Sc',
    'Ti',
    'V',
    'Cr',
    'Mn',
    'Fe',
    'Co',
    'Ni',
    'Cu',
    'Zn',
    'Ga',
    'Ge',
    'As',
    'Se',
    'Br',
    'Kr',
    'Rb',
    'Sr',
    'Y',
    'Zr',
    'Nb',
    'Mo',
    'Ru',
    'Rh',
    'Pd',
    'Ag',
    'Cd',
    'In',
    'Sn',
    'Sb',
    'Te',
    'I',
    'Xe',
    'Cs',
    'Ba',
    'La',
    'Ce',
    'Pr',
    'Nd',
    'Sm',
    'Eu',
    'Gd',
    'Tb',
    'Dy',
    'Ho',
    'Er',
    'Tm',
    'Yb',
    'Lu',
    'Hf',
    'Ta',
    'W',
    'Re',
    'Os',
    'Ir',
    'Pt',
    'Au',
    'Hg',
    'Tl',
    'Pb',
    'Bi',
}


def _is_chemical_formula(text: str) -> bool:
    """Check if text looks like a chemical formula."""
    pairs = re.findall(r'([A-Z][a-z]?)(\d*)', text)
    pairs = [(e, c) for e, c in pairs if e]
    if len(pairs) < 2:
        return False
    return all(e in _ELEMENTS for e, _ in pairs)


def _chem_to_latex(formula: str) -> str:
    """Convert a chemical formula to LaTeX with subscripts: CO2 -> CO$_{2}$."""
    return re.sub(r'(\d+)', r'$_{\1}$', formula)


def _convert_inline(text: str) -> str:
    """Convert Markdown inline formatting to LaTeX.

    Handles: **bold**, *italic*, `code`, [n](url) citations, plain [n],
    _{sub} subscripts, ^{sup} superscripts, chemical formulas.
    Preserves math delimiters.
    """
    # First, protect math from inline conversion
    math_blocks: list[str] = []

    def _save_math(m: re.Match) -> str:
        math_blocks.append(m.group(0))
        return f"__MATH_{len(math_blocks) - 1}__"

    text = re.sub(r'\$\$.*?\$\$', _save_math, text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+?\$', _save_math, text)

    # Citations [n](url) -> \textsuperscript{\href{url}{[n]}}
    text = re.sub(
        r'\[(\d+)\]\(([^)]+)\)',
        lambda m: rf"\textsuperscript{{\href{{{m.group(2)}}}{{[{m.group(1)}]}}}}",
        text,
    )

    # Plain citations [n] -> superscript (skip those already inside \href{}{[n]})
    text = re.sub(
        r'(?<!\{)\[(\d+)\](?!\})',
        lambda m: rf"\textsuperscript{{[{m.group(1)}]}}",
        text,
    )

    # Subscripts _{text} -> $_{\\mathrm{text}}$ (roman subscript for descriptive labels)
    text = re.sub(
        r'_\{([^}]+)\}',
        lambda m: rf"$_{{\mathrm{{{m.group(1)}}}}}$",
        text,
    )

    # Superscripts ^{text} -> $^{\\text{text}}$
    text = re.sub(
        r'\^\{([^}]+)\}',
        lambda m: rf"$^{{{m.group(1)}}}$",
        text,
    )

    # Bold **text** -> \textbf{text}
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)

    # Italic *text* -> \textit{text}
    text = re.sub(r'\*(.+?)\*', r'\\textit{\1}', text)

    # Inline code `text` -> \texttt{text}
    text = re.sub(r'`(.+?)`', r'\\texttt{\1}', text)

    # Auto-detect chemical formulas (e.g. CO2, H2O, Fe2O3) and subscript digits
    def _maybe_chem(m: re.Match) -> str:
        candidate = m.group(0)
        if _is_chemical_formula(candidate):
            return _chem_to_latex(candidate)
        return candidate

    text = re.sub(
        r'\b[A-Z][a-z]?(?:\d+)[A-Z]?[a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*\b',
        _maybe_chem,
        text,
    )

    # Restore math
    for i, block in enumerate(math_blocks):
        text = text.replace(f"__MATH_{i}__", block)

    return text


# ---------------------------------------------------------------------------
# Block-level conversion
# ---------------------------------------------------------------------------


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 2
    )


def _is_separator_line(line: str) -> bool:
    return bool(re.match(r'^\s*\|[\s\-:|]+\|\s*$', line))


def _parse_table_row(line: str) -> list[str]:
    cells = line.strip().strip('|').split('|')
    return [c.strip() for c in cells]


def _convert_table(lines: list[str]) -> str:
    """Convert Markdown table lines to LaTeX tabular."""
    rows: list[list[str]] = []
    for line in lines:
        if not _is_separator_line(line):
            rows.append(_parse_table_row(line))
    if not rows:
        return ''

    n_cols = max(len(r) for r in rows)
    col_spec = '|'.join(['l'] * n_cols)
    col_spec = f"|{col_spec}|"

    out = [
        r'\begin{table}[htbp]',
        r'\centering',
        rf"\begin{{tabular}}{{{col_spec}}}",
        r'\hline',
    ]

    for i, row in enumerate(rows):
        cells = [_convert_inline(c) for c in row]
        # Pad if needed
        while len(cells) < n_cols:
            cells.append('')
        line_str = ' & '.join(cells) + r' \\'
        out.append(line_str)
        if i == 0:
            out.append(r'\hline')

    out.append(r'\hline')
    out.append(r'\end{tabular}')
    out.append(r'\end{table}')
    return '\n'.join(out)


def _parse_references_to_bib(ref_text: str) -> str:
    """Convert a References section to BibTeX entries (best-effort)."""
    entries = []
    for m in re.finditer(r'\[(\d+)\]\s*(.+?)(?=\n\s*\[\d+\]|\Z)', ref_text, re.DOTALL):
        n = int(m.group(1))
        line = m.group(2).strip()

        # Try to extract URL
        url_match = re.search(r'https?://[^\s\)\]\>]+', line)
        url = url_match.group(0).rstrip('.,;:)') if url_match else ''

        # Try to extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', line)
        year = year_match.group(0) if year_match else ''

        # Clean line for title (remove URL, very rough)
        _title = re.sub(r'https?://[^\s]+', '', line).strip().rstrip('.')  # noqa: F841

        entry = f"""@misc{{ref{n},
  note = {{{line}}},
  year = {{{year}}},
  url = {{{url}}},
}}"""
        entries.append(entry)

    return '\n\n'.join(entries)


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def export_markdown_to_latex(
    md_text: str,
    output_path: str | Path,
    documentclass: str = 'article',
    bibfile: str | None = None,
) -> None:
    """Convert Markdown text to a LaTeX .tex file."""
    lines = md_text.splitlines()
    title = ''
    body_lines: list[str] = []

    # Preamble packages
    packages = [
        'inputenc',  # UTF-8
        'fontenc',  # T1 fonts
        'amsmath',  # math
        'amssymb',  # math symbols
        'hyperref',  # hyperlinks
        'graphicx',  # figures
        'booktabs',  # better tables
        'geometry',  # margins
    ]

    i = 0
    in_list: str | None = None  # "itemize" or "enumerate"

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip HTML comments
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            i += 1
            continue

        # Title (# Heading)
        if stripped.startswith('# ') and not stripped.startswith('## '):
            title = stripped[2:].strip()
            i += 1
            continue

        # Section (## Heading)
        if stripped.startswith('## '):
            if in_list:
                body_lines.append(f"\\end{{{in_list}}}")
                in_list = None
            sec_name = stripped[3:].strip()
            body_lines.append(f"\\section{{{sec_name}}}")
            i += 1
            continue

        # Subsection (### Heading)
        if stripped.startswith('### '):
            if in_list:
                body_lines.append(f"\\end{{{in_list}}}")
                in_list = None
            subsec_name = stripped[4:].strip()
            body_lines.append(f"\\subsection{{{subsec_name}}}")
            i += 1
            continue

        # Table
        if _is_table_line(stripped):
            if in_list:
                body_lines.append(f"\\end{{{in_list}}}")
                in_list = None
            table_lines: list[str] = []
            while i < len(lines) and _is_table_line(lines[i].strip()):
                table_lines.append(lines[i])
                i += 1
            body_lines.append(_convert_table(table_lines))
            continue

        # Bullet list
        if re.match(r'^\s*[-*]\s+', stripped):
            item_text = re.sub(r'^\s*[-*]\s+', '', stripped)
            if in_list != 'itemize':
                if in_list:
                    body_lines.append(f"\\end{{{in_list}}}")
                body_lines.append('\\begin{itemize}')
                in_list = 'itemize'
            body_lines.append(f"  \\item {_convert_inline(item_text)}")
            i += 1
            continue

        # Numbered list
        if re.match(r'^\s*\d+\.\s+', stripped):
            item_text = re.sub(r'^\s*\d+\.\s+', '', stripped)
            if in_list != 'enumerate':
                if in_list:
                    body_lines.append(f"\\end{{{in_list}}}")
                body_lines.append('\\begin{enumerate}')
                in_list = 'enumerate'
            body_lines.append(f"  \\item {_convert_inline(item_text)}")
            i += 1
            continue

        # Empty line -> close list if open, add blank
        if not stripped:
            if in_list:
                body_lines.append(f"\\end{{{in_list}}}")
                in_list = None
            body_lines.append('')
            i += 1
            continue

        # Figure placeholder
        if stripped.lower().startswith('figure ') and '.' in stripped:
            if in_list:
                body_lines.append(f"\\end{{{in_list}}}")
                in_list = None
            body_lines.append('\\begin{figure}[htbp]')
            body_lines.append('  \\centering')
            body_lines.append(
                '  % \\includegraphics[width=0.8\\textwidth]{figure_file}'
            )
            body_lines.append(f"  \\caption{{{_convert_inline(stripped)}}}")
            body_lines.append('\\end{figure}')
            i += 1
            continue

        # Regular paragraph
        if in_list:
            body_lines.append(f"\\end{{{in_list}}}")
            in_list = None

        # Collect continuation lines for paragraph
        para_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line:
                break
            if next_line.startswith('#') or _is_table_line(next_line):
                break
            if re.match(r'^\s*[-*]\s+', next_line) or re.match(
                r'^\s*\d+\.\s+', next_line
            ):
                break
            if next_line.startswith('<!--'):
                break
            # Don't merge reference entries into one paragraph
            if re.match(r'^\[\d+\]', next_line):
                break
            para_lines.append(next_line)
            i += 1

        full_para = ' '.join(para_lines)
        body_lines.append(_convert_inline(full_para))
        body_lines.append('')

    # Close any open list
    if in_list:
        body_lines.append(f"\\end{{{in_list}}}")

    # Build the .tex document
    tex_lines = [
        f"\\documentclass{{{documentclass}}}",
        '',
    ]
    for pkg in packages:
        if pkg == 'geometry':
            tex_lines.append('\\usepackage[margin=2.54cm]{geometry}')
        elif pkg == 'inputenc':
            tex_lines.append('\\usepackage[utf8]{inputenc}')
        elif pkg == 'fontenc':
            tex_lines.append('\\usepackage[T1]{fontenc}')
        elif pkg == 'hyperref':
            tex_lines.append(
                '\\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue]{hyperref}'
            )
        else:
            tex_lines.append(f"\\usepackage{{{pkg}}}")

    tex_lines.append('')

    if title:
        tex_lines.append(f"\\title{{{title}}}")
        tex_lines.append('\\author{}')
        tex_lines.append('\\date{}')
        tex_lines.append('')

    tex_lines.append('\\begin{document}')
    if title:
        tex_lines.append('\\maketitle')
    tex_lines.append('')
    tex_lines.extend(body_lines)
    tex_lines.append('')
    tex_lines.append('\\end{document}')

    # Write .tex
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(tex_lines), encoding='utf-8')
    print(f"LaTeX document exported to {output_path}.")

    # Optionally write .bib
    if bibfile:
        # Extract references section from md
        ref_match = re.search(
            r'\n##\s+References\s*\n(.*)', md_text, re.IGNORECASE | re.DOTALL
        )
        if ref_match:
            bib_content = _parse_references_to_bib(ref_match.group(1))
            bib_path = output_path.parent / bibfile
            bib_path.write_text(bib_content, encoding='utf-8')
            print(f"BibTeX file exported to {bib_path}.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Export assembled Markdown manuscript to LaTeX (.tex) format.'
    )
    ap.add_argument('--input', required=True, help='Path to assembled Markdown file')
    ap.add_argument('--output', required=True, help='Path to output .tex file')
    ap.add_argument(
        '--documentclass',
        default='article',
        help='LaTeX document class (default: article)',
    )
    ap.add_argument(
        '--bibfile',
        default=None,
        help='Generate a .bib file with this name from the References section',
    )
    args = ap.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    md_text = input_path.read_text(encoding='utf-8')
    export_markdown_to_latex(md_text, args.output, args.documentclass, args.bibfile)


if __name__ == '__main__':
    main()
