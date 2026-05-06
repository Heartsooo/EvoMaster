"""ABACUS INPUT Validator — checks for conflicts and common mistakes."""

import json
import os

KNOWLEDGE_DIR = os.path.dirname(__file__)


def parse_input(text: str) -> dict[str, str]:
    """Parse ABACUS INPUT file into key:value dict."""
    params = {}
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            params[parts[0].lower()] = parts[1].strip()
        elif len(parts) == 1 and "=" not in line:
            continue
    return params


def validate_input(params: dict, task_type: str = "scf") -> tuple[list[str], list[str]]:
    errors = []
    warnings = []

    calc = params.get("calculation", "scf")

    # Basic checks
    if "ecutwfc" not in params:
        warnings.append("ecutwfc not set. Must be specified for both PW and LCAO.")

    basis = params.get("basis_type", "pw")

    # Relaxation checks
    if task_type == "relax" or calc in ("relax", "cell-relax"):
        if "force_thr" not in params:
            warnings.append("No force_thr set for relaxation. Recommend 0.01 eV/Angstrom.")
        if calc == "cell-relax" and params.get("cal_stress", "0") == "0":
            errors.append("cell-relax requires cal_stress=1.")

    # MD checks
    if task_type == "md" or calc == "md":
        if calc != "md":
            errors.append(f"MD task but calculation={calc}. Set calculation=md.")
        if "md_nstep" not in params:
            warnings.append("md_nstep not set (defaults to 10, very short).")
        if "md_tfirst" not in params:
            warnings.append("md_tfirst not set (temperature defaults to 0 K).")
        if "md_dt" not in params:
            warnings.append("md_dt not set (defaults to 1.0 fs).")
        if params.get("symmetry", "1") != "0":
            warnings.append("For MD, set symmetry=0 to turn off symmetry.")

    # Band structure checks
    if task_type == "band" or calc == "nscf":
        if params.get("init_chg", "") != "file":
            warnings.append("NSCF/band calculation should use init_chg=file to read charge density.")

    # DFT+U checks
    if params.get("dft_plus_u", "0") != "0":
        if "orbital_corr" not in params:
            errors.append("dft_plus_u enabled but orbital_corr not set.")
        if "hubbard_u" not in params:
            errors.append("dft_plus_u enabled but hubbard_u not set.")

    # vdW checks
    if params.get("vdw_method", "none") != "none":
        pass  # vdw_method is self-contained

    # Spin checks
    nspin = params.get("nspin", "1")
    if nspin == "4" and params.get("lspinorb", "0") == "0":
        warnings.append("nspin=4 usually requires lspinorb=1 for SOC calculations.")

    return errors, warnings


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python validator.py <INPUT_path> [task_type]")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        text = f.read()
    task = sys.argv[2] if len(sys.argv) > 2 else "scf"
    params = parse_input(text)
    errs, warns = validate_input(params, task)
    if errs:
        print("ERRORS:")
        for e in errs:
            print(f"  ✗ {e}")
    if warns:
        print("WARNINGS:")
        for w in warns:
            print(f"  ⚠ {w}")
    if not errs and not warns:
        print("✓ No issues found.")
