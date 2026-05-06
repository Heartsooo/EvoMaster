"""calculate_elastic.py — Elastic constants with an MLIP calculator.

Usage::

    python calculate_elastic.py --structure input.cif --model DPA3.1-3M \\
        [--head Omat24] [--fmax 0.01] [--charge 0] [--spin 1]

Expects a **fully relaxed** periodic structure as input.

Outputs:
    elastic_matrix.csv  — 6×6 Voigt elastic tensor (GPa)
    result.json         — bulk/shear/Young's modulus (GPa)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
from _calculator import build_calculator, build_fparam, set_fparam
from ase.io import read
from ase.optimize import FIRE
from pymatgen.analysis.elasticity import DeformedStructureSet, ElasticTensor, Strain
from pymatgen.analysis.elasticity.elastic import get_strain_state_dict
from pymatgen.io.ase import AseAtomsAdaptor

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

EV_A3_TO_GPA = 160.21766208


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MLIP elastic constants")
    p.add_argument("--structure", required=True, help="Relaxed structure (CIF)")
    p.add_argument("--model", default="DPA3.1-3M")
    p.add_argument("--head", default=None)
    p.add_argument(
        "--norm-strain",
        type=float,
        nargs=3,
        default=[-0.01, 0.01, 4],
        metavar=("MIN", "MAX", "N"),
        help="Normal strain range (default: -0.01 0.01 4)",
    )
    p.add_argument(
        "--shear-strain",
        type=float,
        nargs=3,
        default=[-0.06, 0.06, 4],
        metavar=("MIN", "MAX", "N"),
        help="Shear strain range (default: -0.06 0.06 4)",
    )
    p.add_argument(
        "--fmax", type=float, default=0.01, help="Ionic relaxation fmax (eV/Å)"
    )
    p.add_argument("--charge", type=int, default=None)
    p.add_argument("--spin", type=int, default=None)
    return p.parse_args()


def _fit_elastic_tensor(strains, stresses, eq_stress=None) -> ElasticTensor:
    """Least-squares fit of 6×6 elastic tensor from strain-stress data."""
    strain_states = [tuple(ss) for ss in np.eye(6)]
    ss_dict = get_strain_state_dict(
        strains,
        stresses,
        eq_stress=eq_stress,
        add_eq=eq_stress is not None,
    )
    c_ij = np.zeros((6, 6))
    for i in range(6):
        s_data = ss_dict[strain_states[i]]
        for j in range(6):
            c_ij[i, j] = np.polyfit(
                s_data["strains"][:, i], s_data["stresses"][:, j], 1
            )[0]
    return ElasticTensor.from_voigt(c_ij).zeroed(1e-7)


def main() -> None:
    args = parse_args()
    calc = build_calculator(args.model, head=args.head)
    fparam = build_fparam(args.charge, args.spin)

    atoms = read(args.structure)
    structure = AseAtomsAdaptor.get_structure(atoms)

    norm_strains = np.linspace(
        args.norm_strain[0], args.norm_strain[1], int(args.norm_strain[2])
    )
    shear_strains = np.linspace(
        args.shear_strain[0], args.shear_strain[1], int(args.shear_strain[2])
    )
    deformed = DeformedStructureSet(structure, norm_strains, shear_strains)

    stresses = []
    for ds in deformed:
        a = ds.to_ase_atoms()
        set_fparam(a, fparam)
        a.calc = calc
        FIRE(a, logfile=None).run(fmax=args.fmax)
        stresses.append(a.get_stress(voigt=False))

    strains = [Strain.from_deformation(d) for d in deformed.deformations]

    # Equilibrium stress
    eq_atoms = read(args.structure)
    set_fparam(eq_atoms, fparam)
    eq_atoms.calc = calc
    eq_stress = eq_atoms.get_stress(voigt=False)

    et = _fit_elastic_tensor(strains, stresses, eq_stress)
    K = float(et.k_vrh * EV_A3_TO_GPA)
    G = float(et.g_vrh * EV_A3_TO_GPA)
    E = 9 * K * G / (3 * K + G) if (3 * K + G) != 0 else 0.0

    # Save elastic matrix CSV
    c_gpa = et.voigt * EV_A3_TO_GPA
    labels = ["11", "22", "33", "23", "13", "12"]
    with open("elastic_matrix.csv", "w") as f:
        f.write("Cij(GPa)," + ",".join(labels) + "\n")
        for i, lbl in enumerate(labels):
            row = ",".join(f"{c_gpa[i, j]:.4f}" for j in range(6))
            f.write(f"{lbl},{row}\n")

    result = {
        "model": args.model,
        "bulk_modulus_GPa": K,
        "shear_modulus_GPa": G,
        "youngs_modulus_GPa": E,
        "elastic_matrix_file": "elastic_matrix.csv",
    }
    Path("result.json").write_text(json.dumps(result, indent=2))
    log.info("Elastic: K=%.1f  G=%.1f  E=%.1f GPa", K, G, E)


if __name__ == "__main__":
    main()
