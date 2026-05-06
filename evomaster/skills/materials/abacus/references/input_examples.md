# ABACUS Complete INPUT Examples

## Quick Reference: Mandatory Parameters by Task Type

Always include **universal baseline**: `calculation`, `basis_type`, `ecutwfc`, `scf_thr`, `scf_nmax`, `smearing_method`, `smearing_sigma`.
> **Basis-aware default**: `ecutwfc 100` is the standard baseline for `basis_type lcao`; for `basis_type pw`, prefer `ecutwfc 50` unless PP/system-specific convergence tests require higher values.

| Task | Additional mandatory parameters | Common omission |
|------|---------------------------------|-----------------|
| SCF (pre-NSCF) | `out_chg 1` | Forgetting `out_chg` → NSCF cannot read charge |
| Band (NSCF) | `init_chg file`, `out_band 1`, `nbands`, `symmetry 0` | Leaving `symmetry 1` → k-path folded |
| DOS (NSCF) | `init_chg file`, `out_dos 1`, `dos_edelta_ev`, `dos_sigma`, `dos_nche`, `nbands`, `symmetry 0` | Missing `dos_nche` for LCAO |
| Relax | **`cal_force 1`**, `force_thr_ev 0.01`, `relax_nmax 100` | Missing `cal_force` → no force output |
| Cell-relax | **`cal_force 1`**, **`cal_stress 1`**, `force_thr_ev 0.01`, `stress_thr 0.5`, `relax_nmax 100` | Missing `cal_force` or `cal_stress` → relaxation silently broken |
| Work function / dipole | `out_pot 2`, `efield_flag 1`, `dip_cor_flag 1`, `efield_dir <vacuum>`, `efield_amp 0.0` | Missing `efield_amp 0.0` (pure dipole correction) |
| Spin-polarized | `nspin 2`, `mixing_beta 0.1`, `mixing_ndim 20`, `mixing_gg0 1.5` | Omitting mixing params → SCF diverges |
| Slab KPT | Always `1` in vacuum direction (e.g. `20 20 1 0 0 0`) | Using dense mesh in vacuum direction |
| Supercell / vacancy / defect / BSSE | **`kspacing` in INPUT** (e.g. `kspacing 0.10`) | Using fixed KPT mesh for variable-size supercells |

> **⚠ `force_thr_ev` vs `force_thr`**: Always use `force_thr_ev` (unit: eV/Å). The parameter `force_thr` uses Ry/Bohr — completely different units. `force_thr_ev 0.01` ≈ `force_thr 3.9e-4`. Mixing them up produces absurdly loose or tight thresholds.

> **⚠ Supercell k-points**: For **any supercell** (vacancy, defect, BSSE ghost atoms, adsorption), always use `kspacing` inside INPUT instead of a separate KPT file. This guarantees uniform k-point density that automatically adapts to cell size. Value: `0.10` Å⁻¹ for metals, `0.12`–`0.15` for insulators. For slab supercells: `kspacing 0.10 0.10 1.00` (z=vacuum).

### Relaxation INPUT Example
```
INPUT_PARAMETERS
calculation relax
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 100
smearing_method gauss
smearing_sigma 0.01
cal_force 1
force_thr_ev 0.01
relax_nmax 100
```

### Cell Relaxation INPUT Example
```
INPUT_PARAMETERS
calculation cell-relax
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 100
smearing_method gauss
smearing_sigma 0.01
cal_force 1
cal_stress 1
force_thr_ev 0.01
stress_thr 0.5
relax_nmax 100
```
> **Critical**: `cal_force 1` and `cal_stress 1` are BOTH mandatory for cell-relax. Without `cal_force 1`, ABACUS does not compute forces and the optimizer cannot work. Without `cal_stress 1`, cell vectors are not optimized. These are NOT implied by `calculation cell-relax` — you must include them explicitly.

### BSSE Ghost Atom INPUT Example (Bulk / Supercell)
```
INPUT_PARAMETERS
calculation scf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 100
smearing_method gauss
smearing_sigma 0.01
kspacing 0.10
```
> Use `kspacing` (not a KPT file) for supercell/vacancy/BSSE calculations.
> For magnetic systems, add `nspin 2` and tune mixing parameters (`mixing_beta`, `mixing_ndim`, `mixing_gg0`) for convergence.

### BSSE Ghost Atom INPUT Example (Slab)
Same as above, but set the vacuum direction of kspacing to `1.00`:
```
kspacing 0.10 0.10 1.00
```

### Work Function / Electrostatic Potential INPUT Example
```
INPUT_PARAMETERS
calculation scf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 100
smearing_method gauss
smearing_sigma 0.01
out_pot 2
efield_flag 1
dip_cor_flag 1
efield_dir 2
efield_pos_max 0.0
efield_pos_dec 0.1
efield_amp 0.0
```
Slab KPT for work function (z = vacuum): `20 20 1 0 0 0`

---

## Two-Step Electronic Property Workflow

Electronic property calculations (band structure, DOS) require: SCF → NSCF.

### Step 1: SCF INPUT (charge density output)
```
INPUT_PARAMETERS
calculation scf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 100
smearing_method gauss
smearing_sigma 0.01
out_chg 1
```
> `out_chg 1` is **mandatory** — writes `SPIN1_CHG.cube` to `OUT.ABACUS/`. Without it, NSCF has no charge density to read.

SCF KPT (uniform Monkhorst-Pack):
```
K_POINTS
0
Gamma
8 8 8 0 0 0
```

### Step 2a: NSCF Band Structure INPUT
```
INPUT_PARAMETERS
calculation nscf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 300
init_chg file
out_band 1
nbands 40
symmetry 0
smearing_method gauss
smearing_sigma 0.01
```

**Required NSCF parameters** (ALL must be included):

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `init_chg` | `file` | Read converged charge from SCF. **Without this, NSCF re-runs SCF from scratch.** |
| `out_band` | `1` | Write band eigenvalues to `BANDS_1.dat` |
| `nbands` | integer | Bands to compute: `total_electrons/2 + 20` (insulator) or `×1.5` (metal) |
| `symmetry` | `0` | **Mandatory for line-mode k-paths.** Symmetry folds/reorders k-points. |

Band structure KPT (line mode, example FCC):
```
K_POINTS
4
Line
0.000  0.000  0.000  40  // Gamma
0.500  0.000  0.000  40  // X
0.500  0.500  0.000  40  // M
0.000  0.000  0.000  1   // Gamma
```

### Step 2b: NSCF DOS INPUT
```
INPUT_PARAMETERS
calculation nscf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 300
init_chg file
out_dos 1
dos_edelta_ev 0.01
dos_sigma 0.07
dos_nche 100
nbands 40
symmetry 0
smearing_method gauss
smearing_sigma 0.01
```

DOS-specific parameters:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `out_dos` | `1` | Write DOS to `DOS1_smearing.dat` |
| `dos_edelta_ev` | `0.01` | Energy grid spacing (eV) |
| `dos_sigma` | `0.07` | Gaussian smearing width (eV) |
| `dos_nche` | `100` | Chebyshev expansion order for LCAO DOS |

DOS KPT — **dense uniform mesh** (NOT line-mode):
```
K_POINTS
0
Gamma
12 12 12 0 0 0
```

### Two-Step File Management on Bohrium

Chain SCF and NSCF in a shell script:
```bash
#!/bin/bash
cp INPUT_scf INPUT
cp KPT_scf KPT
OMP_NUM_THREADS=1 mpirun -np 16 abacus
cp INPUT_nscf INPUT
cp KPT_nscf KPT
OMP_NUM_THREADS=1 mpirun -np 16 abacus
```

**Input directory must contain**: `INPUT_scf`, `INPUT_nscf`, `KPT_scf`, `KPT_nscf`, `STRU`, `.upf`, `.orb`, `run.sh`.
**Submit**: `--cmd "bash run.sh > log 2>&1"`
> **Critical**: NSCF reads `OUT.ABACUS/SPIN1_CHG.cube` from SCF. Both steps must share the same directory.

---

## Band Structure for 1D/2D Systems

**1D nanoribbon** (periodic along y):
```
K_POINTS
2
Line
0.000  0.000  0.000  100  // Gamma
0.000  0.500  0.000  1    // Y
```
Dense interpolation (80-120 pts/segment). K-path follows periodic direction only.

**2D materials** (graphene, MoS2, hexagonal BZ):
```
K_POINTS
4
Line
0.000  0.000  0.000  40  // Gamma
0.500  0.000  0.000  40  // M
0.333  0.333  0.000  40  // K
0.000  0.000  0.000  1   // Gamma
```

---

## Multi-File Generation for Comparative Studies

### Surface Energy (bulk + slab)
- `INPUT_bulk_relax`: `calculation cell-relax` — equilibrium bulk energy
- `INPUT_slab5`, `INPUT_slab7`: `calculation relax` — different slab thicknesses
- `KPT_bulk`: dense 3D (e.g. `20 20 20 0 0 0`)
- `KPT_slab`: dense in-plane, 1 in vacuum (e.g. `20 20 1 0 0 0`)
- Keep `basis_type`, `ecutwfc`, `smearing_method`, `smearing_sigma` consistent across all.

### Vacancy Formation Energy
- `INPUT_bulk`: reference bulk energy
- `INPUT_slab_clean`: pristine surface
- `INPUT_slab_vac`: surface with vacancy
- Use consistent parameters across all.

### KPT for Slab Calculations
- In-plane: dense mesh. **Minimum `12 12` for metals** (hard floor — do not use less); `20 20` for production-quality surface energy.
- Vacuum direction: **always `1`**. Never more than 1 k-point.
- `kspacing` mode: `kspacing 0.10 0.10 1.00` (slab, z=vacuum). Bulk: `kspacing 0.10`.

---

## Multi-File Consistency Rules

When generating multiple INPUT files for a comparative study (surface energy, vacancy formation, EOS, etc.):

1. **All INPUT files must share identical**: `basis_type`, `ecutwfc`, `smearing_method`, `smearing_sigma`, `scf_thr`. Use exactly the same values — do not vary these between bulk and slab.
2. **Each INPUT must reference its STRU and KPT files**: add `stru_file <name>` and `kpoint_file <name>` **in every INPUT file**. This is mandatory whenever the workspace contains multiple STRU/KPT files or uses non-default names. ABACUS defaults to looking for files named `STRU` and `KPT` — if your files are named differently (e.g. `bulk.stru`, `KPT_slab`), ABACUS will fail silently.
3. **Task-specific mandatory params still apply**: a `cell-relax` INPUT inside a multi-file set still needs `cal_force 1`, `cal_stress 1`, `force_thr_ev`, `stress_thr`, `relax_nmax`. A `relax` INPUT still needs `cal_force 1`, `force_thr_ev`, `relax_nmax`. **These are NEVER implied by `calculation`** — you must write them explicitly.
4. **Recommended standard values** for consistency: `scf_thr 1.0e-7`, `smearing_method gauss`, `smearing_sigma 0.01`.

## Low-Cost / Benchmark Mode Guidance (PW)

When a task requests "low-cost", "benchmark", or "minimal cost" parameters:

- **`ecutwfc`**: reduce significantly from the production default (e.g. use roughly 1/3 to 1/2 of the standard 50 Ry). The exact value depends on the pseudopotential.
- **k-points**: reduce density or use Gamma-only where the task allows.
- **Convergence thresholds** (`scf_thr`, `stress_thr`, `force_thr_ev`): keep at physically reasonable values — "low-cost" means cheaper basis, not looser convergence.
- **`relax_nmax`**: keep ≥ 50 to ensure the optimizer has enough steps.

---

## File Reference Rule — CRITICAL

**Every non-default filename must be explicitly referenced in INPUT.** Common mistakes:
- ❌ STRU file is `mo_bulk.stru` but INPUT has no `stru_file` → ABACUS looks for `STRU`, fails
- ❌ KPT file is `KPT_slab` but INPUT has no `kpoint_file` → ABACUS looks for `KPT`, fails
- ❌ Two-step workflow: created `KPT_band` for NSCF but forgot to create `KPT_scf` for SCF → SCF INPUT references `kpoint_file KPT_scf` which doesn't exist
- ✅ Always: `stru_file <exact_filename>` and `kpoint_file <exact_filename>` in every INPUT

---

## Common Mistakes Checklist

Before finalizing any INPUT file, verify none of these apply:

- ❌ `cell-relax` without `cal_force 1` → optimizer has no forces, **silently broken** (most common error)
- ❌ `cell-relax` without `cal_stress 1` → cell vectors not optimized
- ❌ `relax` without `cal_force 1` → same problem, forces not computed
- ❌ Using `force_thr` (Ry/Bohr) instead of `force_thr_ev` (eV/Å) → wrong units
- ❌ SCF feeding NSCF but missing `out_chg 1` → NSCF fails to read charge
- ❌ NSCF with `symmetry 1` → k-path folded, wrong band plot
- ❌ Slab KPT with >1 in vacuum direction → wasted computation, wrong physics
- ❌ Multi-file set with inconsistent `ecutwfc` or `smearing_sigma` → invalidates energy differences
- ❌ **STRU/KPT file named non-default but INPUT missing `stru_file`/`kpoint_file`** → ABACUS looks for `STRU`/`KPT`, fails silently
- ❌ **Two-step workflow with only one KPT file** → SCF needs uniform mesh KPT, NSCF needs line-mode KPT; must create both
- ❌ **INPUT references a file that doesn't exist** → always list workspace files and verify every referenced filename exists
