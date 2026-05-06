---
name: pyscf
description: "MUST use this skill for ANY task involving PySCF (DFT, HF, MP2, CCSD(T), TDDFT, geometry optimization with geomeTRIC, property calculations, and other Python-scripted quantum chemistry workflows)."
skill_type: operator
---

# PySCF Skill

PySCF (Python-based Simulations of Chemistry Framework) is a Python library for quantum chemistry calculations. Unlike input-file-driven codes, PySCF calculations are written as Python scripts, providing maximum flexibility.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | `registry.dp.tech/dptech/dp/native/prod-19853/pyscf-geometric:dev-260305` |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `python {script_name} > log 2>&1` |

> Replace `{script_name}` with the actual Python script name (e.g. `run_pyscf.py`).
> The image includes PySCF + geomeTRIC optimizer.
> For alternative images: `Bohrium(action="list_images", keyword="pyscf")`.

## Input Preparation

PySCF does NOT use input files. Write a Python script directly.

### Script Structure

A typical PySCF calculation script:

```python
from pyscf import gto, scf, dft

# 1. Build molecule
mol = gto.M(
    atom='H 0 0 0; H 0 0 0.74',  # or read from file
    basis='def2-SVP',
    charge=0,
    spin=0,  # 2S, not 2S+1
    verbose=4,
)

# 2. Run calculation
mf = dft.RKS(mol)
mf.xc = 'B3LYP'
energy = mf.kernel()

# 3. Save results
print(f"Total energy: {energy} Hartree")
```

### Loading Structure from File

```python
from pyscf import gto

# From XYZ file (preferred)
mol = gto.M(atom='molecule.xyz', basis='def2-SVP')

# From CIF via pymatgen
from pymatgen.core import Structure
struct = Structure.from_file('structure.cif')
# Convert to PySCF atom format...
```

### No render_input.py

PySCF scripts are Python code; there is no `render_input.py` or `diagnose_input.py` step. Validation is implicit in the script logic.

## Task Types

| Task | PySCF Module | Example |
|------|-------------|---------|
| Single-point DFT | `pyscf.dft` | `dft.RKS(mol).run()` |
| Single-point HF | `pyscf.scf` | `scf.RHF(mol).run()` |
| MP2 | `pyscf.mp` | `mp.MP2(mf).run()` |
| CCSD(T) | `pyscf.cc` | `cc.CCSD(mf).run()` then `.ccsd_t()` |
| TDDFT | `pyscf.tddft` | `tddft.TDDFT(mf).run()` |
| Geometry optimization | `geometric` | `from pyscf.geomopt.geometric_solver import optimize; optimize(mf)` |
| Properties | various | dipole, Mulliken, MO energies, HOMO/LUMO gap |

## Common Parameters

| Parameter | Description | Typical Values |
|-----------|-------------|----------------|
| `basis` | Basis set | `'sto-3g'`, `'def2-SVP'`, `'def2-TZVP'`, `'cc-pVDZ'`, `'aug-cc-pVTZ'` |
| `xc` | DFT functional | `'B3LYP'`, `'PBE'`, `'PBE0'`, `'wB97X-D3'`, `'r2SCAN'` |
| `charge` | Total molecular charge | integer |
| `spin` | 2S (number of unpaired electrons) | 0, 1, 2, ... |
| `verbose` | Output level | 4 (normal), 5 (debug) |
| `max_memory` | Memory limit in MB | 4000 (per 32-core machine: ~4 GB/core) |

## Required Files

- **Python script** (`.py`): the calculation script
- **Structure file** (optional): XYZ (`.xyz`, preferred) or CIF (`.cif`) if not embedding coordinates in script
- **No pseudopotentials needed**: PySCF uses all-electron Gaussian basis sets

## Physical Checks

- **Basis set convergence**: at least def2-SVP for qualitative, def2-TZVP for quantitative results
- **Open-shell**: use `UKS`/`UHF`/`ROHF` for open-shell systems; set `spin` = number of unpaired electrons (NOT 2S+1)
- **SCF convergence**: check `mf.converged`; if False, try `mf.max_cycle = 200` or DIIS tuning
- **Memory**: `mol.max_memory = N` (MB); large basis + many atoms can OOM
- **Symmetry**: `mol.symmetry = True` can speed up but may cause issues; disable if SCF diverges
- **Geometry optimization**: geomeTRIC is pre-installed in the Docker image; use `pyscf.geomopt.geometric_solver.optimize`

## Available Properties

```python
# After mf.kernel() converges:
energy = mf.e_tot                    # Total energy (Hartree)
dipole = mf.dip_moment()             # Dipole moment (Debye)
mo_energies = mf.mo_energy           # MO energies
homo = mf.mo_energy[mf.mo_occ > 0][-1]   # HOMO energy
lumo = mf.mo_energy[mf.mo_occ == 0][0]   # LUMO energy
gap = lumo - homo                    # HOMO-LUMO gap

# Mulliken population
from pyscf import lo
mf.mulliken_pop()
```

## Submission Workflow

1. Write Python script (e.g. `run_pyscf.py`)
2. Prepare structure file (XYZ preferred) if not embedding coordinates
3. Place script + structure in one directory
4. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/dp/native/prod-19853/pyscf-geometric:dev-260305", cmd="python run_pyscf.py > log 2>&1")`
5. Poll: `Bohrium(action="poll", job_id=<id>)`

## Reference

PySCF documentation: https://pyscf.org/user.html
geomeTRIC documentation: https://github.com/leeping/geomeTRIC
