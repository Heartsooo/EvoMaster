# manuscript-scribe: patent profile

**Profile-specific writing rules for `patent`.**
These supplement (do not replace) the shared rules in `SKILL.md`.

---

## De-AIGC exception

**De-AIGC rules do NOT apply to the Claims section.** Patent claim language is intentionally formal, repetitive, and structured by convention — "comprising", "wherein", "characterized in that" are required terms, not AI-sounding filler.

De-AIGC **does apply** to: Technical Field, Background Art, Summary of Invention, Detailed Description, and Abstract.

---

## Claims writing (strict rules)

### Structure
1. **Independent claim first**: broadest scope. Must be self-contained — does not reference other claims.
2. **Dependent claims follow**: each narrows the independent claim. Dependent claims MUST reference the claim they depend on by number: "The device of claim 1, wherein..."
3. **One independent claim per inventive concept** is typical; multiple independent claims are allowed but should be logically distinct.

### Language conventions
- Use "comprising" (open-ended — allows additional elements) as the default transition; "consisting of" (closed) only when exact composition is required.
- Present tense for system/device claims: "A system comprising..."
- Method claims: "A method comprising: [gerund phrase]; [gerund phrase]; ..."
- Avoid ambiguity: every technical term used in the claims must be defined in the Detailed Description.
- Functional language ("configured to", "adapted to") is acceptable for device claims but must be supported by structural disclosure in Detailed Description.

### Claim dependency structure example
```
1. A compound comprising [broadest scope].
2. The compound of claim 1, wherein [specific limitation A].
3. The compound of claim 1, wherein [specific limitation B].
4. The compound of claim 2, further comprising [additional limitation].
5. A method of using the compound of claim 1, comprising: [steps].
```

---

## Prior art citation style (Background Art section)

- Cite prior patents as: Patent No. XXXX/XXXXXX (Inventor, Year). Or: US Patent 10,123,456 (Smith et al., 2022).
- Cite prior publications as: Authors, Title, *Journal*, Year, DOI or URL.
- Do NOT use `[n](URL)` hyperlink format for patent citations — use parenthetical or footnote-style.
- State the specific limitation of each cited prior art that the invention overcomes: "Smith (2022) discloses X but does not address Y. The present invention solves Y by..."

---

## Section-specific guidance

### Technical Field
- 1-2 sentences identifying the field: "The present invention relates to [field], in particular to [specific aspect]."

### Background Art
- Describe the state of the art objectively.
- Identify the technical problem clearly: "Existing methods suffer from [specific limitation] when [conditions]."
- Cite relevant prior art with the specific limitation it represents.
- Apply De-AIGC: avoid promotional language about the invention in this section.

### Summary of Invention
- Corresponds to the broadest independent claim in prose form.
- List the key technical advantages over prior art with specificity: "reduces processing time by [X]", "eliminates the need for [Y]".
- Do not make claims here that are not supported by the Detailed Description.

### Detailed Description
- At least one preferred embodiment, with full technical detail: materials, dimensions, conditions, process steps.
- Working examples with data: "In Example 1, compound X was prepared by... The yield was Y%. The melting point was Z°C."
- Enable a skilled person to reproduce the invention without undue experimentation.
- Every term used in Claims must be defined here.
- Apply De-AIGC to narrative prose sections.

### Abstract
- 50-150 words. Brief summary for search/classification.
- Typically mirrors the broadest independent claim in more readable prose.
- No claims language; no "comprising" structure — write as a disclosure summary.
