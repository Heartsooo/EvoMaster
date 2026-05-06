#!/usr/bin/env python3
"""validate_input.py — Pre-flight validation for ABACUS input files.

Checks the most common silent-failure mistakes BEFORE Bohrium submission.
Run this after generating INPUT/STRU/KPT files and before calling Bohrium(submit).

Usage::

    python validate_input.py [--dir <workspace_dir>]

Reads all INPUT* files in the directory (or current dir) and validates against
the corresponding STRU/KPT files. Reports PASS/FAIL with actionable messages.

Exit code: 0 if all checks pass, 1 if any FAIL.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _parse_input(path: Path) -> dict[str, str]:
    """Parse an ABACUS INPUT file into a key-value dict."""
    params: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if line.upper() == "INPUT_PARAMETERS":
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            params[parts[0].lower()] = parts[1].strip()
        elif len(parts) == 1:
            params[parts[0].lower()] = ""
    return params


def _count_stru_species(stru_path: Path) -> tuple[int, bool, list[str]]:
    """Count species in STRU, detect NUMERICAL_ORBITAL presence, and list PP filenames."""
    text = stru_path.read_text()
    lines = text.splitlines()

    species_count = 0
    has_orbital = False
    pp_files: list[str] = []
    orb_files: list[str] = []

    in_atomic_species = False
    in_numerical_orbital = False

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper == "ATOMIC_SPECIES":
            in_atomic_species = True
            in_numerical_orbital = False
            continue
        elif upper == "NUMERICAL_ORBITAL":
            in_atomic_species = False
            in_numerical_orbital = True
            has_orbital = True
            continue
        elif upper in (
            "LATTICE_CONSTANT",
            "LATTICE_VECTORS",
            "ATOMIC_POSITIONS",
        ):
            in_atomic_species = False
            in_numerical_orbital = False
            continue

        if in_atomic_species and stripped and not stripped.startswith("#"):
            parts = stripped.split()
            if len(parts) >= 3:
                species_count += 1
                pp_files.append(parts[2])

        if in_numerical_orbital and stripped and not stripped.startswith("#"):
            orb_files.append(stripped.split()[0])

    return species_count, has_orbital, pp_files + orb_files


def validate_workspace(workspace: Path) -> list[str]:
    """Validate all INPUT* files in workspace. Returns list of messages."""
    messages: list[str] = []
    input_files = sorted(workspace.glob("INPUT*"))
    # Filter out non-files and backup files
    input_files = [f for f in input_files if f.is_file() and not f.name.endswith("~")]

    if not input_files:
        messages.append("FAIL: No INPUT files found in workspace.")
        return messages

    all_files = {f.name for f in workspace.iterdir() if f.is_file()}

    for input_file in input_files:
        prefix = f"[{input_file.name}]"
        try:
            params = _parse_input(input_file)
        except Exception as e:
            messages.append(f"FAIL {prefix}: Cannot parse INPUT: {e}")
            continue

        calc = params.get("calculation", "scf")

        # --- Check stru_file / kpoint_file references ---
        stru_name = params.get("stru_file", "STRU")
        kpt_name = params.get("kpoint_file", "KPT")

        stru_path = workspace / stru_name
        if stru_name not in all_files:
            messages.append(
                f"FAIL {prefix}: stru_file '{stru_name}' not found. "
                f"Available files: {sorted(f for f in all_files if 'stru' in f.lower() or f == 'STRU')}"
            )
        elif stru_path.is_file():
            # Validate ntype
            species_count, has_orbital, referenced_files = _count_stru_species(
                stru_path
            )
            ntype_str = params.get("ntype", "")
            if ntype_str:
                try:
                    ntype_val = int(ntype_str)
                    if ntype_val != species_count:
                        messages.append(
                            f"FAIL {prefix}: ntype={ntype_val} but STRU has "
                            f"{species_count} species in ATOMIC_SPECIES."
                        )
                    else:
                        messages.append(
                            f"PASS {prefix}: ntype={ntype_val} matches STRU species count."
                        )
                except ValueError:
                    messages.append(
                        f"WARN {prefix}: ntype='{ntype_str}' is not an integer."
                    )

            # Validate basis_type vs NUMERICAL_ORBITAL
            basis = params.get("basis_type", "pw")
            if has_orbital and basis == "pw":
                messages.append(
                    f"WARN {prefix}: STRU has NUMERICAL_ORBITAL but basis_type=pw. "
                    f"Consider basis_type=lcao."
                )
            elif not has_orbital and basis == "lcao":
                messages.append(
                    f"FAIL {prefix}: basis_type=lcao but STRU has no NUMERICAL_ORBITAL section. "
                    f"ABACUS will crash."
                )
            else:
                messages.append(
                    f"PASS {prefix}: basis_type={basis} consistent with STRU."
                )

            # Check ecutwfc baseline
            ecutwfc_str = params.get("ecutwfc", "")
            if ecutwfc_str:
                try:
                    ecutwfc = float(ecutwfc_str)
                    if basis == "lcao" and ecutwfc < 50:
                        messages.append(
                            f"WARN {prefix}: ecutwfc={ecutwfc} is low for LCAO (standard: 100)."
                        )
                    elif basis == "pw" and ecutwfc < 30:
                        messages.append(
                            f"WARN {prefix}: ecutwfc={ecutwfc} is low for PW (standard: 50+). If this is a low-cost benchmark, this may be intentional."
                        )
                except ValueError:
                    pass

            # Check referenced PP/orbital files exist
            for ref_file in referenced_files:
                if ref_file not in all_files:
                    messages.append(
                        f"FAIL {prefix}: STRU references '{ref_file}' but file not found in workspace."
                    )

        # Check kpoint_file if not using kspacing
        has_kspacing = "kspacing" in params
        if not has_kspacing and kpt_name not in all_files:
            if calc != "md":  # MD doesn't always need KPT
                messages.append(
                    f"FAIL {prefix}: kpoint_file '{kpt_name}' not found and no kspacing set."
                )

        # --- Relaxation checks ---
        if calc in ("relax", "cell-relax"):
            if params.get("cal_force") != "1":
                messages.append(
                    f"FAIL {prefix}: calculation={calc} but cal_force is not 1. "
                    f"Forces will not be computed — relaxation silently broken."
                )
            else:
                messages.append(f"PASS {prefix}: cal_force=1 for {calc}.")

            if "force_thr" in params and "force_thr_ev" not in params:
                messages.append(
                    f"WARN {prefix}: Using force_thr (Ry/Bohr) instead of force_thr_ev (eV/Å). "
                    f"Are units correct?"
                )

            if "relax_nmax" not in params:
                messages.append(
                    f"WARN {prefix}: relax_nmax not set for {calc}. Default may be too low."
                )

        if calc == "cell-relax":
            if params.get("cal_stress") != "1":
                messages.append(
                    f"FAIL {prefix}: calculation=cell-relax but cal_stress is not 1. "
                    f"Cell vectors will not be optimized."
                )
            else:
                messages.append(f"PASS {prefix}: cal_stress=1 for cell-relax.")

        # --- NSCF checks ---
        if calc == "nscf":
            if params.get("init_chg") != "file":
                messages.append(
                    f"FAIL {prefix}: calculation=nscf but init_chg is not 'file'. "
                    f"NSCF will re-run SCF from scratch."
                )
            if params.get("symmetry", "1") != "0":
                messages.append(
                    f"WARN {prefix}: calculation=nscf but symmetry is not 0. "
                    f"K-path may be folded for band structure."
                )
            if "nbands" not in params:
                messages.append(
                    f"WARN {prefix}: calculation=nscf but nbands not set. "
                    f"May not compute enough bands."
                )
            if params.get("out_band") != "1" and params.get("out_dos") != "1":
                messages.append(
                    f"WARN {prefix}: calculation=nscf but neither out_band nor out_dos is set."
                )

        # --- SCF feeding NSCF check ---
        if calc == "scf" and params.get("out_chg") != "1":
            # Check if there's a companion NSCF INPUT
            nscf_inputs = (
                [
                    f
                    for f in input_files
                    if f != input_file
                    and "nscf" in _parse_input(f).get("calculation", "").lower()
                ]
                if len(input_files) > 1
                else []
            )
            if nscf_inputs:
                messages.append(
                    f"FAIL {prefix}: SCF with companion NSCF but out_chg is not 1. "
                    f"NSCF will not find charge density."
                )

        # --- Non-default filename check ---
        stru_files_in_dir = [f for f in all_files if "stru" in f.lower() or f == "STRU"]
        kpt_files_in_dir = [f for f in all_files if "kpt" in f.lower() or f == "KPT"]

        if len(stru_files_in_dir) > 1 and "stru_file" not in params:
            messages.append(
                f"WARN {prefix}: Multiple STRU-like files ({stru_files_in_dir}) but no stru_file set. "
                f"ABACUS will use 'STRU' by default."
            )
        if (
            len(kpt_files_in_dir) > 1
            and "kpoint_file" not in params
            and not has_kspacing
        ):
            messages.append(
                f"WARN {prefix}: Multiple KPT-like files ({kpt_files_in_dir}) but no kpoint_file set. "
                f"ABACUS will use 'KPT' by default."
            )

    # --- Check run.sh if present ---
    run_sh = workspace / "run.sh"
    if run_sh.is_file():
        content = run_sh.read_text()
        messages.append(f"PASS: run.sh found ({len(content)} bytes).")
        # Check that it references existing files
        for match in re.findall(r"cp\s+(\S+)\s+", content):
            if match not in all_files and not match.startswith("$"):
                messages.append(
                    f"WARN [run.sh]: 'cp {match} ...' but '{match}' not found in workspace."
                )

    return messages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ABACUS input files before submission."
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Workspace directory containing INPUT/STRU/KPT files (default: current dir)",
    )
    args = parser.parse_args()

    workspace = Path(args.dir).resolve()
    if not workspace.is_dir():
        print(f"ERROR: '{workspace}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    messages = validate_workspace(workspace)

    has_fail = False
    for msg in messages:
        if msg.startswith("FAIL"):
            has_fail = True
            print(f"❌ {msg}")
        elif msg.startswith("WARN"):
            print(f"⚠️  {msg}")
        else:
            print(f"✅ {msg}")

    print()
    if has_fail:
        print("RESULT: VALIDATION FAILED — fix the issues above before submitting.")
        sys.exit(1)
    else:
        print("RESULT: All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
