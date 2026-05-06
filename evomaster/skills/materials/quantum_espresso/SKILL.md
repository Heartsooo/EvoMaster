---
name: quantum_espresso
description: "MUST use this skill for ANY task involving Quantum ESPRESSO (pw.x and related executables: SCF, relax, vc-relax, band structure, DOS, phonon calculations, etc.)."
skill_type: operator
---

# Quantum ESPRESSO Skill

Quantum ESPRESSO (QE) is an integrated suite of codes for electronic-structure calculations and materials modeling at the nanoscale, based on DFT, plane waves, and pseudopotentials. The primary executable is `pw.x`.

## Bohrium Submission Config

| Item | Default Value |
|------|---------------|
| image | `registry.dp.tech/dptech/quantum-espresso:7.1` |
| machine | `c32_m128_cpu` (32 cores, 128 GB RAM) |
| cmd | `OMP_NUM_THREADS=1 mpirun -np 32 pw.x -i {input_file} > log 2>&1` |

> Replace `{input_file}` with the actual `.in` or `.pw` filename.
> Match `-np` to the machine core count.
> For a different QE version, query `Bohrium(action="list_images", keyword="quantum-espresso")`.

## Input Preparation

QE input files use Fortran-style namelists (`&CONTROL ... /`, `&SYSTEM ... /`, etc.) followed by card sections (ATOMIC_SPECIES, ATOMIC_POSITIONS, K_POINTS, CELL_PARAMETERS).

### Using render_input.py (recommended)

```bash
# Generate input
uv run python scripts/render_input.py --software qe --task scf --output pw.in [--structure structure.cif]

# Validate
uv run python scripts/diagnose_input.py --software qe --input pw.in
```

### Ready-to-run input file

If the user provides a complete QE input file, skip preparation and submit directly.

## Task Types

| Task | calculation | Description | Key Parameters |
|------|-------------|-------------|----------------|
| scf | `'scf'` | Single-point energy | ecutwfc, ecutrho, conv_thr |
| relax | `'relax'` | Atomic position optimization | forc_conv_thr, nstep |
| vc-relax | `'vc-relax'` | Variable-cell relaxation | press_conv_thr, cell_dofree |
| band | `'bands'` | Band structure (needs prior SCF) | nbnd, K_POINTS crystal_b |
| nscf | `'nscf'` | Non-SCF for DOS (needs prior SCF) | nbnd, denser K_POINTS |

## Required Files

- **Input file** (`.in`): generated or user-provided
- **Structure**: embedded in the input file (ATOMIC_POSITIONS, CELL_PARAMETERS) or loaded from CIF via render
- **Pseudopotentials** (`.upf`): one per element; referenced by `pseudo_dir` in `&CONTROL`. Usually bundled in the Docker image under `/opt/pp/` or `/usr/share/espresso/pseudo/`

## Physical Checks

- **ecutwfc**: typically 40-80 Ry depending on pseudopotentials; always check PP recommendation
- **ecutrho**: for norm-conserving PP, `4 * ecutwfc`; for ultrasoft/PAW, `8-12 * ecutwfc`
- **K_POINTS**: Monkhorst-Pack grid; denser for metals, sparser for large cells. Rule of thumb: k * a ~ 30-50 (a in Angstrom)
- **conv_thr**: typically 1.0d-8 to 1.0d-10 for production SCF
- **Smearing**: required for metals (`smearing = 'mp'` or `'mv'`, `degauss = 0.02`)
- **Pseudopotential consistency**: all PPs must come from the same library (e.g. all SSSP or all PSlibrary)
- **Band structure**: requires prior SCF charge density; specify high-symmetry k-path in `K_POINTS crystal_b`

## Submission Workflow

1. Prepare structure (CIF/POSCAR)
2. Generate: `render_input.py --software qe --task scf --structure struct.cif --output pw.in`
3. Diagnose: `diagnose_input.py --software qe --input pw.in`
4. Collect files into one directory
5. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/quantum-espresso:7.1", cmd="OMP_NUM_THREADS=1 mpirun -np 32 pw.x -i pw.in > log 2>&1")`
6. Poll: `Bohrium(action="poll", job_id=<id>)`

## Reference

Official documentation: `site:www.quantum-espresso.org/Doc/`
