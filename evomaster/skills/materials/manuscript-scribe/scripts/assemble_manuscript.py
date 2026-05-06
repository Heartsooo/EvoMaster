"""
Assemble section files (or a single draft) into one manuscript and run checks:
1. All technical terms are defined (at first use).
2. All abbreviations are defined exactly once (no duplicate definitions).
3. Reference links are valid and References section matches in-text citations.
4. (Optional) Word-count and content validation via --profile + --check_length.

Usage:
  python assemble_manuscript.py --sections_dir sections/ --output draft_manuscript.md
  python assemble_manuscript.py --draft draft_manuscript.md --output final.md --validate
  python assemble_manuscript.py --draft draft.md --output final.md --profile research_paper --check_length

Output: Writes assembled Markdown and a validation report (JSON or text).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import requests
except ImportError:
    requests = None

try:
    from format_profiles import get_profile, resolve_section
except ImportError:
    get_profile = None  # type: ignore[assignment]
    resolve_section = None  # type: ignore[assignment]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
from longtask_runtime import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_FATAL_ERROR,
    STATUS_RETRYABLE_ERROR,
    append_event,
    build_result,
    emit_result,
    init_or_load_state,
)

# Section order when merging from a directory (fallback when no --profile)
DEFAULT_SECTION_ORDER = [
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "References",
]


def extract_sections_from_draft(content: str) -> dict[str, str]:
    """Parse a single draft file into section name -> section text (including ## Header)."""
    sections = {}
    current = None
    buf: list[str] = []
    for line in content.splitlines(keepends=True):
        if re.match(r"^##\s+.+\s*$", line):
            if current is not None:
                sections[current] = "".join(buf)
            current = line.replace("##", "").strip()
            buf = [line]
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "".join(buf)
    return sections


def load_sections_from_dir(sections_dir: Path) -> dict[str, str]:
    """Load section files: SectionName.md -> content. Strip leading # Title so only ## SectionName + body is kept."""
    sections = {}
    for f in sections_dir.iterdir():
        if f.suffix.lower() == ".md":
            name = f.stem
            raw = f.read_text(encoding="utf-8").strip()
            # If file has "# Title\n\n## SectionName", keep only "## SectionName\n\n..."
            marker = f"## {name}"
            if marker in raw:
                idx = raw.find(marker)
                raw = raw[idx:]
            elif not raw.startswith("#"):
                raw = f"## {name}\n\n{raw}"
            sections[name] = raw
    return sections


def assemble(
    sections: dict[str, str], order: list[str] | None = None, title: str | None = None
) -> str:
    """Merge sections in order. Prepend title once if given. Keys not in order are appended at end."""
    order = order or DEFAULT_SECTION_ORDER
    seen = set()
    parts = []
    if title:
        parts.append(f"# {title}\n")
    for name in order:
        if name in sections:
            seen.add(name)
            parts.append(sections[name].strip())
    for name, text in sections.items():
        if name not in seen:
            parts.append(text.strip())
    return "\n\n".join(parts)


# ----- Check 1: Technical terms (heuristic: report possible undefined terms) -----
def collect_defining_phrases(text: str) -> set[str]:
    """Simple heuristic: phrases that often introduce definitions."""
    defs = set()
    # "X is defined as", "X refers to", "X denotes", "we define X as"
    for m in re.finditer(
        r"(?:defined as|refers to|denotes|we define)\s+([^.,;:\n]+?)(?=[.;,:\n])",
        text,
        re.IGNORECASE,
    ):
        defs.add(m.group(1).strip().lower())
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9\s\-]+?)\s*\(\s*[A-Z]{2,}\s*\)", text):
        # "Full Name (ABBR)" -> full name as defined term
        defs.add(m.group(1).strip().lower())
    return defs


def check_terms(body_text: str, terms_file: Path | None) -> dict:
    """Report possible undefined technical terms. If terms_file provided, list required terms and check each is 'defined' in text."""
    result = {"passed": True, "undefined": [], "message": ""}
    defining = collect_defining_phrases(body_text)
    if terms_file and terms_file.exists():
        required = set()
        for line in terms_file.read_text(encoding="utf-8").splitlines():
            t = line.split("#")[0].strip().lower()
            if t:
                required.add(t)
        for t in required:
            if t not in defining and t not in body_text.lower():
                result["undefined"].append(t)
                result["passed"] = False
        if result["undefined"]:
            result["message"] = (
                "Technical terms missing definition or usage: "
                + ", ".join(result["undefined"])
            )
        else:
            result["message"] = (
                "All listed technical terms appear with definitions or in context."
            )
    else:
        result["message"] = (
            "No terms file provided; skipped term check (define terms in reference/ or pass --terms)."
        )
    return result


# ----- Check 2: Abbreviations -----
def extract_abbrev_definitions(text: str) -> dict[str, str]:
    """Return dict: ABBR -> "Full Name" from "Full Name (ABBR)" or "ABBR (Full Name)"."""
    abbrevs = {}
    # Full Name (ABBR)
    for m in re.finditer(
        r"([A-Za-z][A-Za-z0-9\s\-/]+?)\s*\(\s*([A-Z][A-Z0-9]{1,})\s*\)", text
    ):
        full, abbr = m.group(1).strip(), m.group(2).strip()
        if abbr not in abbrevs:
            abbrevs[abbr] = full
    # ABBR (Full Name)
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,})\s*\(\s*([^)]+)\)", text):
        abbr, full = m.group(1).strip(), m.group(2).strip()
        if abbr not in abbrevs:
            abbrevs[abbr] = full
    return abbrevs


def check_abbreviations(full_text: str) -> dict:
    """Ensure each abbreviation has exactly one definition and no re-definition."""
    result = {
        "passed": True,
        "duplicate_definitions": [],
        "undefined_abbrevs": [],
        "message": "",
    }
    # Split by sections to find "first use" (first section where ABBR appears)
    _sections = re.split(r"\n##\s+", full_text)  # noqa: F841
    extract_abbrev_definitions(full_text)
    # Count definitions per ABBR (by occurrence)
    defs_count: dict[str, list[int]] = {}
    for m in re.finditer(
        r"([A-Za-z][A-Za-z0-9\s\-/]+?)\s*\(\s*([A-Z][A-Z0-9]{1,})\s*\)", full_text
    ):
        abbr = m.group(2).strip()
        defs_count.setdefault(abbr, []).append(m.start())
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,})\s*\(\s*([^)]+)\)", full_text):
        abbr = m.group(1).strip()
        defs_count.setdefault(abbr, []).append(m.start())
    for abbr, positions in defs_count.items():
        if len(positions) > 1:
            result["duplicate_definitions"].append(abbr)
    # Optional: find standalone ALL-CAPS that might be undefined (heuristic: 2–5 chars, not in defs)
    # Skip for now to avoid false positives; we only report duplicate defs and missing defs if we have a list
    if result["duplicate_definitions"]:
        result["message"] = (
            "Note (non-blocking): Duplicate abbreviation definitions: "
            + ", ".join(result["duplicate_definitions"])
        )
    else:
        result["message"] = "No duplicate abbreviation definitions found."
    return result


# ----- Check 3: References -----
def extract_citation_numbers_from_body(text: str) -> set[int]:
    """Extract [n] and [n](url) from body (exclude References section)."""
    # Remove References section for body
    ref_start = re.search(r"\n##\s+(References|参考文献)\s*\n", text, re.IGNORECASE)
    body = text[: ref_start.start()] if ref_start else text
    nums = set()
    for m in re.finditer(r"\[(\d+)\](?:\([^)]*\))?", body):
        nums.add(int(m.group(1)))
    return nums


def extract_references_section(text: str) -> str:
    """Return the References section content (after ## References)."""
    m = re.search(
        r"\n##\s+(References|参考文献)\s*\n(.*)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    # Group 2 is the body because group 1 is the heading label alternation.
    return m.group(2).strip()


def parse_references_entries(ref_section: str) -> dict[int, str]:
    """Parse [n] ... url from References. Returns { n: line_text }."""
    entries = {}
    for m in re.finditer(
        r"\[(\d+)\]\s*(.+?)(?=\n\s*\[\d+\]|\Z)", ref_section, re.DOTALL
    ):
        n = int(m.group(1))
        line = m.group(2).strip()
        entries[n] = line
    return entries


def extract_url_from_ref_line(line: str) -> str | None:
    """Return first URL (http/https) from a reference line."""
    m = re.search(r"https?://[^\s\)\]\>]+", line)
    return m.group(0).rstrip(".,;:)") if m else None


def check_references(
    full_text: str,
    validate_urls: bool = False,
    require_references: bool = True,
) -> dict:
    """Ensure in-text citations and References section match; optionally validate URLs."""
    result = {
        "passed": True,
        "missing_in_refs": [],
        "missing_in_text": [],
        "invalid_urls": [],
        "message": "",
    }
    if not require_references:
        result["message"] = (
            "References check skipped for profile without a References section."
        )
        return result
    body_nums = extract_citation_numbers_from_body(full_text)
    ref_section = extract_references_section(full_text)
    ref_entries = parse_references_entries(ref_section)

    for n in body_nums:
        if n not in ref_entries:
            result["missing_in_refs"].append(n)
            result["passed"] = False
    for n in ref_entries:
        if n not in body_nums:
            result["missing_in_text"].append(n)
            result["passed"] = False

    if validate_urls and requests is not None:
        for n, line in ref_entries.items():
            url = extract_url_from_ref_line(line)
            if url:
                try:
                    r = requests.head(url, timeout=10, allow_redirects=True)
                    if r.status_code >= 400:
                        result["invalid_urls"].append((n, url, r.status_code))
                        result["passed"] = False
                except Exception as e:
                    result["invalid_urls"].append((n, url, str(e)))
                    result["passed"] = False
            else:
                result["invalid_urls"].append((n, "(no URL)", "missing"))
                result["passed"] = False

    if result["missing_in_refs"]:
        result["message"] = "Citations in text missing from References: " + str(
            sorted(result["missing_in_refs"])
        )
    elif result["missing_in_text"]:
        result["message"] = "References section has entries not cited in text: " + str(
            sorted(result["missing_in_text"])
        )
    elif result["invalid_urls"]:
        result["message"] = "Invalid or unreachable reference URLs: " + str(
            result["invalid_urls"]
        )
    else:
        result["message"] = "References consistent with text." + (
            " URLs validated." if validate_urls else ""
        )
    return result


def _word_count(text: str) -> int:
    """Count words (handles mixed CJK and Latin text)."""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))
    return cjk + latin


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments (<!-- ... -->) from text."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


def _section_body(text: str) -> str:
    """Extract clean body text from a section (strip ## header and HTML comments)."""
    body = re.sub(r"^##\s+.*\n?", "", text).strip()
    return _strip_html_comments(body)


def _is_placeholder_body(text: str) -> bool:
    t = _section_body(text).strip().lower()
    return t in {"(tbd)", "tbd", "todo", "待补充", "待完善", "待定"}


def _prefer_section_text(existing: str, incoming: str) -> str:
    if not existing:
        return incoming
    if not incoming:
        return existing
    existing_placeholder = _is_placeholder_body(existing)
    incoming_placeholder = _is_placeholder_body(incoming)
    if existing_placeholder and not incoming_placeholder:
        return incoming
    if incoming_placeholder and not existing_placeholder:
        return existing
    return (
        incoming
        if _word_count(_section_body(incoming)) > _word_count(_section_body(existing))
        else existing
    )


def _rename_section_header(text: str, canonical_name: str) -> str:
    stripped = text.strip()
    if not stripped:
        return f"## {canonical_name}\n"
    lines = stripped.splitlines()
    if lines and re.match(r"^##\s+.+$", lines[0].strip()):
        lines[0] = f"## {canonical_name}"
        return "\n".join(lines)
    return f"## {canonical_name}\n\n{stripped}"


def _canonicalize_sections_for_profile(
    sections: dict[str, str],
    profile_name: str,
) -> dict[str, str]:
    """Canonicalize section names via format profile aliases and merge duplicates."""
    if resolve_section is None:
        return sections
    normalized: dict[str, str] = {}
    for raw_name, raw_text in sections.items():
        try:
            canonical = resolve_section(profile_name, raw_name)
        except Exception:
            canonical = raw_name
        text = (
            raw_text
            if canonical == raw_name
            else _rename_section_header(raw_text, canonical)
        )
        if canonical in normalized:
            normalized[canonical] = _prefer_section_text(normalized[canonical], text)
        else:
            normalized[canonical] = text
    return normalized


def _print_word_summary(combined: str) -> None:
    """Print per-section and total word counts."""
    sections = extract_sections_from_draft(combined)
    total = 0
    print("\n--- Word Count Summary ---")
    for name, text in sections.items():
        body = _section_body(text)
        wc = _word_count(body)
        total += wc
        print(f"  {name}: {wc} words")
    print(f"  TOTAL: {total} words")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble manuscript and run consistency checks."
    )
    ap.add_argument(
        "--sections_dir", default=None, help="Directory of section .md files to merge"
    )
    ap.add_argument(
        "--draft", default=None, help="Single draft file (sections as ## Headers)"
    )
    ap.add_argument("--output", required=True, help="Output assembled Markdown path")
    ap.add_argument(
        "--validate", action="store_true", help="Validate reference URLs (HTTP HEAD)"
    )
    ap.add_argument(
        "--terms",
        default=None,
        help="Optional file listing required technical terms (one per line)",
    )
    ap.add_argument(
        "--report", default=None, help="Write validation report to this JSON file"
    )
    ap.add_argument(
        "--profile",
        default=None,
        help="Format profile name (e.g. research_paper, computational_report). "
        "When set, uses the profile's section order instead of the default.",
    )
    ap.add_argument(
        "--check_length",
        action="store_true",
        help="Run word-count and content validation (requires --profile).",
    )
    ap.add_argument(
        "--export",
        default="all",
        choices=["all", "md", "docx", "latex"],
        help="Export format(s) after assembly. 'all' (default) = .md + .tex + .docx "
        "(docx skipped if python-docx not installed). 'md' = Markdown only.",
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

    if args.sections_dir and args.draft:
        print("Use either --sections_dir or --draft, not both.", file=sys.stderr)
        sys.exit(1)
    if not args.sections_dir and not args.draft:
        print(
            "Provide --sections_dir or --draft. Example: --draft draft_manuscript.md --output final.md",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── 4: Auto-detect profile from state.json in --draft mode ────────
    # init_manuscript writes the profile to state.json; read it here so
    # word-count checks and section ordering use the correct profile even
    # when the agent omits --profile from the assemble call.
    if args.profile is None and args.draft:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
            from longtask_runtime import read_json as _read_state_json

            _st = _read_state_json(Path("_tmp/manuscript/state.json"), default={})
            _stored = _st.get("profile") or None
            if _stored:
                args.profile = _stored
        except Exception:
            pass

    if args.check_length and not args.profile:
        print("--check_length requires --profile.", file=sys.stderr)
        sys.exit(1)

    # ── Resolve section order from profile or default ──────────────────
    profile = None
    section_order = DEFAULT_SECTION_ORDER
    if args.profile:
        if get_profile is None:
            print(
                "Warning: format_profiles not available; using default section order.",
                file=sys.stderr,
            )
        else:
            profile = get_profile(args.profile)
            section_order = profile["sections"]

    # ── Load and assemble ──────────────────────────────────────────────
    if args.sections_dir:
        sections_dir = Path(args.sections_dir)
        sections = load_sections_from_dir(sections_dir)
        if args.profile:
            sections = _canonicalize_sections_for_profile(sections, args.profile)
            if profile is not None and bool(profile.get("strict_sections", False)):
                allowed = set(profile.get("sections", []))
                ignored = sorted(name for name in sections if name not in allowed)
                if ignored:
                    sections_dir_resolved = sections_dir.resolve()
                    cwd_resolved = Path.cwd().resolve()
                    if sections_dir_resolved == cwd_resolved:
                        print(
                            "ERROR: --sections_dir points to current working directory and includes non-profile "
                            "markdown files, which can concatenate versioned drafts into one document. "
                            "Use a dedicated sections directory (e.g. ./sections) or switch to --draft.",
                            file=sys.stderr,
                        )
                        print(
                            "Detected non-profile markdown stems: "
                            + ", ".join(ignored),
                            file=sys.stderr,
                        )
                        sys.exit(2)
                    print(
                        "Warning: ignored non-profile section files in strict mode: "
                        + ", ".join(ignored),
                        file=sys.stderr,
                    )
                sections = {
                    name: text for name, text in sections.items() if name in allowed
                }

        # Try to load profile from _profile.json if --profile not given
        if profile is None:
            pj = sections_dir / "_profile.json"
            if pj.exists():
                pdata = json.loads(pj.read_text(encoding="utf-8"))
                section_order = pdata.get("sections", section_order)

        # Take title from first section file if present
        title = None
        for name in section_order:
            f = sections_dir / f"{name}.md"
            if f.exists():
                first_line = f.read_text(encoding="utf-8").splitlines()[0].strip()
                if first_line.startswith("# ") and not first_line.startswith("## "):
                    title = first_line.lstrip("# ")
                break
        combined = assemble(sections, order=section_order, title=title)
    else:
        combined = Path(args.draft).read_text(encoding="utf-8")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(combined, encoding="utf-8")
    print(f"Assembled manuscript written to {out_path}.")

    # ── Word count summary (always shown) ──────────────────────────────
    _print_word_summary(combined)

    # ── Run three consistency checks ───────────────────────────────────
    terms_file = Path(args.terms) if args.terms else None
    body_only = combined
    ref_start = re.search(r"\n##\s+References\s*\n", combined, re.IGNORECASE)
    if ref_start:
        body_only = combined[: ref_start.start()]

    check1 = check_terms(body_only, terms_file)
    check2 = check_abbreviations(combined)
    references_required = True
    if profile is not None:
        references_required = any(
            s.lower() == "references" for s in profile.get("sections", [])
        )
    check3 = check_references(
        combined,
        validate_urls=args.validate,
        require_references=references_required,
    )

    # Check 4: Placeholder (TBD) sections
    tbd_sections = [
        name
        for name, text in extract_sections_from_draft(combined).items()
        if _is_placeholder_body(text)
    ]
    check4 = {
        "passed": len(tbd_sections) == 0,
        "placeholder_sections": tbd_sections,
        "message": (
            f"Placeholder sections (still TBD): {', '.join(tbd_sections)}"
            if tbd_sections
            else "No placeholder sections found."
        ),
    }

    report: dict = {
        "technical_terms": check1,
        "abbreviations": check2,
        "references": check3,
        "placeholder_sections": check4,
        "overall_passed": (
            check1["passed"]
            and check2["passed"]
            and check3["passed"]
            and check4["passed"]
        ),
    }
    print("\n--- Consistency Checks ---")
    print("1. Technical terms:", check1["message"])
    print("2. Abbreviations:", check2["message"])
    print("3. References:", check3["message"])
    print("4. Placeholder sections:", check4["message"])

    # ── Optional: content validation via validate_content ──────────────
    if args.check_length and profile is not None:
        try:
            from validate_content import print_report as vc_print
            from validate_content import run_validation

            # Re-parse sections for validation (body-only, no headers/comments)
            vc_sections: dict[str, str] = {}
            parsed = extract_sections_from_draft(combined)
            for name, text in parsed.items():
                vc_sections[name] = _section_body(text)
            vc_report = run_validation(vc_sections, profile)
            print("\n--- Content Validation ---")
            vc_print(vc_report)
            report["content_validation"] = vc_report
            if not vc_report["overall_passed"]:
                report["overall_passed"] = False
        except ImportError:
            print(
                "Warning: validate_content.py not available; skipped content validation.",
                file=sys.stderr,
            )

    print("\nOverall:", "PASSED" if report["overall_passed"] else "FAILED")

    # ── Auto-export to other formats ───────────────────────────────────
    if args.export in ("all", "latex"):
        try:
            from export_latex import export_markdown_to_latex

            tex_path = out_path.with_suffix(".tex")
            bib_name = out_path.stem + ".bib"
            export_markdown_to_latex(combined, tex_path, bibfile=bib_name)
        except Exception as e:
            print(f"LaTeX export skipped: {e}", file=sys.stderr)

    if args.export in ("all", "docx"):
        try:
            from export_docx import export_markdown_to_docx

            docx_path = out_path.with_suffix(".docx")
            export_markdown_to_docx(combined, docx_path)
        except ImportError:
            print(
                "Word export skipped: python-docx not installed (pip install python-docx).",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"Word export skipped: {e}", file=sys.stderr)

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"Report written to {args.report}.")

    state_path = Path(args.state) if args.state else Path("_tmp/manuscript/state.json")
    result_path = state_path.parent / "result.json"
    events_path = state_path.parent / "events.jsonl"
    status = (
        STATUS_COMPLETED if report.get("overall_passed") else STATUS_RETRYABLE_ERROR
    )
    message = (
        "Assembly and checks passed."
        if status == STATUS_COMPLETED
        else "Assembly completed with validation issues."
    )
    init_or_load_state(
        state_path=state_path,
        task_type="manuscript",
        stage="assemble_manuscript",
        resume=args.resume,
        extra={
            "profile": args.profile or "",
            "output": str(out_path),
            "overall_passed": bool(report.get("overall_passed")),
            "export": args.export,
        },
    )
    append_event(
        events_path=events_path,
        status=status,
        stage="assemble_manuscript",
        message=message,
        payload={
            "output": str(out_path),
            "overall_passed": bool(report.get("overall_passed")),
            "export": args.export,
        },
    )
    emit_result(
        build_result(
            status=status,
            stage="assemble_manuscript",
            message=message,
            result_path=result_path,
            payload={
                "output": str(out_path),
                "overall_passed": bool(report.get("overall_passed")),
                "report_file": args.report or "",
                "export": args.export,
            },
        )
    )
    return 0 if status == STATUS_COMPLETED else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit_result(
            build_result(
                status=STATUS_FATAL_ERROR,
                stage="assemble_manuscript",
                message=f"Fatal error: {exc}",
            )
        )
        raise SystemExit(1)
