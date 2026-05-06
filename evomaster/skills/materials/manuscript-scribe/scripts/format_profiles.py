"""
Format profiles for manuscript-scribe.

Each profile defines section order, per-section metadata (min_words, max_words,
required_elements, writing_hint), and an overall minimum word count.  Profiles
drive ``init_manuscript.py`` (template generation), ``validate_content.py``
(quality gates), and ``assemble_manuscript.py`` (section ordering).

Two profile-level flags control strictness:

* ``strict_sections`` (bool, default ``False``):
  When ``True``, **only** the listed sections are accepted. ``write_section.py``
  rejects unknown names with exit-code 2, and ``validate_content.py`` marks
  unexpected sections as errors.  When ``False``, extra sections are allowed
  (warned but not blocked).

* ``section_aliases`` (dict[str, str], default ``{}``):
  Maps common misspellings / synonyms (lower-case) to the canonical section
  name.  Alias resolution happens in ``resolve_section()`` and is used by
  ``write_section.py`` so the agent can write ``"Computational Methods"`` and
  it lands in ``"Methods"``.

Usage from other scripts::

    from format_profiles import (
        get_profile, list_profiles, resolve_section,
        required_content_sections, is_strict_profile,
    )
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

FORMAT_PROFILES: dict[str, dict[str, Any]] = {
    # ── Standard academic research paper ─────────────────────────────────
    # Default section order: Abstract, Introduction, Methods, Results,
    # Discussion, References.
    # Nature-style variant: omit Methods here; add it after Discussion.
    # To use the Nature variant, pass --nature_order flag to init_manuscript.py
    # or specify sections explicitly; the section metadata is identical.
    'research_paper': {
        'description': 'Standard academic research paper (default IMRaD order; Nature-style variant: Methods after Discussion)',
        'sections': [
            'Abstract',
            'Introduction',
            'Methods',
            'Results',
            'Discussion',
            'References',
        ],
        # Nature-style alternate section order (Methods after Discussion)
        'sections_nature_variant': [
            'Abstract',
            'Introduction',
            'Results',
            'Discussion',
            'Methods',
            'References',
        ],
        'overall_min_words': 3000,
        'section_meta': {
            'Abstract': {
                'min_words': 150,
                'max_words': 300,
                'required_elements': ['objective', 'methods', 'key_findings'],
                'writing_hint': (
                    'Concise summary of the entire paper: state the problem, '
                    'methods used, main results, and significance in one paragraph. '
                    'Nature-style variant: keep ≤200 words; focus on problem and main finding.'
                ),
            },
            'Introduction': {
                'min_words': 400,
                'required_elements': ['background', 'gap', 'objective'],
                'writing_hint': (
                    'Start broad (field context), narrow to the specific gap in '
                    'knowledge, then state the objective/contribution of this work. '
                    'Cite relevant prior work throughout. '
                    'Nature-style variant: keep concise; get to the point quickly.'
                ),
            },
            'Methods': {
                'min_words': 400,
                'required_elements': ['approach', 'parameters'],
                'writing_hint': (
                    'Describe the approach in enough detail for reproducibility: '
                    'materials/models, computational or experimental setup, key '
                    'parameters, and analysis techniques. Cite methods references. '
                    'Nature-style variant: this section is placed after Discussion.'
                ),
            },
            'Results': {
                'min_words': 500,
                'required_elements': ['data', 'observations'],
                'writing_hint': (
                    'Present findings with supporting data (figures, tables). '
                    'Describe trends and observations objectively. Reference each '
                    'figure/table explicitly. '
                    'Nature-style variant: light interpretation may be combined here.'
                ),
            },
            'Discussion': {
                'min_words': 400,
                'required_elements': ['interpretation', 'comparison', 'implications'],
                'writing_hint': (
                    'Interpret results in the context of prior work. Compare with '
                    'literature, discuss implications, limitations, and future '
                    'directions.'
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': (
                    'Numbered list matching in-text [n](url) citations. Each entry: '
                    'Authors, Title, *Journal*, Year, URL.'
                ),
            },
        },
    },
    # ── Grant proposal ────────────────────────────────────────────────────
    'grant': {
        'description': 'Grant proposal / funding application',
        'sections': [
            'Summary / Abstract',
            'Significance',
            'Approach',
            'Preliminary Results',
            'Timeline',
            'References',
        ],
        'overall_min_words': 2500,
        'section_meta': {
            'Summary / Abstract': {
                'min_words': 200,
                'max_words': 400,
                'required_elements': ['objective', 'significance', 'approach'],
                'writing_hint': (
                    'Executive summary of the proposal: what you will do, why it '
                    'matters, and how.'
                ),
            },
            'Significance': {
                'min_words': 400,
                'required_elements': ['impact', 'gap'],
                'writing_hint': (
                    'Why this research matters. Identify the gap and potential '
                    'impact on the field or society.'
                ),
            },
            'Approach': {
                'min_words': 600,
                'required_elements': ['methodology', 'milestones'],
                'writing_hint': (
                    'Detailed research plan: methods, milestones, risk mitigation. '
                    'Demonstrate feasibility.'
                ),
            },
            'Preliminary Results': {
                'min_words': 300,
                'required_elements': ['evidence'],
                'writing_hint': (
                    'Show existing data or pilot results that support feasibility.'
                ),
            },
            'Timeline': {
                'min_words': 100,
                'required_elements': ['schedule'],
                'writing_hint': 'Gantt chart or milestone table with deliverables.',
            },
            'References': {
                'min_words': 0,
                'writing_hint': 'Numbered list with URLs.',
            },
        },
    },
    # ── Lean computational report ─────────────────────────────────────────
    'computational_report': {
        'description': (
            'Lean computational study write-up (DFT, MD, simulation results). '
            'Three sections only: Methods, Results and Discussion, References.'
        ),
        'strict_sections': True,
        'section_aliases': {
            'method': 'Methods',
            'computational method': 'Methods',
            'computational methods': 'Methods',
            'methodology': 'Methods',
            'result': 'Results and Discussion',
            'results': 'Results and Discussion',
            'discussion': 'Results and Discussion',
            'results discussion': 'Results and Discussion',
            'reference': 'References',
            'bibliography': 'References',
        },
        'sections': [
            'Methods',
            'Results and Discussion',
            'References',
        ],
        'overall_min_words': 800,
        'section_meta': {
            'Methods': {
                'min_words': 200,
                'required_elements': [
                    'software',
                    'functional_or_method',
                    'basis_or_cutoff',
                    'convergence',
                ],
                'writing_hint': (
                    'Structural model source (experimental data, database, etc.), '
                    'software/framework (e.g. CP2K, VASP, ABACUS), exchange-correlation '
                    'functional (PBE, HSE, etc.), basis set or plane-wave cutoff, '
                    'pseudopotentials, convergence criteria, k-point sampling, any '
                    'corrections (e.g. Hubbard U, dispersion). Cite method references '
                    'with [n](url). '
                    'TYPOGRAPHIC: NO raw input keywords (RUN_TYPE, EPS_SCF, CUTOFF); '
                    "describe physically ('single-point energy', 'convergence threshold "
                    "5 × 10^{−6}'). NO file names (cp2k.inp, *.pdos). "
                    'Italic physics quantities: *U*_{eff}, *E*_{F}. '
                    'Periodic systems: HOCO/LUCO not HOMO/LUMO; VBM/CBM for band edges. '
                    'En-dash for ranges (1.88–1.89 Å), minus for negatives (−0.5 eV).'
                ),
            },
            'Results and Discussion': {
                'min_words': 300,
                'required_elements': ['key_observable', 'interpretation'],
                'writing_hint': (
                    'Present key observables (band structure, DOS, orbitals, energies, '
                    'formation energies, elastic constants, etc.), interpret physical '
                    'meaning, compare with experiment or literature where possible. '
                    "Reference figures (e.g. 'Figure xx-a'). Assign physical mechanisms "
                    '(e.g. charge-transfer, bonding character). '
                    'TYPOGRAPHIC: Build mechanism-oriented narrative (orbital analysis → '
                    'charge-transfer assignment). Chemical formulas: C_{7}H_{8} or CO2 '
                    '(auto-subscripted). Significant figures: match method precision '
                    '(bond lengths 2 decimals, band gaps 2 decimals). Use ≈ for approx.'
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': (
                    'Numbered list. Each entry: '
                    '[n] Authors. Title. *Journal*, **Year**, Volume, Pages. URL. '
                    'Journal italic, year bold, page range with en-dash. '
                    'Must match in-text [n] citations exactly.'
                ),
            },
        },
    },
    # ── Patent application ────────────────────────────────────────────────
    'patent': {
        'description': 'Patent application document',
        'strict_sections': True,
        'section_aliases': {
            'prior art': 'Background Art',
            'technical background': 'Background Art',
            'invention summary': 'Summary of Invention',
            'invention_summary': 'Summary of Invention',
            'description': 'Detailed Description',
            'embodiments': 'Detailed Description',
            # Chinese headings
            '技术领域': 'Technical Field',
            '背景技术': 'Background Art',
            '发明内容': 'Summary of Invention',
            '具体实施方式': 'Detailed Description',
            '具体实施例': 'Detailed Description',
            '实施方式': 'Detailed Description',
            '权利要求': 'Claims',
            '权利要求书': 'Claims',
            '摘要': 'Abstract',
            # File-stem / snake_case / compact variants
            'technical_field': 'Technical Field',
            'technicalfield': 'Technical Field',
            'background_art': 'Background Art',
            'backgroundart': 'Background Art',
            'summary_of_invention': 'Summary of Invention',
            'summaryofinvention': 'Summary of Invention',
            'detailed_description': 'Detailed Description',
            'detaileddescription': 'Detailed Description',
            'abstract_patent': 'Abstract',
            'abstractpatent': 'Abstract',
        },
        'sections': [
            'Technical Field',
            'Background Art',
            'Summary of Invention',
            'Detailed Description',
            'Claims',
            'Abstract',
        ],
        'overall_min_words': 3000,
        'section_meta': {
            'Technical Field': {
                'min_words': 50,
                'required_elements': ['field|技术领域'],
                'writing_hint': (
                    'One or two sentences identifying the technical field of the '
                    'invention.'
                ),
            },
            'Background Art': {
                'min_words': 300,
                'required_elements': ['prior_art|背景技术', 'problem|问题'],
                'writing_hint': (
                    'Describe the state of the art and the technical problem that '
                    'the invention solves. Reference prior patents or publications.'
                ),
            },
            'Summary of Invention': {
                'min_words': 200,
                'required_elements': ['solution|技术方案', 'advantage|有益效果'],
                'writing_hint': (
                    'Broad description of the invention and its advantages over '
                    'prior art. Should correspond to the broadest claim.'
                ),
            },
            'Detailed Description': {
                'min_words': 1000,
                'required_elements': ['embodiment|实施例', 'examples|示例'],
                'writing_hint': (
                    'Full technical description with at least one preferred '
                    'embodiment. Include specific materials, conditions, dimensions, '
                    'and working examples with data. Enable a skilled person to '
                    'reproduce the invention.'
                ),
            },
            'Claims': {
                'min_words': 200,
                'required_elements': [
                    'independent_claim|独立权利要求',
                    'dependent_claims|从属权利要求',
                ],
                'writing_hint': (
                    'Numbered claims. Start with the broadest independent claim, '
                    'then dependent claims that narrow it. Use patent claim language '
                    '(comprising, wherein, characterized in that).'
                ),
            },
            'Abstract': {
                'min_words': 50,
                'max_words': 150,
                'required_elements': ['summary|摘要'],
                'writing_hint': (
                    'Brief summary of the disclosure for search/classification '
                    'purposes. Typically matches the broadest independent claim.'
                ),
            },
        },
    },
    # ── Review article ────────────────────────────────────────────────────
    'review': {
        'description': 'Review / survey article (comprehensive literature analysis)',
        'sections': [
            'Abstract',
            'Introduction',
            'Scope and Methodology',
            'State of the Art',
            'Critical Analysis',
            'Future Directions',
            'Conclusions',
            'References',
        ],
        'overall_min_words': 6000,
        'section_meta': {
            'Abstract': {
                'min_words': 200,
                'max_words': 350,
                'required_elements': ['scope', 'key_findings', 'conclusions'],
                'writing_hint': (
                    'Summarize the scope, key findings from the literature, and '
                    'the main conclusions/outlook.'
                ),
            },
            'Introduction': {
                'min_words': 500,
                'required_elements': ['background', 'motivation', 'scope'],
                'writing_hint': (
                    'Broad context, motivation for the review, and explicit scope '
                    '(what is covered and what is not).'
                ),
            },
            'Scope and Methodology': {
                'min_words': 200,
                'required_elements': ['search_strategy', 'inclusion_criteria'],
                'writing_hint': (
                    'Describe how the literature was searched and selected. '
                    'Databases used, keywords, date range, inclusion/exclusion criteria.'
                ),
            },
            'State of the Art': {
                'min_words': 2000,
                'required_elements': ['prior_work', 'themes'],
                'writing_hint': (
                    'The main body. Organize by theme, material class, method, or '
                    'chronology. Multiple subsections. Detailed discussion with '
                    'quantitative comparisons, not just a list of papers. Cite '
                    'extensively.'
                ),
            },
            'Critical Analysis': {
                'min_words': 600,
                'required_elements': ['strengths', 'weaknesses', 'gaps'],
                'writing_hint': (
                    'Synthesize across the reviewed works. Identify consensus, '
                    'contradictions, methodological strengths/weaknesses, and '
                    'knowledge gaps.'
                ),
            },
            'Future Directions': {
                'min_words': 300,
                'required_elements': ['opportunities', 'challenges'],
                'writing_hint': (
                    'Promising research directions, emerging techniques, open '
                    'problems.'
                ),
            },
            'Conclusions': {
                'min_words': 200,
                'required_elements': ['summary', 'outlook'],
                'writing_hint': (
                    "Concise summary of the review's main messages and outlook."
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': 'Numbered list with URLs. Expect 50+ references.',
            },
        },
    },
    # ── Technical / engineering report ─────────────────────────────────────
    'technical_report': {
        'description': 'Technical or engineering report',
        'sections': [
            'Executive Summary',
            'Introduction',
            'Methodology',
            'Findings',
            'Analysis and Discussion',
            'Recommendations',
            'Appendices',
            'References',
        ],
        'overall_min_words': 3000,
        'section_meta': {
            'Executive Summary': {
                'min_words': 200,
                'max_words': 500,
                'required_elements': ['objective', 'key_findings', 'recommendations'],
                'writing_hint': (
                    'Stand-alone summary for decision-makers. State the objective, '
                    'key findings, and recommendations.'
                ),
            },
            'Introduction': {
                'min_words': 300,
                'required_elements': ['background', 'objective', 'scope'],
                'writing_hint': (
                    'Background, objective of the study, and scope of the report.'
                ),
            },
            'Methodology': {
                'min_words': 400,
                'required_elements': ['approach', 'tools'],
                'writing_hint': (
                    'Describe the approach, tools, data sources, and any standards '
                    'or protocols followed.'
                ),
            },
            'Findings': {
                'min_words': 500,
                'required_elements': ['data', 'observations'],
                'writing_hint': (
                    'Present findings factually with supporting data, figures, and '
                    'tables.'
                ),
            },
            'Analysis and Discussion': {
                'min_words': 500,
                'required_elements': ['interpretation', 'comparison'],
                'writing_hint': (
                    'Interpret findings, compare with benchmarks or prior studies, '
                    'discuss implications.'
                ),
            },
            'Recommendations': {
                'min_words': 200,
                'required_elements': ['actions'],
                'writing_hint': (
                    'Actionable recommendations based on the findings and analysis.'
                ),
            },
            'Appendices': {
                'min_words': 0,
                'writing_hint': (
                    'Supplementary data, raw results, detailed calculations. '
                    'Optional; omit if not needed.'
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': 'Numbered list with URLs.',
            },
        },
    },
    # ── Single thesis chapter ─────────────────────────────────────────────
    'thesis_section': {
        'description': (
            'Single thesis chapter (longer and more pedagogical than a paper)'
        ),
        'sections': [
            'Introduction',
            'Literature Review',
            'Methodology',
            'Results',
            'Discussion',
            'Conclusion',
            'References',
        ],
        'overall_min_words': 5000,
        'section_meta': {
            'Introduction': {
                'min_words': 500,
                'required_elements': ['context', 'objective', 'chapter_outline'],
                'writing_hint': (
                    'Chapter context within the thesis, research questions or '
                    'hypotheses, and an outline of what follows in this chapter.'
                ),
            },
            'Literature Review': {
                'min_words': 1000,
                'required_elements': ['prior_work', 'gap'],
                'writing_hint': (
                    'Thorough review of prior work relevant to this chapter. '
                    'More detailed and pedagogical than a journal paper introduction. '
                    'Identify gaps that this chapter addresses.'
                ),
            },
            'Methodology': {
                'min_words': 800,
                'required_elements': ['approach', 'justification'],
                'writing_hint': (
                    'Detailed description of methods with justification for each '
                    'choice. Explain why this approach was selected over alternatives.'
                ),
            },
            'Results': {
                'min_words': 600,
                'required_elements': ['data', 'observations'],
                'writing_hint': (
                    'Present results with figures and tables. Describe observations '
                    'in detail; a thesis allows more space than a paper.'
                ),
            },
            'Discussion': {
                'min_words': 600,
                'required_elements': ['interpretation', 'comparison', 'implications'],
                'writing_hint': (
                    'Interpret results, compare with literature, discuss '
                    'limitations, and connect back to the research questions.'
                ),
            },
            'Conclusion': {
                'min_words': 300,
                'required_elements': ['summary', 'contributions'],
                'writing_hint': (
                    "Summarize the chapter's contributions, key findings, and how "
                    'they feed into the next chapter or the thesis overall.'
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': 'Numbered list with URLs.',
            },
        },
    },
    # ------------------------------------------------------------------ literature_review
    'literature_review': {
        'description': (
            'Literature review / deep-survey output (5-section structure '
            'matching deep-survey skill output exactly)'
        ),
        'sections': [
            'Executive Summary',
            'Key Methodologies',
            'State of the Art',
            'Gap Analysis',
            'References',
        ],
        'overall_min_words': 4000,
        'section_meta': {
            'Executive Summary': {
                'min_words': 200,
                'required_elements': ['objective', 'key_findings'],
                'writing_hint': (
                    '3-5 paragraphs: field overview, key developments, '
                    'main methods, open challenges.'
                ),
            },
            'Key Methodologies': {
                'min_words': 300,
                'required_elements': ['methods'],
                'writing_hint': (
                    'Table + narrative: method / key features / '
                    'typical applications / references.'
                ),
            },
            'State of the Art': {
                'min_words': 1500,
                'required_elements': ['prior_work', 'themes'],
                'writing_hint': (
                    'Multiple subsections by theme. '
                    'Quantitative comparisons, not just a list. 20+ sources.'
                ),
            },
            'Gap Analysis': {
                'min_words': 300,
                'required_elements': ['gaps'],
                'writing_hint': (
                    'Ranked gaps by impact. '
                    'Each gap: 2-4 sentences with evidence and citation.'
                ),
            },
            'References': {
                'min_words': 0,
                'writing_hint': (
                    'Numbered list [n] Authors. Title. *Journal*, **Year**. URL.'
                ),
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers — single source of truth for profile queries
# ---------------------------------------------------------------------------


def get_profile(name: str) -> dict[str, Any]:
    """Return a profile dict by name.  Raises ``KeyError`` if not found."""
    if name not in FORMAT_PROFILES:
        available = ', '.join(sorted(FORMAT_PROFILES))
        raise KeyError(f"Unknown format profile '{name}'. Available: {available}")
    return FORMAT_PROFILES[name]


def list_profiles() -> list[str]:
    """Return sorted list of available profile names."""
    return sorted(FORMAT_PROFILES)


def is_strict_profile(name: str) -> bool:
    """Return ``True`` if the profile rejects unexpected sections."""
    return bool(get_profile(name).get('strict_sections', False))


def resolve_section(profile_name: str, raw_section: str) -> str:
    """Resolve *raw_section* to its canonical section name.

    Resolution order:
    1. Case-insensitive exact match with profile section list.
    2. Alias match via ``section_aliases``.
    3. Strict profile → ``ValueError``; non-strict → passthrough.
    """
    profile = get_profile(profile_name)
    sections = profile['sections']

    def _norm(value: str) -> str:
        # Accept section keys in snake_case, camelCase, kebab-case, and mixed spacing.
        text = value.strip()
        text = re.sub(r'[_\-]+', ' ', text)
        text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()

    key = _norm(raw_section)
    canonical_map = {_norm(s): s for s in sections}
    if key in canonical_map:
        return canonical_map[key]

    aliases: dict[str, str] = profile.get('section_aliases', {})
    alias_map = {_norm(k): v for k, v in aliases.items()}
    mapped = alias_map.get(key)
    if mapped and mapped in sections:
        return mapped

    if profile.get('strict_sections', False):
        allowed_text = ', '.join(sections)
        raise ValueError(
            f"Section '{raw_section}' is not allowed for strict profile "
            f"'{profile_name}'. Allowed: {allowed_text}"
        )
    return raw_section


def required_content_sections(profile_name: str) -> list[str]:
    """Return sections with ``min_words > 0`` (i.e. that need real content)."""
    profile = get_profile(profile_name)
    return [
        sec
        for sec in profile['sections']
        if profile.get('section_meta', {}).get(sec, {}).get('min_words', 0) > 0
    ]


def profile_summary(name: str) -> str:
    """Return a one-line summary: 'name — description (N sections, M+ words)'."""
    p = get_profile(name)
    n = len(p['sections'])
    w = p['overall_min_words']
    return f"{name} — {p['description']} ({n} sections, {w}+ words)"


def all_profiles_summary() -> str:
    """Return a multi-line summary of every profile (for --list_formats)."""
    lines = []
    for name in list_profiles():
        p = FORMAT_PROFILES[name]
        secs = ', '.join(p['sections'])
        lines.append(f"  {name}")
        lines.append(f"    {p['description']}")
        lines.append(f"    Sections: {secs}")
        lines.append(f"    Min words: {p['overall_min_words']}")
        strict = 'yes' if p.get('strict_sections') else 'no'
        lines.append(f"    Strict: {strict}")
        lines.append('')
    return '\n'.join(lines)
