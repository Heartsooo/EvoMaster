# ABACUS Troubleshooting Guide

Quick-reference for common ABACUS input generation failures and how to avoid them.

## Top 10 Silent Failures

These are the most common errors that cause ABACUS to fail silently or produce wrong results without obvious error messages.

### 1. Missing `cal_force 1` in relax/cell-relax
**Symptom**: Job completes but positions don't move.
**Fix**: Always include `cal_force 1` for `calculation relax` or `cell-relax`. This is NEVER implied.

### 2. Missing `cal_stress 1` in cell-relax
**Symptom**: Atoms relax but cell vectors stay fixed.
**Fix**: `calculation cell-relax` requires BOTH `cal_force 1` AND `cal_stress 1`.

### 3. STRU/KPT file name mismatch
**Symptom**: ABACUS looks for `STRU` / `KPT` but your files are named differently.
**Fix**: Always add `stru_file <exact_name>` and `kpoint_file <exact_name>` in INPUT when filenames are non-default.

### 4. Missing SCF KPT file in two-step workflow
**Symptom**: SCF step fails because `KPT_scf` doesn't exist.
**Fix**: Create BOTH `KPT_scf` (uniform mesh) and `KPT_band`/`KPT_dos` (line-mode/dense). Each INPUT must reference its own KPT.

### 5. Missing `out_chg 1` in SCF before NSCF
**Symptom**: NSCF with `init_chg file` fails or re-runs SCF from scratch.
**Fix**: SCF INPUT must always have `out_chg 1` when followed by NSCF.

### 6. `symmetry 1` in NSCF band structure
**Symptom**: Band plot shows wrong k-path (folded points).
**Fix**: NSCF INPUT must have `symmetry 0`.

### 7. Using `force_thr` instead of `force_thr_ev`
**Symptom**: Relaxation converges immediately (too loose) or never (too tight).
**Fix**: Use `force_thr_ev` (eV/Å). `force_thr` is in Ry/Bohr — completely different units.

### 8. Fixed KPT mesh for supercells
**Symptom**: Inconsistent k-sampling across different cell sizes.
**Fix**: Use `kspacing` in INPUT for supercell/vacancy/BSSE/defect calculations.

### 9. Inconsistent parameters across multi-file sets
**Symptom**: Energy differences are meaningless.
**Fix**: All INPUT files in a comparative study must share identical `basis_type`, `ecutwfc`, `smearing_method`, `smearing_sigma`, `scf_thr`.

### 10. Missing `ntype` update for ghost atoms
**Symptom**: ABACUS doesn't recognize ghost species.
**Fix**: `ntype` in INPUT must equal total species count (real + ghost). Every ghost species needs entries in both ATOMIC_SPECIES and NUMERICAL_ORBITAL.

## Decision Tree: Which Task Type?

```
Is it a single-point energy?
  → calculation scf

Is it atomic relaxation (fixed cell)?
  → calculation relax
  → MUST ADD: cal_force 1, force_thr_ev 0.01, relax_nmax 100

Is it full cell + position optimization?
  → calculation cell-relax
  → MUST ADD: cal_force 1, cal_stress 1, force_thr_ev 0.01, stress_thr 0.5, relax_nmax 100

Is it band structure or DOS?
  → TWO-STEP: SCF (out_chg 1) → NSCF (init_chg file, symmetry 0)
  → Band: out_band 1, nbands, KPT line-mode
  → DOS: out_dos 1, dos_edelta_ev, dos_sigma, dos_nche, KPT dense uniform

Is it molecular dynamics?
  → calculation md

Is it work function / electrostatic potential?
  → calculation scf + out_pot 2 + dipole correction params
```

## Pre-Flight Checklist (Run Before Submitting)

### For EVERY ABACUS job:
- [ ] PP files (`.upf`) exist and names match ATOMIC_SPECIES in STRU
- [ ] Orbital files (`.orb`) exist and match NUMERICAL_ORBITAL (LCAO only)
- [ ] `basis_type` matches: `lcao` if orbitals present, `pw` if not
- [ ] `LATTICE_CONSTANT 1.8897259886` (Å in Bohr)
- [ ] Species order in ATOMIC_POSITIONS matches ATOMIC_SPECIES
- [ ] `stru_file` / `kpoint_file` in INPUT match actual filenames
- [ ] Every file referenced in INPUT/STRU actually exists in workspace

### For relaxation:
- [ ] `cal_force 1` present
- [ ] `force_thr_ev` (not `force_thr`) present
- [ ] `relax_nmax 100` present
- [ ] For cell-relax: `cal_stress 1` also present

### For two-step (band/DOS):
- [ ] SCF INPUT has `out_chg 1`
- [ ] NSCF INPUT has `init_chg file`, `symmetry 0`, `nbands`
- [ ] TWO separate KPT files created (one for SCF, one for NSCF)
- [ ] Both INPUTs reference their respective KPT files
- [ ] `run.sh` chains SCF → NSCF steps correctly

### For supercell/vacancy/BSSE:
- [ ] `kspacing` in INPUT (not separate KPT file)
- [ ] `ntype` accounts for all species including ghost atoms
- [ ] Ghost species have entries in ATOMIC_SPECIES and NUMERICAL_ORBITAL
- [ ] Ghost atoms have magnetic moment 0.0 and mobility 0 0 0

### For slab calculations:
- [ ] KPT: 1 in vacuum direction (e.g., `20 20 1 0 0 0`)
- [ ] Vacuum ≥ 15 Å (20 Å for work function)
- [ ] If dipole correction needed: `efield_flag 1`, `dip_cor_flag 1`, `efield_amp 0.0`

## Bohrium Submission Quick Reference

```bash
# Standard submission
Bohrium(action="submit",
  input_dir="<dir>",
  image="registry.dp.tech/dptech/abacus:LTSv3.10.1",
  cmd="OMP_NUM_THREADS=1 mpirun -np 16 abacus > log 2>&1",
  machine="c32_m128_cpu")

# Two-step (band/DOS) - use run.sh
Bohrium(action="submit",
  input_dir="<dir>",
  image="registry.dp.tech/dptech/abacus:LTSv3.10.1",
  cmd="bash run.sh > log 2>&1",
  machine="c32_m128_cpu")
```

## PP/Orbital Download

```bash
wget -q "https://store.aissquare.com/datasets/dc875646-a526-41f1-a180-d54b218fc80a/ABACUS-APNS-PPORBs-v1.zip" && unzip -qo ABACUS-APNS-PPORBs-v1.zip
# Then copy needed files:
cp apns-pseudopotentials-v1/<Element>.upf .
cp apns-orbitals-efficiency-v1/<Element>_gga_*au_100Ry_*.orb .  # LCAO only
```
