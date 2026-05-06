---
name: proposal-review
description: "Review and evaluate research proposals or project plans. Produces structured scorecards, rationale documents, risk assessments, and funding recommendations. Load for any proposal/project evaluation task."
skill_type: operator
---

# Proposal Review Skill

Structured evaluation of research proposals, project plans, and funding applications. Produces scorecards, rationale documents, and risk mitigation plans.

## When to use

* "Review / evaluate this proposal" → full review workflow below
* "Score this project plan" → scorecard generation
* "Assess risks of this project" → risk analysis + mitigation

## Review Workflow

1. **Read** the proposal document thoroughly before scoring.
2. **Score** each dimension per the evaluation policy. Each sub-score rationale must cite ≥ 2 specific evidence points from the proposal text.
3. **Write deliverables**: scorecard JSON, rationale Markdown, risk mitigation JSON (or as task specifies).
4. **Verify**: All files exist with correct filenames; JSON files are parseable; all task-required keys present.

## Standard Chinese Academic Review Vocabulary

When writing reviews in Chinese, use the following standard terms consistently:

| Concept | Standard term | Avoid |
|---------|--------------|-------|
| Feasibility / executability | **可行性** and **可执行性** (use both; 可执行性 for operational-level concerns) | 可做性 |
| Project establishment / approval | **立项** (e.g., "是否建议立项", "立项依据") | 启动项目 |
| Innovation | **创新性** | 新颖性 (acceptable but less formal) |
| Importance / significance | **重要性** | 意义 (acceptable as supplement) |
| Funding recommendation | **资助建议** / **立项建议** | — |

**Hard rule**: When reviewing feasibility, always discuss 可执行性 (operational executability) as a distinct concern from general 可行性 — specifically address whether the proposed methods, resources, and timeline allow the project to actually be executed. When giving funding recommendations, use the term 立项 (e.g., "建议立项" or "不建议立项" or "建议有条件立项").

## Rationale Document Guidance

* Each scoring dimension must have ≥ 2 evidence-grounded arguments.
* Explicitly name risk points with severity ratings.
* Include an improvement suggestions section.
* Discuss 可执行性 alongside general 可行性 in the feasibility section — cover resource requirements, team capability, timeline realism, and technical risk mitigation specifically from an operational execution perspective.
* Include a 立项 recommendation tied to the overall score and risk assessment.

## Deliverable Format Requirements

* **Scorecard JSON**: Must contain all scoring dimensions as top-level keys with numeric values within the specified range. Include `total_score` and `recommendation` (e.g. "建议立项" / "不建议立项" / "建议有条件立项").
* **Rationale Markdown**: Structured sections per dimension; each section cites ≥ 2 specific evidence points from the proposal. Must include separate 可行性 and 可执行性 assessments.
* **Risk assessment JSON** (if required): Top-level `risks` array with `{description, severity, mitigation}` objects.
* **Always write all required deliverable files before reporting task completion.** Check filenames match the task specification exactly.

## Rules

* All conclusions must be traceable to the proposal text. Do not invent facts or cite external knowledge not in the document.
* Respect the score ranges specified in the evaluation policy.
* JSON deliverables must have all task-specified keys at the top level.
* **Completeness check**: Before finishing, list all files in the workspace and verify every required deliverable exists with correct filename and valid content (JSON parseable, Markdown non-empty).
