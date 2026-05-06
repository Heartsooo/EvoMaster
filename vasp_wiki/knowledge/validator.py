"""
VASP INCAR Validator
Validates INCAR tags against constraints, dependencies, and best practices.

Usage:
    from validator import validate_incar
    errors, warnings = validate_incar(incar_tags, task_type, system_info)
"""

import json
import os
from typing import Any

KNOWLEDGE_DIR = os.path.dirname(__file__)


def load_json(name: str) -> dict:
    path = os.path.join(KNOWLEDGE_DIR, name)
    with open(path) as f:
        return json.load(f)


def parse_incar(incar_text: str) -> dict[str, str]:
    """Parse INCAR text into a tag:value dict."""
    tags = {}
    for line in incar_text.splitlines():
        line = line.split("#")[0].split("!")[0].strip()
        if "=" not in line:
            continue
        for part in line.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            key, val = part.split("=", 1)
            tags[key.strip().upper()] = val.strip()
    return tags


def _get(tags: dict, key: str, default=None):
    return tags.get(key, default)


def _is_true(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().upper() in (".TRUE.", "T", "TRUE", ".T.")


def _as_int(val: str | None, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val.split()[0])
    except (ValueError, IndexError):
        return default


def _as_float(val: str | None, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val.split()[0])
    except (ValueError, IndexError):
        return default


def validate_incar(
    tags: dict[str, str],
    task_type: str = "scf",
    system_info: dict | None = None,
) -> tuple[list[str], list[str]]:
    """
    Validate INCAR tags.

    Args:
        tags: dict of INCAR tag -> value (strings)
        task_type: one of scf, relax, band, dos, md, hybrid, gw, phonon, neb, optical
        system_info: optional dict with keys like:
            - is_metal: bool
            - has_magnetic: bool
            - elements: list[str]
            - n_atoms: int
            - enmax: float (max ENMAX from POTCAR)

    Returns:
        (errors, warnings) - lists of message strings
    """
    errors = []
    warnings = []
    info = system_info or {}

    # ── Conflict checks ──

    # C001: ALGO + hybrid
    algo = _get(tags, "ALGO", "").lower()
    if _is_true(_get(tags, "LHFCALC")) and algo in ("veryfast", "fast"):
        errors.append(
            f"ALGO={_get(tags, 'ALGO')} is incompatible with LHFCALC=.TRUE. "
            "Use ALGO=All or ALGO=Damped for hybrid functionals."
        )

    # C002: ISMEAR=-5 with MD
    ismear = _as_int(_get(tags, "ISMEAR"), 1)
    ibrion = _as_int(_get(tags, "IBRION"), -1)
    if ismear == -5 and ibrion == 0:
        errors.append(
            "ISMEAR=-5 (tetrahedron) cannot be used for molecular dynamics. "
            "Use ISMEAR=0 (Gaussian) or ISMEAR=1 (Methfessel-Paxton)."
        )

    # C004: ISMEAR>0 for insulators
    if ismear > 0 and info.get("is_metal") is False:
        warnings.append(
            f"ISMEAR={ismear} (Methfessel-Paxton) may give negative occupancies "
            "for insulators/semiconductors. Consider ISMEAR=0."
        )

    # C005: IBRION=-1 with NSW>0
    nsw = _as_int(_get(tags, "NSW"), 0)
    if ibrion == -1 and nsw > 0:
        errors.append(
            f"IBRION=-1 with NSW={nsw} will recompute the same structure {nsw} times. "
            "Set NSW=0 for single-point or IBRION>=0 for relaxation/MD."
        )

    # C006: ICHARG=11 + hybrid
    icharg = _as_int(_get(tags, "ICHARG"), -1)
    if icharg == 11 and _is_true(_get(tags, "LHFCALC")):
        errors.append(
            "ICHARG=11 does not work with hybrid functionals. "
            "Use KPOINTS_OPT method for hybrid band structures."
        )

    # C007: NPAR and NCORE both set
    if "NPAR" in tags and "NCORE" in tags:
        warnings.append(
            "Both NPAR and NCORE are set. Use only NCORE (preferred)."
        )

    # ── Dependency checks ──

    # D002: LDAU dependencies
    if _is_true(_get(tags, "LDAU")):
        for req in ["LDAUTYPE", "LDAUL", "LDAUU", "LDAUJ"]:
            if req not in tags:
                errors.append(f"LDAU=.TRUE. requires {req} to be set.")
        if "LMAXMIX" not in tags:
            warnings.append(
                "LDAU is set but LMAXMIX is not. "
                "Set LMAXMIX=4 for d-electrons or 6 for f-electrons."
            )

    # D005: Meta-GGA requires LASPH
    if "METAGGA" in tags and not _is_true(_get(tags, "LASPH")):
        errors.append(
            f"METAGGA={_get(tags, 'METAGGA')} requires LASPH=.TRUE."
        )

    # D007: LOPTICS needs NBANDS
    if _is_true(_get(tags, "LOPTICS")) and "NBANDS" not in tags:
        warnings.append(
            "LOPTICS=.TRUE. needs sufficient empty bands. "
            "Set NBANDS to 2-3x the default value."
        )

    # D010: Langevin thermostat needs LANGEVIN_GAMMA
    mdalgo = _as_int(_get(tags, "MDALGO"), 0)
    if mdalgo == 3 and "LANGEVIN_GAMMA" not in tags:
        errors.append(
            "MDALGO=3 (Langevin thermostat) requires LANGEVIN_GAMMA to be set."
        )

    # D011: ISPIN=2 should set MAGMOM
    ispin = _as_int(_get(tags, "ISPIN"), 1)
    if ispin == 2 and "MAGMOM" not in tags:
        warnings.append(
            "ISPIN=2 but MAGMOM is not set. "
            "VASP will use default (1.0 per atom) which may not converge to correct magnetic state."
        )

    # ── Pulay stress check ──
    isif = _as_int(_get(tags, "ISIF"), 2)
    if isif >= 3:
        enmax = info.get("enmax", 0)
        encut = _as_float(_get(tags, "ENCUT"), 0)
        if encut > 0 and enmax > 0 and encut < 1.25 * enmax:
            warnings.append(
                f"ISIF={isif} (volume relaxation) with ENCUT={encut} eV. "
                f"ENMAX from POTCAR is ~{enmax} eV. "
                f"Set ENCUT >= {1.3 * enmax:.0f} eV to avoid Pulay stress."
            )
        prec = _get(tags, "PREC", "").lower()
        if prec and prec not in ("accurate", "a"):
            warnings.append(
                f"ISIF={isif} but PREC={_get(tags, 'PREC')}. "
                "Use PREC=Accurate for volume relaxation."
            )

    # ── Task-specific checks ──

    if task_type == "relax":
        if nsw == 0:
            errors.append("Relaxation task but NSW=0 (no ionic steps). Set NSW > 0.")
        if "EDIFFG" not in tags:
            warnings.append(
                "No EDIFFG set for relaxation. Recommend EDIFFG=-0.01 to -0.05 (force criterion)."
            )

    if task_type == "md":
        if ibrion != 0:
            errors.append(f"MD task but IBRION={ibrion}. Set IBRION=0 for MD.")
        if "TEBEG" not in tags:
            warnings.append("MD task but TEBEG not set (temperature defaults to 0 K).")
        if nsw < 100:
            warnings.append(f"MD with NSW={nsw} is very short. Typically need 1000+ steps.")
        if ismear == -5:
            errors.append("ISMEAR=-5 is forbidden for MD. Use ISMEAR=0 or 1.")
        if "ISYM" not in tags or _as_int(_get(tags, "ISYM"), 2) != 0:
            warnings.append("For MD, set ISYM=0 to turn off symmetry.")

    if task_type == "band":
        if icharg != 11 and not _is_true(_get(tags, "LKPOINTS_OPT")):
            warnings.append(
                "Band structure typically needs ICHARG=11 (non-SCF from CHGCAR) "
                "or LKPOINTS_OPT=.TRUE. for hybrid functionals."
            )

    if task_type == "dos":
        if ismear != -5:
            warnings.append(
                f"DOS calculation with ISMEAR={ismear}. "
                "ISMEAR=-5 (tetrahedron+Blöchl) gives the most accurate DOS."
            )

    if task_type == "phonon":
        ediff = _as_float(_get(tags, "EDIFF"), 1e-4)
        if ediff > 1e-6:
            warnings.append(
                f"EDIFF={ediff} may be too loose for phonons. "
                "Recommend EDIFF=1E-7 or tighter."
            )

    if task_type == "hybrid":
        if not _is_true(_get(tags, "LHFCALC")):
            errors.append("Hybrid functional task but LHFCALC is not set to .TRUE.")
        if not _is_true(_get(tags, "LASPH")):
            warnings.append("Hybrid functionals should use LASPH=.TRUE.")

    if task_type == "gw":
        if "NBANDS" not in tags:
            warnings.append("GW calculations need many empty bands. Set NBANDS explicitly.")
        if "ENCUTGW" not in tags:
            warnings.append("ENCUTGW not set for GW. Converge this parameter.")

    return errors, warnings


# ── Convenience: validate INCAR file from path ──

def validate_incar_file(
    incar_path: str,
    task_type: str = "scf",
    system_info: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Read and validate an INCAR file."""
    with open(incar_path) as f:
        text = f.read()
    tags = parse_incar(text)
    return validate_incar(tags, task_type, system_info)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python validator.py <INCAR_path> [task_type]")
        sys.exit(1)

    path = sys.argv[1]
    task = sys.argv[2] if len(sys.argv) > 2 else "scf"

    errs, warns = validate_incar_file(path, task)

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
