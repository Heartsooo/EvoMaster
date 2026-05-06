# manuscript-scribe: research_paper profile

**Profile-specific writing rules for `research_paper`.**
These supplement (do not replace) the shared rules in `SKILL.md`.

---

## Overview

The `research_paper` profile covers standard academic papers in IMRaD format (Introduction, Methods, Results, Discussion) or the Nature-style variant (Methods placed after Discussion). Both variants use the same section metadata; reorder at assembly time when targeting Nature-style journals.

---

## Section-specific writing guidance

### Abstract
- One coherent paragraph, not a list.
- Structure: problem statement → approach → key result → bounded significance.
- **No vague claims**: quantify the main result (e.g. "reduces X by 15% compared to Y under conditions Z").
- Nature-style variant: keep ≤200 words; cut every word that does not carry information.

### Introduction
- Open with the **concrete scientific problem**, not with "In recent years, there has been growing interest in X."
- Narrow funnel: broad context (2-3 sentences) → knowledge gap (specific, evidence-backed) → this work's objective (one clear statement).
- Every gap claim must cite the paper(s) that establish the gap.
- Do not spend more than 20% of the Introduction on general background.
- Nature-style variant: introduction is typically 3-5 paragraphs; get to the gap quickly.

### Methods
- Sufficient detail for an expert to reproduce: materials/models, computational or experimental setup, key parameters, analysis techniques.
- Cite method references with `[n](URL)`.
- IMRaD placement: after Introduction. Nature-style: after Discussion.

### Results
- Present findings objectively; describe trends and observations with data.
- Reference every figure and table explicitly: "Figure 1a shows...", "Table 2 lists...".
- Do not interpret here (save that for Discussion); do not make claims beyond what the data directly show.
- Nature-style variant: light interpretation may be woven in — labeled as such.

### Discussion
- Interpret results in context of prior work: what do the data mean, not just what they show.
- Compare with literature: agreements, contradictions, reasons.
- State limitations explicitly.
- End with implications — **scoped**: within this system, for this class of materials, under these conditions.

---

## Merged Nature-style notes

When writing for Nature-family journals:
- Methods section is placed **after Discussion** (handle at assembly with `assemble_manuscript.py --profile research_paper`).
- Abstract ≤200 words; no structured headings within it.
- Introduction is concise (Nature does not have a lengthy review-style intro).
- Results may include light interpretation (Nature style combines Results and Discussion elements more fluidly).
- These are writing-style notes; the `research_paper` profile in `format_profiles.py` supports both orderings.

---

## De-AIGC rules (mandatory — full apply)

Full guide: `Skill action=get_reference reference_name="de_aigc_style_guide.md"` (in `skills/_common/reference/`).

**Non-negotiable for every section:**
1. Lead with the real problem, not broad context.
2. Replace abstract labels (`framework`, `strategy`, `paradigm`) with concrete operations.
3. Calibrate claims: `support`, `indicate`, `constrain` — not `prove`, `establish`, `eliminate`.
4. Remove all filler openers: `Notably,`, `Significantly,`, `Importantly,`, `It is worth noting that`.
5. One main point per sentence.
6. Quantify main results; avoid relative-only claims ("improved performance" → "reduces MAE by 12 meV/atom on benchmark X").

**Delete on sight**: `groundbreaking`, `unprecedented`, `pioneering`, `paves the way for`, `showcasing`, `highlighting`, `fosters`, `unleashes`.

After drafting each section, apply the 5-pass De-AIGC checklist (claim calibration → specificity upgrade → compression → redundancy removal → tone scan).

---

## Formula guidance

- Include equations when they are central to understanding the method or result and are present in your sources.
- Explain every symbol on first appearance: "where *E*_{total} is the total energy, *N* is the number of atoms..."
- Markdown notation: italic for physical quantities `*E*`, subscripts `_{subscript}`, superscripts `^{exponent}`.
- En-dash "–" for ranges (1.88–1.89 Å), minus "−" for negatives (−0.5 eV).
