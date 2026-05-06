"""optimize_structure.py — Structure optimization with an MLIP calculator.

Usage::

    python optimize_structure.py --structure input.cif --model DPA3.1-3M \\
        [--head Omat24] [--relax-cell] [--fmax 0.01] [--steps 100] \\
        [--charge 0] [--spin 1]

Outputs (in working directory):
    {stem}_optimized.cif / .xyz   — optimized structure
    {stem}_traj.traj              — optimization trajectory
    result.json                   — summary (energy, steps, convergence)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from _calculator import build_calculator, build_fparam, set_fparam
from ase.filters import FrechetCellFilter
from ase.io import read, write
from ase.optimize import BFGS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MLIP structure optimization")
    p.add_argument(
        "--structure", required=True, help="Input structure file (CIF, POSCAR, XYZ …)"
    )
    p.add_argument(
        "--model",
        default="DPA3.1-3M",
        help="Model name, path, or URL (default: DPA3.1-3M)",
    )
    p.add_argument(
        "--head", default=None, help="Model head for DP family (e.g. Omat24, OMol25)"
    )
    p.add_argument(
        "--relax-cell", action="store_true", help="Also relax cell shape/volume"
    )
    p.add_argument(
        "--fmax",
        type=float,
        default=0.01,
        help="Force convergence (eV/Å, default: 0.01)",
    )
    p.add_argument(
        "--steps", type=int, default=100, help="Max optimization steps (default: 100)"
    )
    p.add_argument(
        "--charge", type=int, default=None, help="System charge (DPA3.2-5M only)"
    )
    p.add_argument(
        "--spin", type=int, default=None, help="Spin multiplicity (DPA3.2-5M only)"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    stem = Path(args.structure).stem

    # Read structure
    atoms = read(args.structure)
    is_periodic = atoms.pbc.any()

    # Build calculator
    calc = build_calculator(args.model, head=args.head)
    atoms.calc = calc

    # fparam (charge / spin)
    fparam = build_fparam(args.charge, args.spin)
    set_fparam(atoms, fparam)

    # Ignore relax_cell for non-periodic systems
    relax_cell = args.relax_cell and is_periodic
    if args.relax_cell and not is_periodic:
        log.warning("--relax-cell ignored for non-periodic system")

    # Optimize
    traj_file = f"{stem}_traj.traj"
    if relax_cell:
        opt_target = FrechetCellFilter(atoms)
    else:
        opt_target = atoms
    optimizer = BFGS(opt_target, trajectory=traj_file)
    converged = optimizer.run(fmax=args.fmax, steps=args.steps)

    # Save optimized structure
    fmt = "cif" if is_periodic else "xyz"
    out_file = f"{stem}_optimized.{fmt}"
    write(out_file, atoms, format=fmt)

    energy = float(atoms.get_potential_energy())
    log.info(
        "Done: %d steps, energy=%.4f eV, converged=%s → %s",
        optimizer.nsteps,
        energy,
        converged,
        out_file,
    )

    # result.json
    result = {
        "optimized_structure": out_file,
        "trajectory": traj_file,
        "final_energy_eV": energy,
        "steps": optimizer.nsteps,
        "converged": bool(converged),
        "model": args.model,
    }
    Path("result.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
