# Typographic & Writing Rules Reference

## Typographic style (mandatory for all manuscript-scribe output)

The export scripts (`export_docx.py`, `export_latex.py`) apply many of these automatically, but the **LLM must produce correctly formatted Markdown** for the conversion to work.

### Terminology
- **Define every abbreviation** at first use: "density functional theory (DFT)", "projected density of states (PDOS)". After the definition, use only the abbreviation.

### Physical quantities & font conventions in Markdown
- **Italic for scalar physical quantities**: `*U*`, `*E*`, `*k*`, `*T*`, `*V*`. Bold for vectors: `**F**`, `**k**`.
- **Subscripts**: `_{text}` notation: `*U*_{eff}`, `*E*_{F}`, `*E*_{g}`, `*k*_{B}`. Export scripts convert to Word subscript / LaTeX `_{\\mathrm{...}}`.
- **Superscripts**: `^{text}` notation: `10^{−6}`, `cm^{−1}`, `Å^{2}`. Export scripts convert to Word superscript / LaTeX `^{}`.
- **Descriptive subscripts are roman** (upright), not italic. Examples: *U*_{eff} — *U* italic, "eff" roman; *E*_{F} — "F" roman (Fermi); *E*_{g} — "g" roman (gap); *k*_{B} — "B" roman (Boltzmann).
- Physical quantity symbols: **always italic** (*U*, *E*, *T*, *k*, *V*, *P*, *H*, *G*, *S*).
- **No Unicode fake superscripts/subscripts**: Do NOT use `³`, `₂`, `⁻⁶`. Use `^{3}`, `_{2}`, `^{−6}`. Exception: in pure Markdown output (no export), Unicode is acceptable as a fallback.

### Symbols: dash and minus
- **Range / connection: en-dash "–"** (U+2013), NOT hyphen "-". Examples: `1.88–1.89 Å`, `pp. 57–70`, `Cu–N bond`.
- **Negative sign: minus "−"** (U+2212), NOT hyphen. Examples: `−6`, `−0.5 eV`, `10^{−6}`.
- **Hyphen "-"** only for compound adjectives: `self-consistent`, `plane-wave`, `Broyden-type`.
- The LLM must use the correct Unicode characters (–, −) in the Markdown source. The export scripts preserve them.

### Chemical formula formatting
- **Element order**: Hill system — C first, H second, then remaining elements alphabetically. For inorganic: electropositive first.
- **No spaces** between elements in a formula.
- **Element counts as subscripts**: Write `C_{7}H_{8}N_{2}O`. Export scripts convert `_{n}` to proper subscripts.

### Significant figures
- **Match precision to method accuracy**: DFT bond lengths 2 decimals, band gaps 2 decimals, lattice parameters 3–4 decimals.
- **Use "≈"** for approximate values.

### Reference list format
- `[n] Authors. Title. *Journal*, **Year**, Volume, Pages. URL`
- **Journal name**: italic. **Year**: bold. **Page range**: en-dash.

### Quick reference: LLM vs export responsibilities

| Rule | LLM writes (Markdown) | Export script handles |
|------|----------------------|---------------------|
| Italic physics quantities | `*E*`, `*U*` | Convert to italic font |
| Subscripts | `_{eff}`, `_{2}` | Word subscript / LaTeX |
| Superscripts | `^{−6}`, `^{2}` | Word superscript / LaTeX |
| Chemical formula subscripts | `C_{7}H_{8}` or `CO2` | Auto-detect and subscript |
| En-dash for ranges | `–` (U+2013) | Preserve |
| Minus sign | `−` (U+2212) | Preserve |

## De-AIGC Writing Rules (mandatory for all profiles except patent Claims)

Full reference: `Skill action=get_reference reference_name="de_aigc_style_guide.md"` (in `skills/_common/reference/`).

**Core rules (apply at every writing step):**
1. Lead with the real problem, not broad context.
2. Prefer concrete verbs over abstract labels.
3. Calibrate claims to evidence.
4. Remove filler openers: `Notably,`, `Significantly,`, `It is worth noting that`, `Importantly,`, `In this context,`.
5. Replace vague statistics with named ones (MAD, RMSD, STD); add boundary conditions.
6. Goal text per sentence: one main point only.

**High-risk openers to delete on sight**: `It is well known that`, `This section reviews`, `It should be noted that`, `Paves the way for`, `Groundbreaking`, `Unprecedented`, `This work fosters`, `Showcasing`, `Highlighting`.

**After drafting each section**, run the 5-pass De-AIGC checklist (claim calibration → specificity upgrade → compression → redundancy removal → tone scan).

**Patent exception**: De-AIGC rules apply to all sections **except Claims**.

## Planner mode guidelines

1. **Per-section steps**: Each section should be its own step.
2. **Multiple search cycles per section**: At least 2–3 search-summarize-append cycles per section.
3. **Validate before assembly**: Run `validate_content.py --planner_mode` for stricter thresholds (1.5x).
4. **Fix shortfalls**: Append more content before proceeding to assembly.

## Concept explanation and conceptual rigor (mandatory)

- **Definitions**: Precise definition for every key concept at first use.
- **Formulas**: Explain every symbol.
- **Concept relationships**: State how concepts relate.
- **Examples**: Where helpful, illustrate with concrete retrieval examples.

## Word count targets (for planner mode, aim for 1.5x these)
- Abstract: 150–300 words
- Introduction: 500+ words
- Methods: 400+ words (200+ for computational_report)
- Results: 500+ words (300+ for computational_report's "Results and Discussion")
- Discussion: 500+ words
- Literature Review (thesis): 1000+ words
- State of the Art (review): 2000+ words
