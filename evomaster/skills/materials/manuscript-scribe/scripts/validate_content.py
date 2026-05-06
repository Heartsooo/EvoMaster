"""
Validate manuscript content against a format profile: word counts, completeness,
required elements, information flow, section ordering, unexpected sections, and
citation numbering consistency.

Run this **before** assemble_manuscript.py to catch short or incomplete sections early,
or pass --profile to assemble_manuscript.py to run checks at assembly time.

Usage:
  python validate_content.py --draft draft.md --profile research_paper
  python validate_content.py --sections_dir sections/ --profile computational_report
  python validate_content.py --draft draft.md --profile research_paper --planner_mode --report report.json

Output: Prints validation summary; optionally writes JSON report to --report.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from format_profiles import get_profile, resolve_section  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_common'))
from longtask_runtime import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_FATAL_ERROR,
    STATUS_RETRYABLE_ERROR,
    append_event,
    build_result,
    emit_result,
    init_or_load_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    """Count words (handles mixed CJK and Latin text)."""
    # Count CJK characters individually
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', text))
    # Count Latin/ASCII words
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))
    return cjk + latin


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments (<!-- ... -->) from text."""
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL).strip()


def _normalize_section_key(name: str) -> str:
    """Normalize section labels across styles (spaces/snake/camel/kebab)."""
    text = name.strip()
    text = re.sub(r'[_\-]+', ' ', text)
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()


def _is_placeholder_body(text: str) -> bool:
    t = _strip_html_comments(text).strip().lower()
    return t in {'(tbd)', 'tbd', 'todo', '待补充', '待完善', '待定'}


def _prefer_section_body(existing: str, incoming: str) -> str:
    """Merge duplicate section bodies by preferring richer non-placeholder text."""
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
    return incoming if _word_count(incoming) > _word_count(existing) else existing


def _canonicalize_sections(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, str]:
    """Canonicalize section keys by profile aliases and merge duplicates."""
    profile_name = str(profile.get('_profile_name', '') or '')
    canonical: dict[str, str] = {}
    canonical_map = {
        _normalize_section_key(sec): sec for sec in profile.get('sections', [])
    }
    alias_map = {
        _normalize_section_key(k): v
        for k, v in (profile.get('section_aliases', {}) or {}).items()
    }

    for raw_name, body in sections.items():
        key = _normalize_section_key(raw_name)
        mapped = canonical_map.get(key) or alias_map.get(key)
        if not mapped and profile_name:
            # Reuse shared resolver for consistency across scripts.
            try:
                mapped = resolve_section(profile_name, raw_name)
            except Exception:
                mapped = raw_name
        canonical_name = mapped or raw_name
        if canonical_name in canonical:
            canonical[canonical_name] = _prefer_section_body(
                canonical[canonical_name], body
            )
        else:
            canonical[canonical_name] = body
    return canonical


def _extract_sections_from_draft(content: str) -> dict[str, str]:
    """Parse a single draft into {section_name: body_text} (body only, no header).

    HTML comments (writing hints from init_manuscript) are stripped so they do not
    inflate word counts or interfere with completeness checks.
    """
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in content.splitlines():
        m = re.match(r'^##\s+(.+?)\s*$', line)
        if m:
            if current is not None:
                sections[current] = _strip_html_comments('\n'.join(buf).strip())
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = _strip_html_comments('\n'.join(buf).strip())
    return sections


def _load_sections(args: argparse.Namespace) -> dict[str, str]:
    """Load sections from either --draft or --sections_dir."""
    if args.draft:
        content = Path(args.draft).read_text(encoding='utf-8')
        return _extract_sections_from_draft(content)
    elif args.sections_dir:
        sdir = Path(args.sections_dir)
        sections: dict[str, str] = {}
        for f in sdir.iterdir():
            if f.suffix.lower() == '.md' and not f.name.startswith('_'):
                raw = f.read_text(encoding='utf-8').strip()
                name = f.stem
                # Strip "# Title" and "## SectionName" headers to get body only
                lines = raw.splitlines()
                body_lines = []
                for line in lines:
                    if re.match(r'^#{1,2}\s+', line):
                        continue
                    if line.strip().startswith('<!--') and line.strip().endswith('-->'):
                        continue
                    body_lines.append(line)
                sections[name] = '\n'.join(body_lines).strip()
        return sections
    return {}


def _extract_key_terms(text: str) -> set[str]:
    """Extract potential key terms: multi-word capitalized phrases and technical terms."""
    terms: set[str] = set()
    # Abbreviations defined as "Full Name (ABBR)"
    for m in re.finditer(r'([A-Za-z][A-Za-z0-9\s\-]+?)\s*\(\s*([A-Z]{2,})\s*\)', text):
        terms.add(m.group(2).strip())
    # Standalone abbreviations (2+ uppercase chars)
    for m in re.finditer(r'\b([A-Z][A-Z0-9]{1,})\b', text):
        t = m.group(1)
        # Filter common words
        if t not in {
            'TBD',
            'URL',
            'HTTP',
            'HTTPS',
            'PDF',
            'JSON',
            'HTML',
            'API',
            'AND',
            'THE',
            'FOR',
            'NOT',
        }:
            terms.add(t)
    return terms


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_word_counts(
    sections: dict[str, str],
    profile: dict[str, Any],
    planner_mode: bool = False,
) -> dict[str, Any]:
    """Check per-section and overall word counts against profile minimums."""
    result: dict[str, Any] = {
        'passed': True,
        'total_words': 0,
        'overall_min': profile['overall_min_words'],
        'sections': {},
        'warnings': [],
        'errors': [],
    }
    multiplier = 1.5 if planner_mode else 1.0

    for sec_name in profile['sections']:
        meta = profile['section_meta'].get(sec_name, {})
        min_w = int(meta.get('min_words', 0) * multiplier)
        max_w = meta.get('max_words')
        body = sections.get(sec_name, '')
        wc = _word_count(body)
        result['total_words'] += wc

        sec_info: dict[str, Any] = {'word_count': wc, 'min_words': min_w}
        if max_w:
            sec_info['max_words'] = max_w

        if wc < min_w:
            sec_info['status'] = 'UNDER'
            msg = f"{sec_name}: {wc} words (minimum {min_w})"
            if min_w > 0:
                result['errors'].append(msg)
                result['passed'] = False
        elif max_w and wc > max_w:
            sec_info['status'] = 'OVER'
            result['warnings'].append(f"{sec_name}: {wc} words (max {max_w})")
        else:
            sec_info['status'] = 'OK'

        result['sections'][sec_name] = sec_info

    overall_min = int(profile['overall_min_words'] * multiplier)
    if result['total_words'] < overall_min:
        result['errors'].append(
            f"Overall: {result['total_words']} words (minimum {overall_min})"
        )
        result['passed'] = False

    return result


def check_completeness(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Check for TBD placeholders and missing sections."""
    result: dict[str, Any] = {'passed': True, 'missing': [], 'tbd': [], 'empty': []}

    for sec_name in profile['sections']:
        if sec_name not in sections:
            result['missing'].append(sec_name)
            result['passed'] = False
            continue
        body = sections[sec_name].strip()
        if not body:
            result['empty'].append(sec_name)
            result['passed'] = False
        elif body == '(TBD)' or body.startswith('(TBD)'):
            result['tbd'].append(sec_name)
            result['passed'] = False

    return result


def check_required_elements(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Heuristic check for required elements in each section."""
    result: dict[str, Any] = {'passed': True, 'missing_elements': {}}

    for sec_name in profile['sections']:
        meta = profile['section_meta'].get(sec_name, {})
        required = meta.get('required_elements', [])
        if not required:
            continue
        body = sections.get(sec_name, '').lower()
        if not body or body.startswith('(tbd)'):
            continue  # Already caught by completeness check

        missing = []
        for elem in required:
            # Support multilingual aliases in one token, e.g. "solution|技术方案".
            alias_groups = [
                p.strip().lower() for p in str(elem).split('|') if p.strip()
            ]
            matched = False
            for alias in alias_groups:
                keywords = alias.replace('_', ' ').split()
                if any(kw in body for kw in keywords):
                    matched = True
                    break
            if not matched:
                missing.append(elem)
        if missing:
            result['missing_elements'][sec_name] = missing
            result['passed'] = False

    return result


def check_information_flow(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Check cross-section coherence: terms defined in earlier sections should
    appear in later sections where appropriate."""
    result: dict[str, Any] = {'passed': True, 'warnings': []}

    sec_names = profile['sections']
    sec_terms: dict[str, set[str]] = {}
    for name in sec_names:
        body = sections.get(name, '')
        sec_terms[name] = _extract_key_terms(body)

    # Define expected flow relationships based on common patterns
    flow_pairs = []
    lower_names = [n.lower() for n in sec_names]

    # Methods -> Results (terms in methods should appear in results)
    methods_idx = next((i for i, n in enumerate(lower_names) if 'method' in n), None)
    results_idx = next((i for i, n in enumerate(lower_names) if 'result' in n), None)
    if methods_idx is not None and results_idx is not None:
        flow_pairs.append((sec_names[methods_idx], sec_names[results_idx]))

    # Results -> Discussion (terms in results should appear in discussion)
    discussion_idx = next(
        (i for i, n in enumerate(lower_names) if 'discussion' in n or 'analysis' in n),
        None,
    )
    if results_idx is not None and discussion_idx is not None:
        flow_pairs.append((sec_names[results_idx], sec_names[discussion_idx]))

    for src, dst in flow_pairs:
        src_terms = sec_terms.get(src, set())
        dst_terms = sec_terms.get(dst, set())
        if not src_terms or not dst_terms:
            continue
        # Check how many source terms appear in destination
        overlap = src_terms & dst_terms
        if src_terms and len(overlap) < len(src_terms) * 0.3:
            missing = src_terms - dst_terms
            if missing:
                sample = sorted(missing)[:5]
                result['warnings'].append(
                    f"Low term overlap from {src} -> {dst}: "
                    f"terms {sample} from {src} not found in {dst}"
                )

    if result['warnings']:
        result['passed'] = False

    return result


def check_section_ordering(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Verify that sections appear in the expected profile order."""
    result: dict[str, Any] = {
        'passed': True,
        'expected': profile['sections'],
        'actual': [],
        'warnings': [],
    }

    actual_order = list(sections.keys())
    result['actual'] = actual_order

    expected = profile['sections']
    # Filter actual to only those that match expected names
    actual_in_expected = [s for s in actual_order if s in expected]
    expected_in_actual = [s for s in expected if s in actual_order]

    if actual_in_expected != expected_in_actual:
        result['warnings'].append(
            f"Section order mismatch. Expected: {expected_in_actual}, "
            f"Actual: {actual_in_expected}"
        )
        result['passed'] = False

    return result


def check_unexpected_sections(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Flag sections not defined in the profile.

    * **Strict** profiles (``strict_sections=True``): unexpected sections are
      **errors** and set ``passed=False``.
    * **Non-strict** profiles: unexpected sections are **warnings** only —
      ``passed`` stays ``True`` so they do not block validation.
    """
    expected = set(profile['sections'])
    unexpected = [s for s in sections if s not in expected]
    strict = bool(profile.get('strict_sections', False))
    return {
        'passed': (not unexpected) if strict else True,
        'unexpected': unexpected,
        'strict': strict,
    }


def check_citation_consistency(
    sections: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Check in-text ``[n]`` citations against References numbering.

    Validates:
    * In-text numbers are contiguous from 1.
    * References list numbers are contiguous from 1.
    * Every in-text ``[n]`` has a matching ``[n]`` in References and vice-versa.
    """
    result: dict[str, Any] = {
        'passed': True,
        'in_text': [],
        'reference_entries': [],
        'missing_in_references': [],
        'unused_references': [],
        'errors': [],
    }

    # Determine the references section name for this profile.
    reference_section = next(
        (s for s in profile['sections'] if s.lower() == 'references'),
        None,
    )
    if reference_section is None:
        # Some profiles (e.g. patent) do not require a dedicated References section.
        non_ref_text = '\n\n'.join(sections.values())
        result['in_text'] = sorted(
            {
                int(m.group(1))
                for m in re.finditer(r'\[(\d+)\](?:\([^)]+\))?', non_ref_text)
            }
        )
        result['reference_entries'] = []
        return result

    # Body text (everything except the reference section).
    non_ref_text = '\n\n'.join(
        body for name, body in sections.items() if name != reference_section
    )
    in_text_nums = sorted(
        {int(m.group(1)) for m in re.finditer(r'\[(\d+)\](?:\([^)]+\))?', non_ref_text)}
    )

    # Reference entries (lines starting with [n]).
    ref_body = sections.get(reference_section, '')
    ref_nums = sorted(
        {
            int(m.group(1))
            for m in re.finditer(r'^\s*\[(\d+)\]', ref_body, flags=re.MULTILINE)
        }
    )

    result['in_text'] = in_text_nums
    result['reference_entries'] = ref_nums

    # Contiguity
    if in_text_nums:
        expected = list(range(1, max(in_text_nums) + 1))
        if in_text_nums != expected:
            result['errors'].append(
                f"In-text citation numbering is not contiguous from 1: found {in_text_nums}, expected {expected}."
            )
    if ref_nums:
        expected_ref = list(range(1, max(ref_nums) + 1))
        if ref_nums != expected_ref:
            result['errors'].append(
                f"References numbering is not contiguous from 1: found {ref_nums}, expected {expected_ref}."
            )

    # Cross-check
    missing = [n for n in in_text_nums if n not in ref_nums]
    unused = [n for n in ref_nums if n not in in_text_nums]
    if missing:
        result['missing_in_references'] = missing
        result['errors'].append(f"In-text citations missing in References: {missing}")
    if unused:
        result['unused_references'] = unused
        result['errors'].append(f"References not cited in text: {unused}")

    if result['errors']:
        result['passed'] = False
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_validation(
    sections: dict[str, str],
    profile: dict[str, Any],
    planner_mode: bool = False,
) -> dict[str, Any]:
    """Run all validation checks and return a combined report."""
    sections = _canonicalize_sections(sections, profile)
    report: dict[str, Any] = {}
    report['word_counts'] = check_word_counts(sections, profile, planner_mode)
    report['completeness'] = check_completeness(sections, profile)
    report['required_elements'] = check_required_elements(sections, profile)
    report['information_flow'] = check_information_flow(sections, profile)
    report['section_ordering'] = check_section_ordering(sections, profile)
    report['unexpected_sections'] = check_unexpected_sections(sections, profile)
    report['citation_consistency'] = check_citation_consistency(sections, profile)

    report['overall_passed'] = all(
        report[k]['passed']
        for k in [
            'word_counts',
            'completeness',
            'required_elements',
            'information_flow',
            'section_ordering',
            'unexpected_sections',
            'citation_consistency',
        ]
    )
    return report


def print_report(report: dict[str, Any]) -> None:
    """Print a human-readable validation summary."""
    wc = report['word_counts']
    print(
        f"=== Word Counts (total: {wc['total_words']} words, min: {wc['overall_min']}) ==="
    )
    for sec, info in wc['sections'].items():
        status = info['status']
        marker = 'OK' if status == 'OK' else ('WARN' if status == 'OVER' else 'FAIL')
        min_str = f" (min {info['min_words']})" if info['min_words'] else ''
        print(f"  [{marker}] {sec}: {info['word_count']} words{min_str}")
    for e in wc.get('errors', []):
        print(f"  ERROR: {e}")
    for w in wc.get('warnings', []):
        print(f"  WARN:  {w}")

    comp = report['completeness']
    if comp['missing']:
        print(f"\n=== Missing Sections: {comp['missing']} ===")
    if comp['tbd']:
        print(f"=== Still TBD: {comp['tbd']} ===")
    if comp['empty']:
        print(f"=== Empty Sections: {comp['empty']} ===")

    elems = report['required_elements']
    if elems['missing_elements']:
        print('\n=== Missing Required Elements ===')
        for sec, missing in elems['missing_elements'].items():
            print(f"  {sec}: missing {missing}")

    flow = report['information_flow']
    if flow['warnings']:
        print('\n=== Information Flow Warnings ===')
        for w in flow['warnings']:
            print(f"  {w}")

    order = report['section_ordering']
    if order['warnings']:
        print('\n=== Section Ordering ===')
        for w in order['warnings']:
            print(f"  {w}")

    unexpected = report['unexpected_sections']
    if unexpected['unexpected']:
        severity = 'ERROR' if unexpected.get('strict') else 'WARN'
        print("\n=== Unexpected Sections (not in profile) ===")
        for s in unexpected['unexpected']:
            print(f"  [{severity}] {s}")

    cite = report['citation_consistency']
    if cite['errors']:
        print('\n=== Citation Consistency ===')
        for e in cite['errors']:
            print(f"  ERROR: {e}")

    overall = 'PASSED' if report['overall_passed'] else 'FAILED'
    print(f"\nOverall: {overall}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Validate manuscript content against a format profile.'
    )
    ap.add_argument('--draft', default=None, help='Path to single draft file')
    ap.add_argument(
        '--sections_dir', default=None, help='Directory of section .md files'
    )
    ap.add_argument(
        '--profile',
        required=True,
        help='Format profile name (e.g. research_paper, computational_report)',
    )
    ap.add_argument(
        '--planner_mode',
        action='store_true',
        help='Enforce stricter minimums (1.5x base)',
    )
    ap.add_argument('--report', default=None, help='Write JSON report to this path')
    ap.add_argument(
        '--state',
        default=None,
        help='Optional long-task state file path (default: _tmp/manuscript/state.json).',
    )
    ap.add_argument(
        '--resume',
        action='store_true',
        help='Resume and update existing state file when available.',
    )
    args = ap.parse_args()

    if not args.draft and not args.sections_dir:
        print('Provide --draft or --sections_dir.', file=sys.stderr)
        sys.exit(1)
    if args.draft and args.sections_dir:
        print('Use either --draft or --sections_dir, not both.', file=sys.stderr)
        sys.exit(1)

    profile = get_profile(args.profile)
    profile = dict(profile)
    profile['_profile_name'] = args.profile
    sections = _load_sections(args)

    report = run_validation(sections, profile, planner_mode=args.planner_mode)
    print_report(report)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding='utf-8',
        )
        print(f"\nReport written to {args.report}.")

    state_path = Path(args.state) if args.state else Path('_tmp/manuscript/state.json')
    result_path = state_path.parent / 'result.json'
    events_path = state_path.parent / 'events.jsonl'
    status = (
        STATUS_COMPLETED if report.get('overall_passed') else STATUS_RETRYABLE_ERROR
    )
    message = (
        'Validation passed.'
        if status == STATUS_COMPLETED
        else 'Validation reported issues to fix.'
    )
    init_or_load_state(
        state_path=state_path,
        task_type='manuscript',
        stage='validate_content',
        resume=args.resume,
        extra={
            'profile': args.profile,
            'planner_mode': bool(args.planner_mode),
            'overall_passed': bool(report.get('overall_passed')),
            'source': args.draft or args.sections_dir or '',
        },
    )
    append_event(
        events_path=events_path,
        status=status,
        stage='validate_content',
        message=message,
        payload={
            'profile': args.profile,
            'planner_mode': bool(args.planner_mode),
            'overall_passed': bool(report.get('overall_passed')),
            'errors': report.get('word_counts', {}).get('errors', []),
        },
    )
    emit_result(
        build_result(
            status=status,
            stage='validate_content',
            message=message,
            result_path=result_path,
            payload={
                'profile': args.profile,
                'planner_mode': bool(args.planner_mode),
                'overall_passed': bool(report.get('overall_passed')),
                'report_file': args.report or '',
            },
        )
    )
    return 0 if status == STATUS_COMPLETED else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit_result(
            build_result(
                status=STATUS_FATAL_ERROR,
                stage='validate_content',
                message=f"Fatal error: {exc}",
            )
        )
        raise SystemExit(1)
