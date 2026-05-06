"""Bohrium authentication and MCP calculation storage/executor configuration.

Used by the MCP calculation path adaptor. Reads BOHRIUM_* from environment variables (.env)
to generate HTTPS storage and inject executor authentication information.
Aligned with the private_callback in _tmp/MatMaster.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict

from dotenv import load_dotenv


def _load_project_env() -> None:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)


_load_project_env()


def get_bohrium_service_env() -> str:
    raw = (os.getenv("SERVICE_ENV", "test") or "").strip().lower()
    return raw or "test"


def get_bohrium_base_url() -> str:
    override = (os.getenv("BOHRIUM_BASE_URL", "") or "").strip().rstrip("/")
    if override:
        return override
    service_env = get_bohrium_service_env()
    if service_env == "prod":
        return "https://openapi.dp.tech"
    return f"https://openapi.{service_env}.dp.tech"


def get_bohrium_credentials() -> Dict[str, Any]:
    """Read Bohrium credentials from environment variables (.env or os.environ)."""
    access_key = os.getenv("BOHRIUM_ACCESS_KEY", "").strip()
    try:
        project_id = int(os.getenv("BOHRIUM_PROJECT_ID", "-1"))
    except (TypeError, ValueError):
        project_id = -1
    try:
        user_id = int(os.getenv("BOHRIUM_USER_ID", "-1"))
    except (TypeError, ValueError):
        user_id = -1
    return {
        "access_key": access_key,
        "project_id": project_id,
        "user_id": user_id,
        "base_url": get_bohrium_base_url(),
    }


def get_bohrium_storage_config() -> Dict[str, Any]:
    """HTTPS storage for MCP calculation (type https + Bohrium plugin)."""
    cred = get_bohrium_credentials()
    return {
        "type": "https",
        "plugin": {
            "type": "bohrium",
            "access_key": cred["access_key"],
            "project_id": cred["project_id"],
            "app_key": "agent",
        },
    }


def inject_bohrium_executor(executor_template: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-copy an executor template and inject BOHRIUM_* credentials (aligned with MatMaster private_callback)."""
    executor = copy.deepcopy(executor_template)
    cred = get_bohrium_credentials()
    if executor.get("type") == "dispatcher":
        rp = executor.setdefault("machine", {}).setdefault("remote_profile", {})
        rp["access_key"] = cred["access_key"]
        rp["project_id"] = cred["project_id"]
        rp["real_user_id"] = cred["user_id"]
        resources = executor.setdefault("resources", {})
        envs = resources.setdefault("envs", {})
        envs["BOHRIUM_PROJECT_ID"] = cred["project_id"]
        envs["BOHRIUM_BASE_URL"] = cred["base_url"]
    return executor
