---
name: manuscript-scribe
description: "Specialized skill for WRITING long-form academic content (Papers, Grants, Reports, Patents, Theses). BYPASSES the chat output limit by writing directly to local Markdown files, with optional Word (.docx) export. Use when: (1) User asks to write or draft a paper, report, patent, thesis chapter, or computational write-up. (2) User provides bullet points or data and wants sections written to files. (3) User wants to polish or formalize existing sections. Do NOT use for short replies in chat—only when the deliverable is a file."
skill_type: operator
depends_on: mcp-mat-doc
---

<!-- multi-server: mat_sn, mat_doc -->

# Manuscript Scribe Skill

Primary output is **files**. Use only when the deliverable is a **file** (paper, report, section to file), not for answering questions in chat.

## Format profiles

| Profile | Use Case | Min words |
|---|---|---|
| `research_paper` | Standard academic paper (IMRaD) | 3000 |
| `grant` | Grant proposal | 2500 |
| `computational_report` | Lean DFT/MD/simulation write-up | 800 |
| `patent` | Patent application | 3000 |
| `review` | Review article | 6000 |
| `technical_report` | Technical/engineering report | 3000 |
| `thesis_section` | Single thesis chapter | 5000 |

List profiles: `init_manuscript.py --list_formats`. Always pass `--profile` to all scripts. When deep-survey delegates, use `literature_review` profile, not `review`.

## Workflow

1. **Retrieval first** — Run literature search (mat_sn_*, web-search) before any writing. Exception: `computational_report` with user-provided parameters.
2. **Chunked writing** — Draft each section in chunks via `write_section.py` (create + `--append`), or build in temp files with `append_chunk.py`, then pass with `--content_file`.
3. **Validate** — `validate_content.py --draft draft.md --profile <profile>`. Fix sections below minimum word count.
4. **Assemble** — `assemble_manuscript.py --sections_dir sections/ --output final.md --validate --profile <profile>`. Runs consistency checks (terms, abbreviations, references). Auto-exports to `.tex`+`.bib` and `.docx` (`--export all`).
5. **Polish** — `polish_text.py --file <assembled> --target_section <Name> --use_llm` for point-by-point revision.

**Search → summarize → append** per-section flow: after each search, agent LLM summarizes with citations → `append_chunk.py` → repeat → pass temp file to `write_section.py`.

## Scripts

| Script | Purpose | Key args |
|--------|---------|----------|
| `init_manuscript.py` | Create outline | `--title "..." --template <profile>` (--title required) |
| `write_section.py` | Write/append section | `--section "Name" --content_file <path> --draft draft.md [--append] [--profile]` |
| `append_chunk.py` | Accumulate temp content | `--path "_tmp/section_X.md" --content "..."` |
| `validate_content.py` | Quality gate | `--draft draft.md --profile <profile> [--planner_mode]` |
| `assemble_manuscript.py` | Merge + check + export | `--sections_dir sections/ --output final.md --validate --profile <profile>` |
| `run_pipeline.py` | Resumable orchestrator | `--stage <stage> --state _tmp/manuscript/state.json --resume` |
| `polish_text.py` | Grammar/style revision | `--file draft.md --target_section "Name" [--use_llm]` |
| `export_docx.py` | Word export | `--input final.md --output manuscript.docx` |
| `export_latex.py` | LaTeX export | `--input final.md --output manuscript.tex --bibfile refs.bib` |

**Long content**: Always use `--content_file` instead of inline `--content` for sections > 1 paragraph (avoids truncation).

## Citation and references

- **In text**: `[n](URL)` immediately after the relevant claim.
- **References section**: Exactly matching in-text [n] numbers, with full citation and source URL.
- Format details in `citation_and_output_format.md` (already in system prompt).

## Typographic & writing rules

For detailed typographic style, De-AIGC rules, planner mode guidelines, and word count targets, see **`references/typographic_and_writing_rules.md`**.

Key reminders: use `_{text}` for subscripts, `^{text}` for superscripts, en-dash "–" for ranges, minus "−" for negatives. Define every abbreviation at first use. Remove AI filler openers.

## Rules

* **Retrieval first**: Search literature before writing. Do not write from memory only.
* **User uploads (mandatory)**: Fully parse/read every uploaded file before writing.
* **Chunked writing**: Multiple `write_section.py` calls per section (create + --append) or build section in file then pass with --content_file.
* **Profile**: Always pass `--profile` to init, write, validate, and assemble scripts.
* **Validate + assemble**: Run both before finishing. Fix term, abbreviation, reference, and word-count issues.
* Write long content to **files**; one section per call for `write_section.py`.
* **Delivery**: Direct mode = concise summary + file path. Planner mode = full document in chat + finish.
