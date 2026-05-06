---
name: abacus
description: "MUST use this skill for ANY task involving ABACUS (SCF, relax, cell-relax, band structure, DOS, MD, work function, BSSE, vacancy, surface energy, DFT+U, phonon, EOS). Contains hard guards on parameters, low-cost benchmark ranges, K-point rules, and validation scripts that prevent silent failures."
skill_type: operator
---

# ABACUS Skill

ABACUS supports PW and LCAO basis sets. This skill should focus on producing
correct, runnable files and avoiding silent-failure configurations.

## When to Use

Use this skill for any ABACUS task: SCF, band/DOS, relax/cell-relax, MD,
electric-field/dipole, vacancy/defect/supercell, surface/work-function, BSSE.

## Minimum Workflow

1. Read provided `STRU` first and reuse filenames exactly (PP/orbital/structure).
2. Generate `INPUT` (and `KPT` when needed).
3. For uncertain params/workflows, check local `references/*` first.
4. If references are insufficient or ambiguous, use official ABACUS docs on web as fallback.
5. For complex tasks, do not rely only on pretrained priors; gather relevant knowledge from multiple sources to enrich context before finalizing inputs.

## Hard Guards (Must Pass)

- `ntype` in `INPUT` must equal species count in `STRU` `ATOMIC_SPECIES`.
- For `relax`/`cell-relax`/`md`, set `cal_force 1` explicitly.
- For `cell-relax`, also set `cal_stress 1` explicitly.
- For SCF -> NSCF workflows:
  - SCF: `out_chg 1`
  - NSCF: `init_chg file`, `symmetry 0`, `nbands <N>`, plus `out_band 1` or `out_dos 1`
- If file names are not defaults, set `stru_file` and `kpoint_file` to real names.
- Every referenced file must exist in workspace.

## K-point Rules

- Supercell/vacancy/defect/BSSE: prefer `kspacing` in `INPUT` (avoid brittle manual meshes).
- Band structure: use dedicated line-mode KPT for NSCF step.
- SCF and NSCF should not share a single KPT by default in band/DOS workflows.
- Metal slab calculations: **minimum 12×12 in-plane** k-points (or equivalent `kspacing ≤ 0.10` in-plane). Do not use less.

## Parameter Baseline (Use Judgment, Not Blind Fixed Values)

- Use physically reasonable `ecutwfc`, `smearing`, and SCF thresholds for system and PP quality.
- `ecutwfc` (Type: Real): energy cutoff for plane-wave functions. Unit is `Ry`. Even under `basis_type lcao`, `ecutwfc` is still required because local pseudopotential parts and related forces are evaluated in plane-wave representation. Default baseline: `50` (PW), `100` (LCAO), unless task requirements override.
- For fast tasks with lower accuracy requirements, choose lower-precision settings (including lower `ecutwfc`) to prioritize turnaround time.
- Distinguish `LCAO` vs `PW` parameter semantics and sensitivity; do not directly copy basis-specific settings across modes.
- Use `smearing_sigma 0.015` as the default starting point unless the task specifies otherwise.
- For critical parameters, verify intent and physical meaning before finalizing.
- If a parameter meaning is unclear, check the official ABACUS input reference:
  `http://abacus.deepmodeling.com/en/latest/advanced/input_files/input-main.html`.
- Typical production defaults are acceptable, but task requirements override defaults.
- If the task specifies cutoffs or convergence policy, follow the task first.
- **Low-cost / benchmark mode**: when the task requests "low-cost", "benchmark", or "minimal cost" parameters, significantly reduce `ecutwfc` from production defaults. See `references/input_examples.md` for guidance.
- Keep multi-file studies (EOS/surface/vacancy comparisons) consistent on core numerics.

## Task-Specific Deltas

- `relax`: include `force_thr_ev` and `relax_nmax`.
- `cell-relax`: include `force_thr_ev`, `stress_thr`, and `relax_nmax`.
- Work function / slab potential: `out_pot 2`; add dipole correction when needed.
- Spin/noncollinear/SOC: keep `nspin`, `noncolin`, and `lspinorb` consistent.

## Bohrium Submission Defaults

This section is the **single source of truth** for ABACUS `image` / `machine` / `cmd` on Bohrium. Other skills (for example `matmaster/skills/playground-skills/input-manual-helper`) refer here instead of copying the values.

Keep the previous default profile unless task/environment explicitly overrides it.

| Item | Default |
|------|---------|
| image | `registry.dp.tech/dptech/abacus:LTSv3.10.1` |
| machine | `c32_m128_cpu` |
| cmd | `OMP_NUM_THREADS=1 mpirun -np 16 abacus > log 2>&1` |

Notes:
- `-np` is typically half of CPU cores for this profile (32 -> 16).
- For GPU tasks, use environment-approved GPU machine profiles with `basis_type pw`.

## Pre-Submission Validation

After generating all INPUT/STRU/KPT files, run the validation script before Bohrium submission:
```bash
python ${SKILL_DIR}/scripts/validate_input.py --dir <input_dir>
```
It catches the most common silent failures: ntype mismatch, missing cal_force/cal_stress, missing out_chg for SCF→NSCF, wrong basis_type, missing PP/orbital files, and stru_file/kpoint_file reference errors. Fix any FAIL items before submitting.

## References

Reference-first policy:
- Prefer local references below for stable and task-aligned guidance.
- Use official ABACUS/Bohrium web documentation as fallback when local references are insufficient.

- **Pre-flight validator**: `scripts/validate_input.py` — run before every Bohrium submit
- Input templates and multi-step examples: `references/input_examples.md`
- STRU format basics: `references/stru_format.md`
- Multi-species STRU examples: `references/stru_multispecies.md`
- Electric field and dipole notes: `references/electric_field.md`
- Troubleshooting: `references/troubleshooting.md`
- Output parameter guide (files, grep patterns): `references/output_params.md`
- Advanced tasks (surface energy, vacancy, EOS, DFT+U, phonon, basis-type detection): `references/advanced_tasks.md`
- Parsed results and plots after the run: `matmaster/skills/playground-skills/result-analysis` (`parse_abacus.py`, etc.)
