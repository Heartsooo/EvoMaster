"""_calculator.py — Multi-MLIP ASE calculator factory.

Provides a unified interface for constructing ASE calculators from different
machine-learning interatomic potential (MLIP) families.  DPA is the default
and primary model; MACE, SevenNet, and MatterSim are also supported.

Usage (inside other scripts in this directory)::

    from _calculator import build_calculator, build_fparam, set_fparam

    calc = build_calculator("DPA3.1-3M", head="Omat24")
    atoms.calc = calc
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

import numpy as np

try:
    from ase.calculators.calculator import Calculator
except ImportError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ase"])
    from ase.calculators.calculator import Calculator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known pretrained models — name → metadata
# ---------------------------------------------------------------------------

KNOWN_MODELS: dict[str, dict] = {
    # ── DPA (default / primary) ──────────────────────────────────────────
    "DPA2.4-7M": {
        "family": "DP",
        "url": "https://bohrium.oss-cn-zhangjiakou.aliyuncs.com/13756/27666/store/upload/cd12300a-d3e6-4de9-9783-dd9899376cae/dpa-2.4-7M.pt",
        "default_head": "Omat24",
    },
    "DPA3.1-3M": {
        "family": "DP",
        "url": "https://bohrium.oss-cn-zhangjiakou.aliyuncs.com/13756/27666/store/upload/18b8f35e-69f5-47de-92ef-af8ef2c13f54/DPA-3.1-3M.pt",
        "default_head": "Omat24",
    },
    "DPA3.2-5M": {
        "family": "DP",
        "url": "https://dp-storage-test2.oss-cn-zhangjiakou.aliyuncs.com/bohrium-test/bohrium/feedback/attachment/01KF3BF3TX9GVTC96Q0PCV01H3/DPA-3.2-5M.pt",
        "default_head": "Omat24",
    },
    # ── MACE ──────────────────────────────────────────────────────────────
    "MACE-MP-0": {"family": "MACE", "model_id": "medium"},
    "MACE-MPA-0": {
        "family": "MACE",
        "url": "https://github.com/ACEsuit/mace-mp/releases/download/mace_mpa_0/mace-mpa-0-medium.model",
    },
    # ── SevenNet ──────────────────────────────────────────────────────────
    "SevenNet-0": {"family": "SevenNet", "model_id": "SevenNet-0"},
    "7net-mf-ompa": {"family": "SevenNet", "model_id": "7net-mf-ompa"},
    # ── MatterSim ─────────────────────────────────────────────────────────
    "MatterSim-v1-5M": {"family": "MatterSim"},
}

# Reverse lookup: URL filename stem → model name (for docstring references)
_URL_STEM_MAP: dict[str, str] = {}
for _name, _meta in KNOWN_MODELS.items():
    _u = _meta.get("url")
    if _u:
        _stem = Path(_u.rstrip("/").rsplit("/", 1)[-1]).stem
        _URL_STEM_MAP[_stem.lower()] = _name


# ---------------------------------------------------------------------------
# Model resolution helpers
# ---------------------------------------------------------------------------

_MODEL_CACHE_DIR = Path(os.environ.get("MLIP_MODEL_CACHE", ".mlip_models"))


def _download_model(url: str) -> Path:
    """Download a model file from *url* into a local cache directory."""
    _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = url.rstrip("/").rsplit("/", 1)[-1]
    dest = _MODEL_CACHE_DIR / filename
    if dest.exists():
        logger.info("Model already cached at %s", dest)
        return dest
    logger.info("Downloading model from %s → %s", url, dest)
    urllib.request.urlretrieve(url, dest)
    return dest


def resolve_model(model_name_or_path: str) -> tuple[str, Path | str | None]:
    """Resolve a model specifier to ``(family, local_path_or_id)``.

    * Known name  → ``(family, downloaded_path)``
    * URL (http)  → ``("DP", downloaded_path)``
    * Local path  → family guessed from extension
    """
    # Known model name
    if model_name_or_path in KNOWN_MODELS:
        meta = KNOWN_MODELS[model_name_or_path]
        family = meta["family"]
        url = meta.get("url")
        model_id = meta.get("model_id")
        if url:
            return family, _download_model(url)
        if model_id:
            return family, model_id
        return family, None

    # URL
    if model_name_or_path.startswith("http://") or model_name_or_path.startswith(
        "https://"
    ):
        return "DP", _download_model(model_name_or_path)

    # Local path
    p = Path(model_name_or_path)
    if p.suffix in {".pt", ".pth", ".pb"}:
        return "DP", p
    if p.suffix == ".model":
        return "MACE", p
    # Default to DP
    return "DP", p


# ---------------------------------------------------------------------------
# Calculator dispatch
# ---------------------------------------------------------------------------


def _init_dp(model_path: Path | str, head: str | None = None) -> Calculator:
    from deepmd.calculator import DP

    path = str(model_path)
    if path.endswith(".pt") or path.endswith(".pth"):
        return DP(model=path, head=head or "Omat24")
    return DP(model=path)


def _init_mace(model_path: Path | str | None, **_kw) -> Calculator:
    try:
        from mace.calculators import mace_mp
    except ImportError as exc:
        raise ImportError("MACE is not installed. Run: pip install mace-torch") from exc
    kw: dict = {"device": "cuda", "default_dtype": "float64"}
    if model_path is not None:
        kw["model"] = str(model_path)
    return mace_mp(**kw)


def _init_sevennet(model_id: str | None, **_kw) -> Calculator:
    try:
        from sevenn.sevennet_calculator import SevenNetCalculator
    except ImportError as exc:
        raise ImportError("SevenNet is not installed. Run: pip install sevenn") from exc
    name = model_id or "SevenNet-0"
    kw: dict = {"model": name, "device": "cuda"}
    if name == "7net-mf-ompa":
        kw["modal"] = "omat24"
    return SevenNetCalculator(**kw)


def _init_mattersim(**_kw) -> Calculator:
    try:
        from mattersim.forcefield import MatterSimCalculator
    except ImportError as exc:
        raise ImportError(
            "MatterSim is not installed. Run: pip install mattersim"
        ) from exc
    return MatterSimCalculator(load_path="MatterSim-v1.0.0-5M.pth", device="cuda")


_FAMILY_INIT = {
    "DP": _init_dp,
    "MACE": _init_mace,
    "SevenNet": _init_sevennet,
    "MatterSim": _init_mattersim,
}


def build_calculator(
    model_name_or_path: str,
    head: str | None = None,
) -> Calculator:
    """Build an ASE Calculator from a model name, path, or URL.

    Parameters
    ----------
    model_name_or_path
        One of: a known model name (e.g. ``"DPA3.1-3M"``), a URL, or a
        local file path.
    head
        Model head (DP family only). E.g. ``"Omat24"``, ``"OMol25"``.
        Ignored for non-DP families.

    Returns
    -------
    ase.calculators.calculator.Calculator
    """
    family, resolved = resolve_model(model_name_or_path)
    logger.info(
        "Building %s calculator: family=%s, resolved=%s",
        model_name_or_path,
        family,
        resolved,
    )

    init_fn = _FAMILY_INIT.get(family)
    if init_fn is None:
        raise ValueError(
            f"Unknown model family {family!r}. " f"Supported: {sorted(_FAMILY_INIT)}"
        )

    if family == "DP":
        # Head: explicit arg > model metadata > "Omat24"
        if head is None and model_name_or_path in KNOWN_MODELS:
            head = KNOWN_MODELS[model_name_or_path].get("default_head")
        return init_fn(resolved, head=head)

    return init_fn(resolved)


# ---------------------------------------------------------------------------
# fparam helpers (charge / spin multiplicity for DPA3.2-5M)
# ---------------------------------------------------------------------------


def build_fparam(
    charge: int | None = None,
    spin_multiplicity: int | None = None,
) -> np.ndarray | None:
    """Build ``fparam`` array for DeePMD-kit models that accept frame params.

    DPA3.2-5M uses ``numb_fparam=2``, order ``[charge, spin_multiplicity]``.
    If only one is given the other gets a physically neutral default.

    Returns ``None`` when neither is provided.
    """
    if charge is None and spin_multiplicity is None:
        return None
    if charge is None:
        logger.warning(
            "spin_multiplicity=%s given without charge; defaulting charge=0.",
            spin_multiplicity,
        )
        charge = 0
    if spin_multiplicity is None:
        logger.warning(
            "charge=%s given without spin_multiplicity; defaulting spin_multiplicity=1.",
            charge,
        )
        spin_multiplicity = 1
    return np.array(
        [float(charge), float(spin_multiplicity)], dtype=np.float64
    ).reshape(1, 2)


def set_fparam(atoms, fparam: np.ndarray | None) -> None:
    """Attach *fparam* to ``atoms.info`` so DP calculator reads it."""
    if fparam is not None:
        atoms.info["fparam"] = fparam
