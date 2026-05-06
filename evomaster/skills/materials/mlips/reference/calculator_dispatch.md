# Multi-MLIP Calculator Dispatch Guide

## Scope

This skill is **DPA-first**. The reason the same scripts work across four MLIP families is that every family exposes an ASE `Calculator`, and `_calculator.py` hides the family-specific construction behind a single `build_calculator()` call. **The unified ASE interface is what is portable — not the runtime environment.**

The default submission image (`registry.dp.tech/dptech/dpa-calculator:...`) ships **only DeePMD-kit / DPA**. MACE, SevenNet and MatterSim Python packages are **not** installed there; treat them as opt-in and either (a) `pip install` them on top, or (b) switch to the multi-family LAMBench image.

## Supported Families

The `_calculator.py` module supports four MLIP families via a unified `build_calculator()` interface:

| Family | Package | Calculator Class | In default image? | Install if missing |
|--------|---------|------------------|-------------------|--------------------|
| **DP** (DPA) | `deepmd-kit` | `deepmd.calculator.DP` | Yes | [deepmodeling/deepmd-kit](https://github.com/deepmodeling/deepmd-kit) |
| **MACE** | `mace-torch` | `mace.calculators.mace_mp` | **No** | `pip install mace-torch` — [ACEsuit/mace](https://github.com/ACEsuit/mace) |
| **SevenNet** | `sevenn` | `sevenn.SevenNetCalculator` | **No** | `pip install sevenn` — [MDIL-SNU/SevenNet](https://github.com/MDIL-SNU/SevenNet) |
| **MatterSim** | `mattersim` | `mattersim.forcefield.MatterSimCalculator` | **No** | `pip install mattersim` — [microsoft/mattersim](https://github.com/microsoft/mattersim) |

> When submitting with a non-DPA family, prepend the install into `cmd`, e.g.:
> `cmd="source /mcp_server/AI4S-agent-tools/.venv/bin/activate && pip install mace-torch && python optimize_structure.py --model MACE-MP-0 ... > log 2>&1"`
> Or use `Bohrium(action="list_images", keyword="lambench")` to pick a prebuilt multi-family image.

## How `build_calculator()` resolves models

```
model_name_or_path
    │
    ├─ Known name (e.g. "DPA3.1-3M", "MACE-MP-0") → lookup KNOWN_MODELS → download if URL → dispatch
    │
    ├─ URL (http/https) → download to cache → default family = DP
    │
    └─ Local path
        ├─ .pt / .pth / .pb → family = DP
        ├─ .model → family = MACE
        └─ other → family = DP (fallback)
```

## Family-specific notes

### DP (DPA)

- Requires `--head` for multi-head models (default: `Omat24`)
- Supports `--charge` and `--spin` via fparam (DPA3.2-5M only)
- Model files: `.pt` (PyTorch) or `.pb` (TensorFlow, legacy)

### MACE

- No `--head` flag (ignored)
- Default dtype: `float64` for accuracy
- Named models (`MACE-MP-0`) use `mace_mp()` auto-download
- Custom `.model` files: pass the local path

### SevenNet

- Named models (`SevenNet-0`, `7net-mf-ompa`) resolved by the `sevenn` package
- `7net-mf-ompa` automatically sets `modal="omat24"`
- No head or fparam support

### MatterSim

- Only one model currently: `MatterSim-v1-5M`
- Auto-downloads `MatterSim-v1.0.0-5M.pth`
- No head or fparam support

## Adding a new MLIP family

1. Add model entries to `KNOWN_MODELS` in `_calculator.py`
2. Write an `_init_{family}()` function
3. Register it in `_FAMILY_INIT`
4. Update this reference document

## Docker images by family

| Family | Known working image |
|--------|-------------------|
| DP (DPA) | `registry.dp.tech/dptech/dpa-calculator:e13a296f` |
| All families | `registry.dp.tech/dptech/dp/native/prod-375/lambench:v2.9` (LAMBench image) |

> Use `Bohrium(action="list_images", keyword="lambench")` to find the latest multi-MLIP image.
> The DPA-specific image is smaller and faster to pull when only DPA is needed.
> If a package is missing in the selected image, the submitted `cmd` / `command` may prepend `pip install <pkg> &&` before running the script.
> If you want the installation to land in the bundled environment, activate `/mcp_server/AI4S-agent-tools/.venv` first, e.g. `source /mcp_server/AI4S-agent-tools/.venv/bin/activate && pip install <pkg> && python ...`.
