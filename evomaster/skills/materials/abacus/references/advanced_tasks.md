# ABACUS Advanced Task Templates

Reference for multi-step and specialized ABACUS workflows not covered by `input_examples.md`.

## Basis Type Detection from STRU

**Rule**: Always read the provided STRU file to determine `basis_type`:

| STRU contains `NUMERICAL_ORBITAL`? | `basis_type` | `ecutwfc` default |
|------------------------------------|-------------|-------------------|
| Yes (`.orb` files listed)          | `lcao`      | `100`             |
| No                                 | `pw`        | `50`              |

**Procedure**:
1. Open the provided STRU file
2. Search for the keyword `NUMERICAL_ORBITAL`
3. If present → `basis_type lcao`, `ecutwfc 100`
4. If absent → `basis_type pw`, `ecutwfc 50`

> **Critical**: Never guess. Always read the STRU first. Using `pw` with a STRU that lists orbitals wastes them; using `lcao` without orbital files causes a crash.

---

## Surface Energy Workflow

**Goal**: γ = (E_slab − n × E_bulk) / (2A)

**Files to generate**:

| File | Purpose |
|------|---------|
| `INPUT_bulk` | Bulk cell-relax → equilibrium E_bulk |
| `STRU_bulk` | Bulk unit cell |
| `KPT_bulk` | Dense 3D mesh (e.g., `12 12 12 0 0 0`) |
| `INPUT_slab` | Slab relax → E_slab |
| `STRU_slab` | Slab supercell with ≥15 Å vacuum |
| `KPT_slab` | Dense in-plane, 1 in vacuum (e.g., `12 12 1 0 0 0`) |
| `run.sh` | Chains bulk then slab calculation |

**INPUT_bulk** (cell-relax):
```
INPUT_PARAMETERS
calculation     cell-relax
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-7
scf_nmax        100
smearing_method gauss
smearing_sigma  0.01
cal_force       1
cal_stress      1
force_thr_ev    0.01
stress_thr      0.5
relax_nmax      100
stru_file       STRU_bulk
kpoint_file     KPT_bulk
```

**INPUT_slab** (relax):
```
INPUT_PARAMETERS
calculation     relax
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-7
scf_nmax        100
smearing_method gauss
smearing_sigma  0.01
cal_force       1
force_thr_ev    0.01
relax_nmax      100
stru_file       STRU_slab
kpoint_file     KPT_slab
```

**Consistency**: Both INPUTs must share identical `basis_type`, `ecutwfc`, `smearing_method`, `smearing_sigma`, `scf_thr`.

---

## Vacancy Formation Energy Workflow

**Goal**: E_vac = E_defect − (N−1)/N × E_perfect

**Files to generate**:

| File | Purpose |
|------|---------|
| `INPUT_perfect` | Pristine supercell SCF/relax |
| `STRU_perfect` | Supercell (e.g., 2×2×2) |
| `INPUT_vacancy` | Supercell with one atom removed |
| `STRU_vacancy` | Vacancy supercell + ghost atom (LCAO) |

For **LCAO** vacancy calculations, include BSSE ghost atoms at the vacancy site. See `stru_format.md` for ghost atom STRU syntax.

**Shared INPUT** (adapt `stru_file` per case):
```
INPUT_PARAMETERS
calculation     relax
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-7
scf_nmax        100
smearing_method gauss
smearing_sigma  0.01
cal_force       1
force_thr_ev    0.01
relax_nmax      100
kspacing        0.10
```

For magnetic systems, add `nspin 2` and tune mixing parameters (`mixing_beta`, `mixing_ndim`, `mixing_gg0`) for convergence.

> Remember: `ntype` in INPUT must include the ghost species.

---

## EOS / Bulk Modulus Workflow

**Goal**: Fit E(V) to Birch-Murnaghan EOS → equilibrium V₀ and bulk modulus B₀.

**Procedure**:
1. Start from the provided or relaxed structure
2. Generate 5–7 structures at volumes: V₀ × {0.94, 0.96, 0.98, 1.00, 1.02, 1.04, 1.06}
3. Scale all lattice vectors uniformly by factor (V_target / V₀)^(1/3)
4. Run SCF at each volume with identical INPUT parameters
5. Collect total energies → fit to 3rd-order Birch-Murnaghan EOS

**Files per volume point** (e.g., v094 … v106):
- `STRU_v094`, `STRU_v096`, …, `STRU_v106` — scaled lattice vectors, same fractional coords
- One shared `INPUT_eos` (set `stru_file` per run via `run.sh`)
- One shared `KPT` file (dense uniform mesh)

**INPUT_eos**:
```
INPUT_PARAMETERS
calculation     scf
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-7
scf_nmax        100
smearing_method gauss
smearing_sigma  0.01
cal_stress      1
kpoint_file     KPT
```

> `cal_stress 1` verifies pressure at each volume (recommended).
> Use identical numerics across ALL volume points.

---

## DFT+U Calculations

ABACUS supports DFT+U (Dudarev simplified) for correlated systems.

**INPUT additions**:
```
dft_plus_u      1
orbital_corr    2 -1
hubbard_u       5.0 0.0
```

**Parameter rules**:
- `orbital_corr`: angular momentum per species in ATOMIC_SPECIES order. `-1` = no correction, `1` = p, `2` = d, `3` = f.
- `hubbard_u`: U value (eV) per species, same order. `0.0` for species without +U.
- Common U values: transition metal 3d → U ≈ 3–5 eV (system-dependent).
- DFT+U often needs tighter convergence: `scf_thr 1.0e-8`, `scf_nmax 200`.

**Example** (Fe₂O₃: Fe with U on d-orbitals, O without):
```
INPUT_PARAMETERS
calculation     scf
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-8
scf_nmax        200
smearing_method gauss
smearing_sigma  0.01
nspin           2
mixing_beta     0.1
mixing_ndim     20
dft_plus_u      1
orbital_corr    2 -1
hubbard_u       5.0 0.0
```

> `orbital_corr 2 -1`: Fe → d-orbital correction (l=2); O → none (l=−1).

---

## Phonon Calculations (Finite Displacement)

ABACUS does not have built-in DFPT phonons. Use the finite-displacement method with Phonopy.

**Workflow**:
1. **Relax** the structure (cell-relax → equilibrium geometry)
2. Generate displaced supercells: `phonopy -d --dim 2 2 2 --abacus`
3. Run SCF on each displaced structure to get forces
4. Collect forces: `phonopy --abacus -f disp-*/OUT.ABACUS/running_scf.log`
5. Post-process: `phonopy -p band.conf`

**INPUT for each displaced structure**:
```
INPUT_PARAMETERS
calculation     scf
basis_type      lcao
ecutwfc         100
scf_thr         1.0e-8
scf_nmax        100
smearing_method gauss
smearing_sigma  0.005
cal_force       1
kspacing        0.10
```

> `cal_force 1` is critical — Phonopy reads forces from the log.
> Tighter `scf_thr` (1.0e-8) and smaller `smearing_sigma` (0.005) for accurate forces.
> `kspacing` adapts automatically to supercell size.
