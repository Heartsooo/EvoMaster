---
name: lammps
description: "MUST use this skill for ANY task involving LAMMPS (classical MD, Monte Carlo/GCMC, shock MSST, DeePMD and other machine-learning potentials, etc.)."
skill_type: operator
---

# LAMMPS Skill

LAMMPS (Large-scale Atomic/Molecular Massively Parallel Simulator) is a classical molecular dynamics code with a focus on materials modeling. It supports a wide range of interatomic potentials, force fields, and advanced simulation techniques.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | `registry.dp.tech/dptech/lammps-agent:03810da8` |
| machine | `c16_m64_1 * NVIDIA 4090` (GPU node) |
| cmd | `lmp -in {input_file} > log 2>&1` |

> LAMMPS default image is GPU-enabled (DeePMD support). For CPU-only runs, query `Bohrium(action="list_images", keyword="lammps")` for alternative images.
> Replace `{input_file}` with the actual `.in` or `.lammps` filename.
> GPU node is default because many LAMMPS workflows use DeePMD or GPU-accelerated pair styles.

## Input Preparation

LAMMPS input files are command scripts with directives like `units`, `atom_style`, `pair_style`, `read_data`, `fix`, `run`, etc.

### Using render_input.py

```bash
# Generate input
uv run python scripts/render_input.py --software lammps --task <task_type> --output lammps.in [--structure structure.cif]

# Validate
uv run python scripts/diagnose_input.py --software lammps --input lammps.in
```

Available task templates: `gcmc` (GCMC adsorption), `msst` (shock simulation).

### Ready-to-run input file

If the user provides a complete LAMMPS script, skip preparation and submit directly.

## Task Types

| Task | Template | Description | Key Parameters |
|------|----------|-------------|----------------|
| md | (custom) | Standard NVT/NPT MD | timestep, run steps, fix npt/nvt, thermo |
| gcmc | `gcmc_adsorption.lammps` | Grand canonical Monte Carlo | fix gcmc, chemical_potential, temperature |
| msst | `msst_shock.lammps` | Multi-Scale Shock Technique | fix msst, shock_velocity, direction |
| deepmd | (custom) | ML potential MD | pair_style deepmd, model file path |

## Required Files

- **Input script** (`.in` / `.lammps`): generated or user-provided
- **Data file** (`.data` / `.lmp`): atomic coordinates + topology; referenced by `read_data` command
- **Potential files**: depends on pair_style
  - EAM: `.eam.alloy` or `.eam.fs` files
  - DeePMD: `frozen_model.pb` or `.pth` file
  - ReaxFF: `ffield.reax` parameter file
  - Tersoff/SW: parameter files

## Physical Checks

- **units**: `metal` for most materials science (eV, Angstrom, ps); `real` for organic/bio (kcal/mol, Angstrom, fs)
- **timestep**: typically 1 fs (metal: 0.001 ps) for standard MD; 0.5 fs for reactive or high-T simulations
- **Neighbor list**: `neighbor` skin distance appropriate for pair cutoff
- **pair_style cutoff**: check consistency with the potential; LJ typically 10-12 A, Coulomb needs Ewald/PPPM for periodic
- **Thermostat/barostat**: Nose-Hoover (`fix nvt/npt`) with appropriate Tdamp/Pdamp (typically 100*timestep for T, 1000*timestep for P)
- **Periodic boundaries**: `boundary p p p` for bulk; adjust for surfaces/slabs
- **DeePMD**: verify model covers all elements in the system; check type_map ordering

## Submission Workflow

1. Prepare data file (structure + topology)
2. Generate/write input script
3. Diagnose: `diagnose_input.py --software lammps --input lammps.in`
4. Collect all files (input script + data file + potential files)
5. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/lammps-agent:03810da8", cmd="lmp -in lammps.in > log 2>&1", machine="c16_m64_1 * NVIDIA 4090")`
6. Poll: `Bohrium(action="poll", job_id=<id>)`

> For CPU-only runs (non-GPU pair styles), use `machine="c32_m128_cpu"` and adjust image accordingly.

## Reference

Official documentation: `site:docs.lammps.org`
