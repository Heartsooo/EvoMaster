"""calculate_phonon.py — Phonon properties with an MLIP calculator.

Usage::

    python calculate_phonon.py --structure input.cif --model DPA3.1-3M \\
        --temperatures 300 600 900 [--head Omat24] [--displacement 0.005] \\
        [--calc-tdos] [--calc-pdos] [--mesh 40] [--charge 0] [--spin 1]

Outputs:
    phonon_band.png / .yaml / .dat  — band structure
    phonon_tdos.png / .dat          — total DOS (if --calc-tdos)
    phonon_pdos.png / .dat          — projected DOS (if --calc-pdos)
    result.json                     — thermal properties summary
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
from _calculator import build_calculator, build_fparam, set_fparam
from ase import Atoms, io
from phonopy import Phonopy
from phonopy.harmonic.dynmat_to_fc import get_commensurate_points
from phonopy.structure.atoms import PhonopyAtoms

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

THz_TO_K = 47.9924


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MLIP phonon calculation")
    p.add_argument("--structure", required=True, help="Input structure (CIF)")
    p.add_argument("--model", default="DPA3.1-3M", help="Model name/path/URL")
    p.add_argument("--head", default=None, help="Model head (DP family)")
    p.add_argument(
        "--temperatures", type=float, nargs="+", default=[], help="Temperatures (K)"
    )
    p.add_argument(
        "--displacement", type=float, default=0.005, help="Displacement distance (Å)"
    )
    p.add_argument("--calc-tdos", action="store_true", help="Calculate total DOS")
    p.add_argument("--calc-pdos", action="store_true", help="Calculate projected DOS")
    p.add_argument("--mesh", type=int, default=40, help="Mesh density for DOS")
    p.add_argument("--sigma", type=float, default=None, help="Gaussian smearing sigma")
    p.add_argument("--charge", type=int, default=None)
    p.add_argument("--spin", type=int, default=None)
    return p.parse_args()


def _compute_forces(phonon: Phonopy, calc, fparam: np.ndarray | None):
    """Compute displaced-supercell forces and set them on the Phonopy object."""
    force_sets = []
    for sc in phonon.supercells_with_displacements:
        sc_atoms = Atoms(
            cell=sc.cell,
            symbols=sc.symbols,
            scaled_positions=sc.scaled_positions,
            pbc=True,
        )
        set_fparam(sc_atoms, fparam)
        sc_atoms.calc = calc
        forces = sc_atoms.get_forces()
        # Remove drift
        force_sets.append(forces - np.mean(forces, axis=0))
    phonon.forces = force_sets
    phonon.produce_force_constants()


def main() -> None:
    args = parse_args()
    atoms = io.read(args.structure)
    calc = build_calculator(args.model, head=args.head)
    fparam = build_fparam(args.charge, args.spin)

    # Build Phonopy object
    ph_atoms = PhonopyAtoms(
        symbols=atoms.get_chemical_symbols(),
        cell=atoms.get_cell(),
        scaled_positions=atoms.get_scaled_positions(),
    )
    phonon = Phonopy(ph_atoms, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    phonon.generate_displacements(distance=args.displacement)

    # Forces
    _compute_forces(phonon, calc, fparam)

    # Thermal properties
    phonon.run_mesh([10, 10, 10])
    result: dict = {"model": args.model}

    if args.temperatures:
        phonon.run_thermal_properties(temperatures=args.temperatures)
        tp = phonon.get_thermal_properties_dict()
        result["entropy_J_mol_K"] = [float(v) for v in tp["entropy"]]
        result["free_energy_kJ_mol"] = [float(v) for v in tp["free_energy"]]
        result["heat_capacity_J_mol_K"] = [float(v) for v in tp["heat_capacity"]]
        result["temperatures_K"] = args.temperatures

    # Max frequency
    comm_q = get_commensurate_points(phonon.supercell_matrix)
    freqs = np.array([phonon.get_frequencies(q) for q in comm_q])
    result["max_frequency_THz"] = float(np.max(freqs))
    result["max_frequency_K"] = float(np.max(freqs) * THz_TO_K)

    # Band structure
    phonon.auto_band_structure(
        npoints=101, write_yaml=True, filename="phonon_band.yaml"
    )
    plot = phonon.plot_band_structure()
    plot.savefig("phonon_band.png", dpi=300)
    result["band_plot"] = "phonon_band.png"
    result["band_yaml"] = "phonon_band.yaml"

    # DOS
    if args.calc_tdos or args.calc_pdos:
        mesh = [args.mesh] * 3
        phonon.run_mesh(mesh, with_eigenvectors=args.calc_pdos, is_mesh_symmetry=False)

    if args.calc_tdos:
        phonon.run_total_dos(sigma=args.sigma)
        phonon.plot_total_dos().savefig("phonon_tdos.png", dpi=300)
        phonon.write_total_dos(filename="phonon_tdos.dat")
        result["total_dos_plot"] = "phonon_tdos.png"

    if args.calc_pdos:
        phonon.run_projected_dos(sigma=args.sigma)
        phonon.plot_projected_dos().savefig("phonon_pdos.png", dpi=300)
        phonon.write_projected_dos(filename="phonon_pdos.dat")
        result["projected_dos_plot"] = "phonon_pdos.png"

    Path("result.json").write_text(json.dumps(result, indent=2))
    log.info("Phonon calculation complete. See result.json for summary.")


if __name__ == "__main__":
    main()
