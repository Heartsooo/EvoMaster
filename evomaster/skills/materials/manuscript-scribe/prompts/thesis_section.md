# manuscript-scribe: thesis_section profile

**Profile-specific writing rules for `thesis_section`.**
These supplement (do not replace) the shared rules in `SKILL.md`.

---

## Overview

The `thesis_section` profile is for a single thesis chapter (or major dissertation section). Thesis writing is more detailed, more pedagogical, and more methodologically transparent than a journal paper. Minimum 5000 words; Literature Review alone must be 1000+ words.

---

## Core principle: teach as well as report

A thesis chapter must be readable by a researcher entering the field, not just by specialists. This means:
- Define concepts that a paper would assume known.
- Explain why methods were chosen (not just which methods were used).
- Discuss limitations and alternatives that were considered but rejected.
- Connect each chapter clearly to the thesis's overall research questions.

---

## Literature Review section (mandatory depth rules)

Minimum **1000 words**. This is the floor, not the target — for most chapters, 1500-2500 words is appropriate.

**Required elements:**
1. **Historical context**: how did the field develop to its current state? Key milestones with dates and citations.
2. **Conceptual foundations**: define and explain every key concept that this chapter builds on. Do not assume the reader knows DFT, molecular dynamics, machine learning potentials, etc.
3. **Prior work directly relevant to this chapter**: organized by theme or chronology. For each group of related work: what was done, what was found, what limitations remained.
4. **Gap identification**: the specific gap(s) that this thesis chapter addresses — stated explicitly and cited to the papers that establish the gap.
5. **Positioning statement**: how this chapter's contribution fills or advances the identified gap.

Do NOT write a Literature Review that is just a list of "Paper X did Y. Paper Z did W." Every paragraph must synthesize and evaluate.

---

## Methodology section (rigor rules)

Minimum **800 words**. Must include:

1. **Justification for each major methodological choice**: why DFT over force fields? Why this functional over others? Why this dataset? State the reasoning, not just the decision.
2. **Comparison with alternatives**: where relevant, name the alternatives considered and explain why they were not used.
3. **Validation approach**: how will results be validated? What benchmarks, experimental comparisons, or convergence tests were applied?
4. **Reproducibility**: sufficient parameter detail (software version, functional, k-mesh, cutoffs, convergence criteria, pseudopotentials) for reproduction.
5. **Formula transparency**: for all key equations, explain every symbol. Use the notation established in the Literature Review consistently.

---

## Formula rules

- Include all key equations used in the methodology and any derived quantities reported in Results.
- Explain every symbol on first appearance.
- Maintain consistent symbol definitions throughout the chapter.
- For computational methods: include the XC functional form, any corrections (Hubbard U, dispersion), and convergence criteria as explicit expressions.

---

## Cross-chapter coherence notes

- Begin Introduction with how this chapter fits into the thesis: "Building on Chapter 2's [finding], this chapter investigates..."
- End Conclusion with how the findings feed forward: "The [result] established here provides the basis for Chapter 4's investigation of..."
- Maintain consistent terminology with adjacent chapters (one concept, one name).

---

## De-AIGC rules (mandatory — full apply)

Full guide: `Skill action=get_reference reference_name="de_aigc_style_guide.md"` (in `skills/_common/reference/`).

**Thesis-specific priorities:**
1. Literature Review: every claim about the field must be cited; no "it is widely accepted that" without citations.
2. Methodology justifications: be concrete — "PBE was chosen because it provides adequate accuracy for metallic bond lengths at lower computational cost than HSE06, as validated by [ref]" not "PBE is a commonly used functional".
3. Results: report observations exactly as shown; do not overinterpret.
4. Discussion: separate what is shown from what is inferred; label inferences explicitly.
5. Limitations section (within Discussion or Conclusion): required — state what the methods or data do not allow you to conclude.

After drafting each section, apply the 5-pass De-AIGC checklist: claim calibration → specificity upgrade → compression → redundancy removal → tone scan.
