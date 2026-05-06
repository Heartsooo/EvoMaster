---
name: gromacs
description: "MUST use this skill for ANY task involving GROMACS (classical MD NVT/NPT, energy minimization, free energy perturbation, enhanced sampling, etc.). For system building (solvation, ions), see gromacs-system-prep."
skill_type: operator
---

# GROMACS Skill

GROMACS is a high-performance molecular dynamics package primarily designed for simulations of proteins, lipids, and nucleic acids, but widely used for any system with classical force fields.

## Bohrium Submission Config

| Item | Default Value (CPU) |
|------|---------------------|
| image | `registry.dp.tech/dptech/gromacs:2022.2` |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `gmx grompp -f md.mdp -c conf.gro -p topol.top -o run.tpr && gmx mdrun -v -deffnm run > log 2>&1` |

| Item | GPU Alternative |
|------|-----------------|
| machine | `c6_m60_1 * NVIDIA 4090` |
| cmd | `gmx grompp -f md.mdp -c conf.gro -p topol.top -o run.tpr && gmx mdrun -v -deffnm run -gpu_id 0 > log 2>&1` |

> Adjust `grompp` arguments to match actual filenames.
> For GPU options: `Bohrium(action="list_machines", machine_type="gpu", keyword="4090")`.
> For different GROMACS versions: `Bohrium(action="list_images", keyword="gromacs")`.

## Input Preparation

GROMACS uses three core files: **topology** (`.top`), **coordinates** (`.gro`), and **simulation parameters** (`.mdp`).

### Using render_input.py (for .mdp generation)

```bash
# Generate mdp file
uv run python scripts/render_input.py --software gromacs --task md --output md.mdp
```

### System Building Workflow

For building a complete system from scratch (solvation, ion addition, topology generation), use the **gromacs-system-prep** skill which provides:
- `gmx pdb2gmx` for topology generation
- `gmx solvate` for solvation
- `gmx genion` for ion addition
- `gmx make_ndx` for index groups

### Ready-to-run files

If the user provides `.gro` + `.top` + `.mdp` (or a pre-built `.tpr`), skip preparation.

## Task Types

| Task | Description | Key MDP Settings |
|------|-------------|------------------|
| em | Energy minimization | `integrator = steep`, `emtol`, `nsteps` |
| nvt | NVT equilibration | `integrator = md`, `tcoupl = V-rescale`, `ref_t` |
| npt | NPT equilibration | `tcoupl = V-rescale`, `pcoupl = Parrinello-Rahman`, `ref_p` |
| md | Production MD | `integrator = md`, `nsteps`, `dt`, output frequencies |
| fep | Free energy perturbation | `free_energy = yes`, `init_lambda_state`, `fep_lambdas` |

## Required Files

- **Topology** (`.top`): force field parameters, molecule definitions
- **Coordinates** (`.gro` or `.pdb`): system coordinates, box dimensions
- **MDP file** (`.mdp`): simulation parameters
- **Force field**: referenced in `.top`; typically AMBER, CHARMM, OPLS-AA, GROMOS
- **Index file** (`.ndx`): optional, for custom groups
- **Restraint files** (`.itp`): optional position restraints

## Physical Checks

- **timestep**: 2 fs with LINCS constraints on H-bonds (`constraint_algorithm = lincs`); 1 fs without constraints
- **Thermostat**: V-rescale (`tcoupl = V-rescale`, `tau_t = 0.1`) for equilibration and production
- **Barostat**: Berendsen for equilibration, Parrinello-Rahman for production NPT (`tau_p = 2.0`)
- **Cutoffs**: typically `rcoulomb = 1.0`, `rvdw = 1.0` nm; PME for long-range electrostatics (`coulombtype = PME`)
- **Neighbor list**: `nstlist = 10`, `ns_type = grid`, `verlet-buffer-tolerance` for Verlet scheme
- **Output frequency**: `nstxout-compressed = 5000` (every 10 ps at dt=2fs) for trajectory; `nstenergy = 500` for energy
- **Box size**: minimum image convention requires box dimension > 2 * rcoulomb; check `gmx editconf -d 1.0` padding
- **Periodic boundary conditions**: `pbc = xyz` for standard 3D periodic

## Submission Workflow

1. Prepare system (use gromacs-system-prep skill if building from scratch)
2. Generate/verify MDP: `render_input.py --software gromacs --task md --output md.mdp`
3. Ensure `.gro`, `.top`, `.mdp` are in one directory
4. Submit (the cmd runs both grompp and mdrun):
   `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/gromacs:2022.2", cmd="gmx grompp -f md.mdp -c conf.gro -p topol.top -o run.tpr && gmx mdrun -v -deffnm run > log 2>&1")`
5. Poll: `Bohrium(action="poll", job_id=<id>)`

## Post-Processing

After job completion, use the **md-analysis** skill for trajectory analysis (RMSD, RMSF, gyration radius, MSD, RDF, H-bonds, energy).

## Reference

Official documentation: `site:manual.gromacs.org`
