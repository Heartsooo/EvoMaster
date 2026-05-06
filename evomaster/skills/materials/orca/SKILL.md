---
name: orca
description: "MUST use this skill for ANY task involving ORCA (DFT, HF, MP2, CCSD(T), DLPNO-CCSD(T), TD-DFT, sTD-DFT, geometry optimization, frequency analysis, and other molecular quantum chemistry calculations)."
skill_type: operator
---

# ORCA Skill

ORCA is an ab initio quantum chemistry program focused on molecular systems. It excels at wavefunction-based methods (CCSD(T), DLPNO-CCSD(T)) and DFT calculations with efficient RI/RIJCOSX approximations. ORCA is particularly strong for molecular spectroscopy, excited states, and high-accuracy thermochemistry.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | `registry.dp.tech/dptech/dp/native/prod-19853/orca:v6.1.1` |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1 /opt/orca611_avx2/orca {input_file} > log 2>&1` |

> ORCA is run via **absolute path** (`/opt/orca611_avx2/orca`), not through mpirun or PATH.
> ORCA handles its own MPI parallelism internally via `%pal nprocs N end` in the input file.
> Replace `{input_file}` with the actual `.inp` filename.

## Input Preparation

ORCA input files use a simple-input-line format: `! method basis keywords` followed by block inputs (`%scf`, `%pal`, `%geom`, etc.) and coordinate specifications (`*xyz charge mult ... *`).

### Using render_input.py (recommended)

```bash
# Generate input
uv run python scripts/render_input.py --software orca --task <task_type> --output input.inp [--structure molecule.xyz]

# Validate
uv run python scripts/diagnose_input.py --software orca --input input.inp
```

### Reference Templates

| Template | Description |
|----------|-------------|
| `minimal_molecule.inp` | Minimal molecular template; coordinates are placeholders |
| `std_dft.inp` | B3LYP/def2-TZVP with RIJCOSX; ground-state DFT baseline |
| `tddft_pbe0.inp` | Full TD-DFT with PBE0/def2-SV(P), TDA disabled |
| `stdft_wb97x-d3.inp` | Simplified TD-DFT (sTD-DFT) wB97X-D3/def2-SV(P); UV/Vis of larger molecules |
| `dlpno_ccsd_t_normal.inp` | DLPNO-CCSD(T) for high-accuracy energetics |

### Ready-to-run input file

If the user provides a complete ORCA `.inp` file, skip preparation and submit directly.

## Task Types

| Task | Description | Key Input Line |
|------|-------------|----------------|
| sp | Single-point energy | `! B3LYP def2-TZVP RIJCOSX` |
| opt | Geometry optimization | `! B3LYP def2-TZVP OPT RIJCOSX` |
| freq | Frequency / thermochemistry | `! B3LYP def2-TZVP FREQ RIJCOSX` |
| opt+freq | Optimize then frequencies | `! B3LYP def2-TZVP OPT FREQ RIJCOSX` |
| tddft | Excited states (full TD-DFT) | `! PBE0 def2-SV(P) RIJCOSX` + `%tddft nroots N end` |
| dlpno | DLPNO-CCSD(T) | `! DLPNO-CCSD(T) def2-TZVP def2-TZVP/C NormalPNO` |

## Required Files

- **Input file** (`.inp`): generated or user-provided
- **Structure**: embedded in input file as `*xyz charge mult ... *` block, or referenced via `*xyzfile charge mult filename.xyz`
- **No external pseudopotentials**: ORCA uses all-electron basis sets; basis set data is built into the binary

## Physical Checks

- **Parallelism**: set `%pal nprocs 32 end` to match machine core count (32 for c32_m128_cpu)
- **Basis set**: def2-SVP for quick tests, def2-TZVP for production, def2-QZVP for benchmark
- **RI approximation**: RIJCOSX or RI-JK for DFT; RI for post-HF. Specify `/C` and `/JK` auxiliary basis sets when using RI explicitly
- **Charge and multiplicity**: first two values after `*xyz`. Verify: total electrons = sum(Z) - charge; multiplicity = 2S+1
- **SCF convergence**: `TightSCF` for production, `VeryTightSCF` for frequency/NMR
- **Memory**: `%maxcore 3500` allocates 3.5 GB per process; adjust based on machine memory / nprocs (128 GB / 32 = 4 GB max per core)
- **TD-DFT**: check `nroots` is sufficient; TDA (Tamm-Dancoff approximation) is default ON, set `TDA false` in `%tddft` for full TD-DFT if needed
- **Open-shell**: use UHF/UKS for doublets/triplets; check `%scf HFTyp UHF end` or use `! UKS` in simple input
- **Large molecules + excited states**: prefer sTD-DFT (simplified TD-DFT) over full TD-DFT for molecules > 100 atoms

## Submission Workflow

1. Prepare molecular structure (XYZ file or embed coordinates in input)
2. Generate: `render_input.py --software orca --task sp --structure molecule.xyz --output input.inp`
3. Diagnose: `diagnose_input.py --software orca --input input.inp`
4. Place input.inp (and .xyz if using xyzfile) in one directory
5. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/dp/native/prod-19853/orca:v6.1.1", cmd="OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1 /opt/orca611_avx2/orca input.inp > log 2>&1")`
6. Poll: `Bohrium(action="poll", job_id=<id>)`

## Reference

Official documentation: `site:www.faccts.de/docs/orca/` or `site:orca-manual.mpi-muelheim.mpg.de`
