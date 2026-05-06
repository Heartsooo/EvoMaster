---
name: abinit
description: "MUST use this skill for ANY task involving ABINIT (ground-state SCF, structural relaxation, DFPT response functions, NLO/SHG workflows, etc.)."
skill_type: operator
---

# ABINIT Skill

ABINIT is an open-source suite for first-principles calculations using DFT, DFPT (density-functional perturbation theory), and many-body perturbation theory. It supports plane-wave and PAW methods with norm-conserving and PAW pseudopotentials.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | `registry.dp.tech/dptech/dp/native/prod-19853/abinit:v9.10.3_pp` |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1 OMP_NUM_THREADS=1 mpirun -np 32 abinit {input_file} > log 2>&1` |

> **Container runs as root**: `OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1` are mandatory, otherwise mpirun refuses to start.
> `OMPI_MCA_rmaps_base_oversubscribe=1` prevents "not enough slots" errors when the container reports fewer slots than `-np`.
> Replace `{input_file}` with the actual `.abi` filename.

## Input Preparation

ABINIT input files use a flat keyword-value format with optional multi-dataset syntax (`ndtset`, `*1`, `*2` suffixes).

### Using render_input.py (recommended)

```bash
# Generate input
uv run python scripts/render_input.py --software abinit --task gs_scf --output run.abi [--structure structure.cif]

# Validate
uv run python scripts/diagnose_input.py --software abinit --input run.abi
```

### Ready-to-run input file

If the user provides a complete `.abi` file, skip preparation and submit directly.

## Task Types

| Task | Description | Key Parameters |
|------|-------------|----------------|
| gs_scf | Ground-state SCF | ecut, nband, ngkpt, toldfe |
| relax | Structural relaxation | ionmov, optcell, tolmxf, ntime |
| dfpt | Response functions (phonons, dielectric) | rfphon, rfatpol, rfdir |
| nlo | Nonlinear optics / SHG | Multi-dataset workflow; managed by render engine |

## Required Files

- **Input file** (`.abi`): generated or user-provided
- **Structure**: embedded in input (acell, rprim, xred/xcart, znucl, typat, natom, ntypat) or loaded via CIF
- **Pseudopotentials**: referenced by `pseudos` variable; PAW (`.xml`) or norm-conserving (`.psp8`) format. Bundled in the Docker image.

## Physical Checks

- **ecut**: typically 20-50 Ha depending on pseudopotentials; always convergence-test
- **ngkpt**: k-point grid; denser for metals. `kptrlatt` as alternative for non-cubic cells
- **toldfe**: energy convergence threshold, typically 1.0d-10 Ha for production
- **nband**: must be >= number of occupied bands; add extra for metals or unoccupied-state calculations
- **occopt**: `1` for semiconductors/insulators, `3`-`7` for metals with smearing (`tsmear`)
- **Pseudopotential table**: verify all elements have matching PP files; check `znucl` ordering matches `typat`

## Submission Workflow

1. Prepare structure (CIF/POSCAR)
2. Generate: `render_input.py --software abinit --task gs_scf --structure struct.cif --output run.abi`
3. Diagnose: `diagnose_input.py --software abinit --input run.abi`
4. Collect into one directory (run.abi + PP files)
5. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/dp/native/prod-19853/abinit:v9.10.3_pp", cmd="OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1 OMP_NUM_THREADS=1 mpirun -np 32 abinit run.abi > log 2>&1")`
6. Poll: `Bohrium(action="poll", job_id=<id>)`

## Reference

Official documentation: `site:docs.abinit.org`
