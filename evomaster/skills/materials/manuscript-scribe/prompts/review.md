# manuscript-scribe: review profile

**Profile-specific writing rules for `review`.**
These supplement (do not replace) the shared rules in `SKILL.md`.

---

## Overview

The `review` profile is for comprehensive review articles or survey papers. The deliverable is a substantive, multi-section review — not a paper that summarizes a few studies. Every section must be fully developed. Minimum 6000 words across all sections; State of the Art alone should be 2000+ words.

---

## Core principle: depth over brevity

A review article's value is its synthesis, not its speed. Prioritize:
- Quantitative comparisons across studies (not just "Group A did X, Group B did Y").
- Identification of patterns, contradictions, and consensus positions in the field.
- Critical assessment of methodology and evidence quality.
- Actionable gap analysis with ranked priorities.

Do NOT write a review that is just a list of paper summaries. Every paragraph should synthesize across at least 2-3 sources.

---

## State of the Art section (mandatory structure)

This section is the heart of the review. It must be organized into **3-6 subsections** based on thematic, methodological, or chronological grouping — whichever creates the most logical narrative for the topic. Required subsection elements:

1. **Opening subsection**: Define the scope and criteria for inclusion in this review. What is covered, what is deliberately excluded, and why.
2. **Thematic subsections**: Each subsection covers one coherent theme, material class, or methodological approach. Include:
   - Representative studies with specific results (numbers, conditions, method details).
   - Quantitative comparison where possible: table or inline numbers.
   - Critical commentary: what does this work establish, what are its limitations, how does it relate to adjacent work?
3. **Synthesis paragraph at end of each subsection**: "Across these studies, the evidence consistently shows X. However, Y and Z contradict each other, and the discrepancy may arise from [reason]."

Do NOT have a single flat "State of the Art" section with no subsections.

---

## Critical Analysis section

- Identify **consensus positions**: what does the field broadly agree on?
- Identify **contradictions**: where do results or interpretations conflict, and what explains the discrepancy?
- Assess **methodological strengths and weaknesses** across the reviewed work: what biases, limitations, or gaps exist in how the field has approached the problem?
- Identify **knowledge gaps** ordered by impact/urgency: most important first, each gap cited to specific evidence.

---

## Cross-reference with deep-survey output

If the caller provides a `collected.json` or survey report from the `deep-survey` skill:
- Use the evidence cards as the primary source for the State of the Art content.
- Supplement with additional retrieval for gaps not covered by the deep-survey output.
- Do not duplicate the deep-survey workflow — use its output as input, not as a reason to skip retrieval entirely.

---

## Scope and Methodology section

- State explicitly what databases, keywords, date ranges, and inclusion/exclusion criteria were used.
- If a deep-survey `collected.json` was the input source, state this.
- This section establishes the review's methodological credibility.

---

## De-AIGC rules (mandatory — full apply)

Full guide: `Skill action=get_reference reference_name="de_aigc_style_guide.md"` (in `skills/_common/reference/`).

**Review-specific priorities:**
1. Replace "the field has seen significant advances" → cite specific advances with numbers and years.
2. Replace "it is well known that X" → cite the primary paper establishing X.
3. "In summary, ..." outside Conclusion section → delete or move to Conclusion.
4. Synthesis claims must be grounded: "studies consistently show X [1,2,3,4]" not "it is commonly accepted that X".
5. Gap Analysis: every gap must cite evidence that the gap exists; no unsupported "future work needed" statements.

After drafting each section, apply the 5-pass De-AIGC checklist: claim calibration → specificity upgrade → compression → redundancy removal → tone scan.
