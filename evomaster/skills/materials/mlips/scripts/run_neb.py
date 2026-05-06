"""run_neb.py — NEB transition-state search with an MLIP calculator.

Usage::

    python run_neb.py --initial initial.cif --final final.cif \\
        --model DPA3.1-3M [--head Omat24] [--images 5] \\
        [--fmax 0.05] [--steps 500] [--charge 0] [--spin 1]

Both initial and final structures must be **fully relaxed** beforehand.

Outputs:
    neb_band.pdf    — energy profile plot
    result.json     — forward/reverse barriers (eV)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from _calculator import build_calculator, build_fparam, set_fparam
from ase.io import read
from ase.mep import NEB, NEBTools
from ase.optimize import BFGS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MLIP NEB calculation")
    p.add_argument("--initial", required=True, help="Initial (relaxed) structure")
    p.add_argument("--final", required=True, help="Final (relaxed) structure")
    p.add_argument("--model", default="DPA3.1-3M")
    p.add_argument("--head", default=None)
    p.add_argument(
        "--images", type=int, default=5, help="Intermediate images (default: 5)"
    )
    p.add_argument("--fmax", type=float, default=0.05, help="Force tolerance (eV/Å)")
    p.add_argument("--steps", type=int, default=500, help="Max NEB steps")
    p.add_argument("--charge", type=int, default=None)
    p.add_argument("--spin", type=int, default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    calc = build_calculator(args.model, head=args.head)
    fparam = build_fparam(args.charge, args.spin)

    initial = read(args.initial)
    final = read(args.final)

    # Validate
    if len(initial) != len(final):
        raise ValueError("Initial and final structures must have the same atom count.")
    if initial.get_chemical_symbols() != final.get_chemical_symbols():
        raise ValueError("Initial and final must have identical element ordering.")

    # Build NEB images
    images = [initial]
    for _ in range(args.images):
        img = initial.copy()
        set_fparam(img, fparam)
        img.calc = calc
        images.append(img)
    set_fparam(initial, fparam)
    initial.calc = calc
    set_fparam(final, fparam)
    final.calc = calc
    images.append(final)

    # NEB
    neb = NEB(images, climb=False, allow_shared_calculator=True)
    neb.interpolate(method="idpp")

    opt = BFGS(neb)
    # Phase 1: coarse relaxation
    converged = opt.run(fmax=0.45, steps=200)
    # Phase 2: climbing image if phase 1 converged
    if converged:
        neb.climb = True
        opt.run(fmax=args.fmax, steps=args.steps)

    # Analysis
    neb_tools = NEBTools(neb.images)
    barrier = neb_tools.get_barrier()  # (forward, reverse)
    neb_tools.plot_bands(label="neb_band")

    result = {
        "model": args.model,
        "forward_barrier_eV": float(barrier[0]),
        "reverse_barrier_eV": float(barrier[1]),
        "num_images": args.images,
        "band_plot": "neb_band.pdf",
    }
    Path("result.json").write_text(json.dumps(result, indent=2))
    log.info("NEB: forward=%.4f eV  reverse=%.4f eV", barrier[0], barrier[1])


if __name__ == "__main__":
    main()
