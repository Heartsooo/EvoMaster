---
name: mlips
description: "MUST use this skill for ANY task involving MLIPs (machine-learning interatomic potentials such as DPA, MACE, SevenNet, MatterSim) — structure optimization, phonon, molecular dynamics, elastic constants, NEB, adsorption energy, etc."
skill_type: operator
---

# MLIPs Skill — Machine Learning Interatomic Potentials

MLIPs for atomistic simulations via ASE calculators on Bohrium GPU nodes.

> **Scope: DPA-first.** The default image ships DPA only. Other families (MACE, SevenNet, MatterSim) are supported **via the same unified ASE calculator interface** in `_calculator.py`, but their Python packages are **not preinstalled** — you must install them yourself (see table below) or switch to the multi-family LAMBench image. Treat anything non-DPA as opt-in.

## Bohrium Submission

| Item | Default |
|------|---------|
| image | `registry.dp.tech/dptech/dpa-calculator:e13a296f` (DPA only) |
| machine | `c16_m64_1 * NVIDIA 4090` |
| cmd | `python {script} {args} > log 2>&1` |

> Default image has DPA, ASE, phonopy, pymatgen preinstalled.
> For missing packages, prepend `pip install ... &&`, or activate the bundled env first: `source /mcp_server/AI4S-agent-tools/.venv/bin/activate && pip install <pkg> && python ...`.
> For multi-family work, use the LAMBench image (see `Bohrium(action="list_images", keyword="lambench")`, e.g. `registry.dp.tech/dptech/dp/native/prod-375/lambench:v2.9`).

## Models

| Model | Family | Domain | Install (if not in image) |
|-------|--------|--------|---------------------------|
| **DPA3.1-3M** | DP | General inorganic — **default**, 3M params | preinstalled |
| **DPA3.2-5M** | DP | General + charge/spin, supports `--charge`/`--spin` | preinstalled |
| DPA2.4-7M | DP | Legacy multi-head | preinstalled |
| MACE-MP-0 / MACE-MPA-0 | MACE | General inorganic foundation | `pip install mace-torch` — [ACEsuit/mace](https://github.com/ACEsuit/mace) |
| SevenNet-0 / 7net-mf-ompa | SevenNet | Graph NN | `pip install sevenn` — [MDIL-SNU/SevenNet](https://github.com/MDIL-SNU/SevenNet) |
| MatterSim-v1-5M | MatterSim | General inorganic, 5M params | `pip install mattersim` — [microsoft/mattersim](https://github.com/microsoft/mattersim) |

**DPA heads**: `Omat24` (default, inorganic), `OMol25` (organic), `OC22` (catalysis), `Organic_Reactions`, `ODAC23` (MOFs). Use `--charge`/`--spin` only with DPA3.2-5M.

## Task Scripts

| Script | Usage | Output |
|--------|-------|--------|
| `optimize_structure.py` | `--structure in.cif --model DPA3.1-3M [--head Omat24] [--relax-cell] [--fmax 0.01]` | `*_optimized.cif`, `result.json` |
| `calculate_phonon.py` | `--structure in.cif --model DPA3.1-3M --temperatures 300 600 [--calc-tdos] [--mesh 40]` | `phonon_band.png`, `result.json` |
| `run_molecular_dynamics.py` | `--structure in.cif --model DPA3.1-3M --stages stages.json` | `trajs/*.extxyz`, `final_structure.xyz`, `result.json` |
| `calculate_elastic.py` | `--structure relaxed.cif --model DPA3.1-3M` (input must be relaxed) | `elastic_matrix.csv`, `result.json` |
| `run_neb.py` | `--initial ini.cif --final fin.cif --model DPA3.1-3M [--images 5]` | `neb_band.pdf`, `result.json` |
| `calculate_adsorption.py` | `--slabs s1.cif s2.cif --adsorbates CO H OH --model DPA3.1-3M --head OC22` | `adsorption_results.json` |

**MD stages.json**: `[{"mode": "NVT", "temperature_K": 300, "runtime_ps": 5, "timestep_ps": 0.0005}]`. Modes: NVT, NVT-Berendsen, NVT-Langevin, NPT-aniso, NPT-tri, NVE.

**Adsorption built-in adsorbates**: H, C, O, N, CO, CO2, H2, H2O, OH, OOH, COOH, HCOO, CHO. Copy both `_calculator.py` and `calculate_adsorption.py` to working directory.

## Key Rules

- **Convergence**: `--fmax 0.01` for optimization, `--fmax 0.05` for NEB.
- **Cell relaxation**: `--relax-cell` for equilibrium properties (elastic, phonon).
- **Elastic**: Input MUST be fully relaxed (run optimize first with `--relax-cell`).
- **NEB**: Both structures must be relaxed, same atoms in same order.
- **Chain outputs**: Use `*_optimized.cif` from optimization as input to subsequent tasks. **Save intermediate results** under task filenames before starting next step.

## Submission Workflow

1. Prepare structure (CIF/POSCAR/XYZ)
2. Copy script(s) + `_calculator.py` to working directory
3. Submit: `Bohrium(action="submit", input_dir="<dir>", image="registry.dp.tech/dptech/dpa-calculator:e13a296f", cmd="python optimize_structure.py --structure input.cif --model DPA3.1-3M > log 2>&1", machine="c16_m64_1 * NVIDIA 4090")`
4. Poll and read `result.json`

## DPA + LAMMPS (requires freeze)

DPA3 checkpoints (`DPA3.1-3M.pt`, `DPA3.2-5M.pt`) are **multi-task / multi-head** models and **cannot be loaded directly by LAMMPS**. You must first freeze a single head/branch into a `.pth` file. This is DPA-specific (MACE/SevenNet/MatterSim do not need this step).

> Requires `deepmd-kit >= 3.1.0` (check with `dp --version`).

**Step 1 — list available branches (heads):**

```bash
dp --pt show DPA-3.2-5M.pt model-branch
```

Typical DPA3 branches: `Omat24` (default inorganic), `OMol25`, `OC22`, `Organic_Reactions`, `ODAC23`, plus `RANDOM` (randomly initialized fitting net). Pick the branch whose training data best matches your system.

**Step 2 — freeze the chosen branch:**

```bash
# --model-branch (preferred) or --head both work
dp --pt freeze -c DPA-3.2-5M.pt -o frozen_model.pth --model-branch Omat24
```

**Step 3 — use the frozen `.pth` in LAMMPS** (via the `deepmd` pair style):

```
pair_style  deepmd frozen_model.pth
pair_coeff  * *
```

Notes:
- The frozen `.pth` is also directly usable by ASE: `from deepmd.calculator import DP; atoms.calc = DP("frozen_model.pth")`.
- The ASE workflows provided by this skill (optimize/phonon/MD/elastic/NEB/adsorption) load the **multi-head `.pt`** directly and select the head via `--head`, so freezing is only required when you actually need LAMMPS.
- For a new downstream system, optionally run `dp --pt change-bias <model.pt> -s <system> --model-branch <Branch>` before freezing to better align the per-element energy bias.
