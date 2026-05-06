"""run_molecular_dynamics.py — Multi-stage MD with an MLIP calculator.

Usage::

    python run_molecular_dynamics.py --structure input.cif --model DPA3.1-3M \\
        --stages stages.json [--head Omat24] [--save-interval 100] \\
        [--seed 42] [--charge 0] [--spin 1]

The ``--stages`` JSON file is a list of stage dicts, e.g.::

    [
      {"mode": "NVT", "temperature_K": 300, "runtime_ps": 5},
      {"mode": "NPT-aniso", "temperature_K": 300, "pressure": 0.0, "runtime_ps": 10}
    ]

Stage keys:
    mode            NVT | NVT-Berendsen | NVT-Langevin | NPT-aniso | NPT-tri | NVE
    runtime_ps      Duration in picoseconds
    temperature_K   Temperature (K) — required for NVT/NPT
    pressure        Pressure (GPa) — required for NPT
    timestep_ps     Time step (default 0.0005 = 0.5 fs)
    tau_t_ps        Thermostat coupling (default 0.01)
    tau_p_ps        Barostat coupling (default 0.1)

Outputs:
    trajs/stage{N}_{mode}_{T}K.extxyz  — per-stage trajectories
    final_structure.xyz                 — final structure
    md_simulation.log                   — thermo log
    result.json                         — summary
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
from _calculator import build_calculator, build_fparam, set_fparam
from ase import units
from ase.io import read, write
from ase.md.langevin import Langevin
from ase.md.nose_hoover_chain import NoseHooverChainNVT
from ase.md.npt import NPT
from ase.md.nvtberendsen import NVTBerendsen
from ase.md.velocitydistribution import (
    MaxwellBoltzmannDistribution,
    Stationary,
    ZeroRotation,
)
from ase.md.verlet import VelocityVerlet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MLIP molecular dynamics")
    p.add_argument("--structure", required=True, help="Input structure file")
    p.add_argument("--model", default="DPA3.1-3M", help="Model name/path/URL")
    p.add_argument("--head", default=None, help="Model head (DP family)")
    p.add_argument("--stages", required=True, help="JSON file with stage definitions")
    p.add_argument("--save-interval", type=int, default=100, help="Save every N steps")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--charge", type=int, default=None)
    p.add_argument("--spin", type=int, default=None)
    return p.parse_args()


# ---------------------------------------------------------------------------


def _build_dynamics(atoms, stage: dict, seed: int):
    """Return an ASE dynamics object for the given stage config."""
    mode = stage["mode"]
    ts_ps = stage.get("timestep_ps", 0.0005)
    ts_fs = ts_ps * 1000
    dt = ts_fs * units.fs
    T = stage.get("temperature_K")
    P = stage.get("pressure")
    tau_t = stage.get("tau_t_ps", 0.01) * 1000 * units.fs
    tau_p = stage.get("tau_p_ps", 0.1) * 1000 * units.fs
    rng = np.random.RandomState(seed)

    if mode in ("NVT", "NVT-NH"):
        return NoseHooverChainNVT(atoms, timestep=dt, temperature_K=T, tdamp=tau_t)
    if mode == "NVT-Berendsen":
        return NVTBerendsen(atoms, timestep=dt, temperature_K=T, taut=tau_t)
    if mode in ("NVT-Langevin", "Langevin"):
        return Langevin(
            atoms, timestep=dt, temperature_K=T, friction=1.0 / tau_t, rng=rng
        )
    if mode in ("NPT-aniso", "NPT-tri"):
        if P is None:
            raise ValueError(f"Pressure required for {mode}")
        mask = np.eye(3, dtype=bool) if mode == "NPT-aniso" else None
        return NPT(
            atoms,
            timestep=dt,
            temperature_K=T,
            externalstress=P * units.GPa,
            ttime=tau_t,
            pfactor=tau_p,
            mask=mask,
        )
    if mode == "NVE":
        return VelocityVerlet(atoms, timestep=dt)
    raise ValueError(f"Unknown MD mode: {mode}")


def _run_stage(
    atoms, stage: dict, stage_idx: int, save_interval: int, seed: int, log_fh
):
    """Run a single MD stage; return atoms after the run."""
    mode = stage["mode"]
    T = stage.get("temperature_K")
    ts_ps = stage.get("timestep_ps", 0.0005)
    runtime_ps = stage["runtime_ps"]
    total_steps = int(runtime_ps / ts_ps)

    # Initialize velocities for first stage
    if stage_idx == 0 and T is not None:
        MaxwellBoltzmannDistribution(
            atoms, temperature_K=T, rng=np.random.RandomState(seed)
        )
        Stationary(atoms)
        ZeroRotation(atoms)

    dyn = _build_dynamics(atoms, stage, seed)

    tag = f"stage{stage_idx + 1}_{mode}_{T}K"
    traj_file = f"trajs/{tag}.extxyz"
    os.makedirs("trajs", exist_ok=True)

    def _save():
        frame = atoms.copy()
        frame.info["energy"] = float(atoms.get_potential_energy())
        frame.arrays["force"] = atoms.get_forces()
        write(traj_file, frame, format="extxyz", append=True)

    def _log():
        e_pot = atoms.get_potential_energy()
        e_kin = atoms.get_kinetic_energy()
        temp = e_kin / (1.5 * len(atoms) * units.kB)
        log_fh.write(f"{dyn.nsteps} {e_pot:.3f} {e_kin:.3f} {temp:.1f}\n")
        log_fh.flush()

    dyn.attach(_save, interval=save_interval)
    dyn.attach(_log, interval=save_interval)

    log.info("[Stage %d] %s  T=%s K  steps=%d", stage_idx + 1, mode, T, total_steps)
    dyn.run(total_steps)
    return atoms


def main() -> None:
    args = parse_args()
    stages = json.loads(Path(args.stages).read_text())

    atoms = read(args.structure)
    calc = build_calculator(args.model, head=args.head)
    atoms.calc = calc

    fparam = build_fparam(args.charge, args.spin)
    set_fparam(atoms, fparam)

    with open("md_simulation.log", "w") as log_fh:
        log_fh.write("step E_pot(eV) E_kin(eV) T(K)\n")
        for i, stage in enumerate(stages):
            atoms = _run_stage(atoms, stage, i, args.save_interval, args.seed, log_fh)

    write("final_structure.xyz", atoms)

    result = {
        "model": args.model,
        "num_stages": len(stages),
        "final_structure": "final_structure.xyz",
        "trajectory_dir": "trajs",
        "log_file": "md_simulation.log",
    }
    Path("result.json").write_text(json.dumps(result, indent=2))
    log.info("MD complete. See result.json.")


if __name__ == "__main__":
    main()
