"""calculate_adsorption.py — Adsorption energy calculations with MLIP.

Computes E_ads = E(slab+ads) - E(slab) - E(gas) for every slab x adsorbate
combination.  Common gas-phase molecules are built automatically; custom
adsorbates can be supplied as structure files.

Usage::

    python calculate_adsorption.py \
        --slabs Ag_001.cif Ag_011.cif \
        --adsorbates CO H OH COOH \
        --model DPA3.1-3M --head OC22 \
        [--height 2.0] [--fmax 0.03] [--steps 300] [--fix-fraction 0.3]

Built-in adsorbates: H, C, O, N, CO, CO2, H2, H2O, OH, OOH, COOH, HCOO, CHO.
For anything else, provide a structure file path (CIF/XYZ/POSCAR).

Outputs:
    adsorption_results.json       — complete energy table
    {slab}_{ads}_relaxed.cif      — relaxed slab+adsorbate structures
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from _calculator import build_calculator
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read, write
from ase.optimize import BFGS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in gas molecules — symbols + Cartesian positions (Angstrom)
# ---------------------------------------------------------------------------
_GAS: dict[str, tuple[list[str], list[list[float]]]] = {
    "H": (["H"], [[0, 0, 0]]),
    "C": (["C"], [[0, 0, 0]]),
    "O": (["O"], [[0, 0, 0]]),
    "N": (["N"], [[0, 0, 0]]),
    "CO": (["C", "O"], [[0, 0, 0], [0, 0, 1.128]]),
    "CO2": (["C", "O", "O"], [[0, 0, 0], [0, 0, 1.162], [0, 0, -1.162]]),
    "H2": (["H", "H"], [[0, 0, 0], [0, 0, 0.74]]),
    "H2O": (["O", "H", "H"], [[0, 0, 0], [0.757, 0.586, 0], [-0.757, 0.586, 0]]),
    "OH": (["O", "H"], [[0, 0, 0], [0, 0, 0.970]]),
    "OOH": (["O", "O", "H"], [[0, 0, 0], [0, 0, 1.21], [0, 0.94, 1.56]]),
    "COOH": (
        ["C", "O", "O", "H"],
        [[0, 0, 0], [1.06, 0.67, 0], [-0.39, 1.20, 0], [-0.20, 2.14, 0]],
    ),
    "HCOO": (
        ["H", "C", "O", "O"],
        [[0, 0, 1.10], [0, 0, 0], [1.05, 0, -0.63], [-1.05, 0, -0.63]],
    ),
    "CHO": (["C", "H", "O"], [[0, 0, 0], [0, 1.09, 0], [0, -0.37, 1.11]]),
}


def build_gas(name: str) -> Atoms:
    """Return a gas-phase molecule in a periodic vacuum box."""
    if name.upper() in _GAS:
        syms, pos = _GAS[name.upper()]
        mol = Atoms(symbols=syms, positions=pos)
    elif Path(name).is_file():
        mol = read(name)
    else:
        raise ValueError(
            f"Unknown adsorbate '{name}'. "
            f"Built-in: {sorted(_GAS)}. Or provide a file path."
        )
    mol.center(vacuum=7.5)
    mol.pbc = True
    return mol


def place_adsorbate(slab: Atoms, ads: Atoms, height: float = 2.0) -> Atoms:
    """Place *ads* above the slab top surface at *height* angstrom."""
    combined = slab.copy()
    combined.set_constraint()  # clear slab constraints
    ads_copy = ads.copy()
    ads_copy.set_constraint()
    ads_copy.pbc = False

    # Shift adsorbate so its lowest atom sits at z_top + height
    z_top = slab.positions[:, 2].max()
    ads_copy.positions[:, 2] += (z_top + height) - ads_copy.positions[:, 2].min()

    # Centre over slab surface (using lattice vectors a, b)
    centre_xy = slab.cell[0, :2] / 2 + slab.cell[1, :2] / 2
    ads_copy.positions[:, :2] += centre_xy - ads_copy.positions[:, :2].mean(axis=0)

    combined += ads_copy
    return combined


def apply_fix_bottom(atoms: Atoms, n_slab: int, fraction: float) -> None:
    """Fix the bottom *fraction* of slab atoms (indices 0..n_slab-1)."""
    z = atoms.positions[:n_slab, 2]
    z_cut = z.min() + fraction * (z.max() - z.min())
    fixed = [i for i in range(n_slab) if atoms.positions[i, 2] <= z_cut]
    atoms.set_constraint(FixAtoms(indices=fixed))
    log.info(
        "  Fixed %d / %d slab atoms (bottom %.0f%%)", len(fixed), n_slab, fraction * 100
    )


def relax_atoms(atoms: Atoms, fmax: float, steps: int, label: str = "") -> float:
    """BFGS relaxation → final energy (eV)."""
    opt = BFGS(atoms, logfile=None)
    converged = opt.run(fmax=fmax, steps=steps)
    e = float(atoms.get_potential_energy())
    log.info(
        "  %s: E = %.6f eV, steps = %d, converged = %s", label, e, opt.nsteps, converged
    )
    return e


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute adsorption energies with MLIP (DPA / MACE / …)"
    )
    p.add_argument(
        "--slabs",
        nargs="+",
        required=True,
        help="Slab structure files (CIF / POSCAR / XYZ)",
    )
    p.add_argument(
        "--adsorbates",
        nargs="+",
        required=True,
        help="Adsorbate names (CO, H, OH …) or file paths",
    )
    p.add_argument(
        "--model",
        default="DPA3.1-3M",
        help="MLIP model name or path (default: DPA3.1-3M)",
    )
    p.add_argument(
        "--head", default="OC22", help="DPA model head (default: OC22 for catalysis)"
    )
    p.add_argument(
        "--height",
        type=float,
        default=2.0,
        help="Adsorbate placement height in Ang (default: 2.0)",
    )
    p.add_argument(
        "--fmax",
        type=float,
        default=0.03,
        help="Force convergence in eV/Ang (default: 0.03)",
    )
    p.add_argument(
        "--steps", type=int, default=300, help="Max optimisation steps (default: 300)"
    )
    p.add_argument(
        "--fix-fraction",
        type=float,
        default=0.3,
        help="Fraction of slab z-range to fix (default: 0.3)",
    )
    p.add_argument(
        "--no-relax",
        action="store_true",
        help="Single-point energies only (skip relaxation)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    calc = build_calculator(args.model, head=args.head)
    results: list[dict] = []

    # ── gas-phase energies ─────────────────────────────────────────────
    log.info("=== Gas-phase energies ===")
    gas_e: dict[str, float] = {}
    for name in args.adsorbates:
        label = Path(name).stem if "/" in name or "\\" in name else name
        mol = build_gas(name)
        mol.calc = calc
        if args.no_relax:
            gas_e[label] = float(mol.get_potential_energy())
        else:
            gas_e[label] = relax_atoms(mol, args.fmax, args.steps, f"Gas {label}")

    # ── per-slab loop ──────────────────────────────────────────────────
    for slab_file in args.slabs:
        slab_name = Path(slab_file).stem
        log.info("\n=== Slab: %s ===", slab_name)

        slab = read(slab_file)
        n_slab = len(slab)
        slab.calc = calc
        apply_fix_bottom(slab, n_slab, args.fix_fraction)

        if args.no_relax:
            e_slab = float(slab.get_potential_energy())
        else:
            e_slab = relax_atoms(slab, args.fmax, args.steps, f"Slab {slab_name}")

        # ── per-adsorbate ──────────────────────────────────────────────
        for ads_name in args.adsorbates:
            label = (
                Path(ads_name).stem if "/" in ads_name or "\\" in ads_name else ads_name
            )
            mol = build_gas(ads_name)
            combined = place_adsorbate(slab, mol, args.height)
            combined.calc = calc
            apply_fix_bottom(combined, n_slab, args.fix_fraction)

            if args.no_relax:
                e_comb = float(combined.get_potential_energy())
            else:
                e_comb = relax_atoms(
                    combined, args.fmax, args.steps, f"{slab_name}+{label}"
                )

            e_ads = e_comb - e_slab - gas_e[label]
            out_file = f"{slab_name}_{label}_relaxed.cif"
            write(out_file, combined)

            results.append(
                {
                    "slab": slab_name,
                    "adsorbate": label,
                    "E_slab_eV": round(e_slab, 6),
                    "E_gas_eV": round(gas_e[label], 6),
                    "E_combined_eV": round(e_comb, 6),
                    "E_ads_eV": round(e_ads, 4),
                    "output_file": out_file,
                }
            )

    # ── summary table ──────────────────────────────────────────────────
    hdr = f"{'Slab':<22} {'Ads':<8} {'E_ads(eV)':>10} {'E_comb':>12} {'E_slab':>12} {'E_gas':>12}"
    sep = "-" * len(hdr)
    print(f"\n{'=' * len(hdr)}")
    print(hdr)
    print(sep)
    for r in results:
        print(
            f"{r['slab']:<22} {r['adsorbate']:<8} {r['E_ads_eV']:>10.4f} "
            f"{r['E_combined_eV']:>12.4f} {r['E_slab_eV']:>12.4f} {r['E_gas_eV']:>12.4f}"
        )
    print(f"{'=' * len(hdr)}")

    Path("adsorption_results.json").write_text(json.dumps(results, indent=2))
    log.info("Results saved to adsorption_results.json")


if __name__ == "__main__":
    main()
