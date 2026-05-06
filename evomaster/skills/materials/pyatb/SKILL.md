---
name: pyatb
description: "MUST use this skill for ANY task involving PyATB (band structure unfolding, Berry phase, topological invariants, transport properties, and other tight-binding post-processing of ABACUS LCAO output HR.dat/SR.dat)."
skill_type: operator
---

# PyATB Skill

PyATB (Python Ab initio Tight-Binding) is a post-processing tool that reads Hamiltonian and overlap matrices from ABACUS LCAO calculations (HR.dat, SR.dat) to compute band structure, Berry phase, topological properties, and transport coefficients.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | *(query first: `Bohrium(action="list_images", keyword="pyatb")`)* |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `python run_pyatb.py > log 2>&1` |

> **Always query the image before submitting**: `Bohrium(action="list_images", keyword="pyatb")`. Do not assume a default image address; PyATB images may change frequently.

## Input Preparation

PyATB uses Python scripts, similar to PySCF. No `render_input.py` or `diagnose_input.py` step is needed.

### Prerequisites

PyATB requires output from a prior **ABACUS LCAO** calculation:
- `HR.dat` — Hamiltonian matrix in real space
- `SR.dat` — Overlap matrix in real space
- `rR.dat` — Position matrix (optional, for Berry phase)
- `kpoints` — k-point information (optional)

These files are produced by ABACUS when `out_mat_hs2 1` (or `out_mat_hs 1`) is set in the INPUT file.

### Script Structure

```python
import pyatb

# 1. Initialize from ABACUS output
tb = pyatb.TB(
    hr_file='HR.dat',
    sr_file='SR.dat',
    rr_file='rR.dat',  # optional
)

# 2. Compute band structure along k-path
kpath = [
    [0.0, 0.0, 0.0],  # Gamma
    [0.5, 0.0, 0.0],  # X
    [0.5, 0.5, 0.0],  # M
    [0.0, 0.0, 0.0],  # Gamma
]
bands = tb.get_band_structure(kpath, npoints=100)

# 3. Write results
import numpy as np
np.savetxt('bands.dat', bands)
print("Band structure calculation complete")
```

## Typical Calculations

| Task | Description | Key Methods |
|------|-------------|-------------|
| Band structure | Electronic band along k-path | `get_band_structure(kpath, npoints)` |
| Band unfolding | Unfold supercell bands to primitive cell | `get_unfolded_bands(...)` |
| Berry phase | Berry phase along a k-path loop | `get_berry_phase(...)` |
| Chern number | Topological invariant (2D) | `get_chern_number(...)` |
| Z2 invariant | Z2 topological index | `get_z2(...)` |
| DOS | Density of states | `get_dos(...)` |
| Transport | Conductivity / Seebeck / Hall | `get_transport(...)` |

## Required Files

- **Python script** (`.py`): the PyATB calculation script
- **HR.dat**: Hamiltonian matrix from ABACUS LCAO run
- **SR.dat**: Overlap matrix from ABACUS LCAO run
- **rR.dat** (optional): Position matrix for Berry phase calculations
- **Lattice information**: either embedded in script or read from ABACUS output

## Submission Workflow

This is a two-step workflow (ABACUS → PyATB):

**Step 1 — ABACUS LCAO calculation** (use `abacus` skill):
1. Set `basis_type lcao` in INPUT
2. Set `out_mat_hs2 1` to output HR.dat and SR.dat
3. Submit via `Bohrium(action="submit", ...)` and wait for completion
4. Download results via `Bohrium(action="poll", job_id=<id>)`

**Step 2 — PyATB post-processing**:
1. Write PyATB script (`run_pyatb.py`)
2. Place script + HR.dat + SR.dat (+ rR.dat if needed) in one directory
3. Query image: `Bohrium(action="list_images", keyword="pyatb")`
4. Submit: `Bohrium(action="submit", input_dir="<dir>", image="<pyatb_image>", cmd="python run_pyatb.py > log 2>&1")`
5. Poll: `Bohrium(action="poll", job_id=<id>)`

## Physical Checks

- **ABACUS output completeness**: verify HR.dat and SR.dat exist and are non-empty before submitting PyATB job
- **Lattice vectors**: must be consistent between ABACUS and PyATB
- **K-path**: should follow the crystal system's Brillouin zone high-symmetry points
- **Memory**: large systems (many orbitals) may require significant memory for matrix operations

## Reference

PyATB repository: https://github.com/pyatb/pyatb
ABACUS documentation: `site:abacus.deepmodeling.com`
