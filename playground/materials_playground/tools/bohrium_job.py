"""EvoMaster-native Bohrium job tool for materials playground.

Supports Bohrium job submission and management actions:
- submit
- poll
- download
- list_images
- list_machines
- kill

Credentials are read from environment variables:
- BOHRIUM_ACCESS_KEY
- BOHRIUM_PROJECT_ID
- BOHRIUM_USER_ID (optional)
- BOHRIUM_USER_NO (optional)
- BOHRIUM_BASE_URL (optional)
- BOHRIUM_USE_SANDBOX (default: 1)
- SERVICE_ENV (default: test)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from urllib.parse import quote

import requests
from pydantic import Field

from evomaster.agent.tools.base import BaseTool, BaseToolParams

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession


STATUS_MAP = {
    -10: "Prepared",
    -2: "Deleted",
    -1: "Failed",
    0: "Pending",
    1: "Running",
    2: "Finished",
    3: "Scheduling",
    4: "Stopping",
    5: "Stopped",
    6: "Terminating",
    7: "Killing",
    8: "Uploading",
    9: "Wait",
}


class BohriumJobToolParams(BaseToolParams):
    name: ClassVar[str] = "bohrium_job"

    action: Literal["submit", "poll", "download", "kill", "list_images", "list_machines"] = Field(
        description="Bohrium operation to perform"
    )
    input_dir: str = Field(default="", description="Input directory for submit")
    image: str = Field(default="", description="Docker image for submit")
    cmd: str = Field(default="", description="Shell command for submit")
    machine: str = Field(default="c32_m128_cpu", description="Machine type for submit")
    job_name: str = Field(default="evomaster_job", description="Human-readable job name")
    disk_size: int = Field(default=50, description="Disk size in GB for non-sandbox submit")
    job_id: str = Field(default="", description="Job ID for poll/download/kill")
    result_dir: str = Field(default="", description="Target directory for download")
    keyword: str = Field(default="", description="Keyword filter for list actions")
    machine_type: Literal["cpu", "gpu"] = Field(default="cpu", description="Machine type filter")
    max_results: int = Field(default=20, description="Max returned records for list actions")


class BohriumJobTool(BaseTool):
    name: ClassVar[str] = "bohrium_job"
    params_class: ClassVar[type[BaseToolParams]] = BohriumJobToolParams

    def prompt(self) -> str:
        return (
            '## Bohrium tool usage\n'
            '- **Always** load the corresponding software skill first '
            '(cp2k, quantum_espresso, abacus, orca, lammps, gromacs, pyscf, abinit, pyatb, mlips) '
            'to obtain image, machine, script choice, and cmd template — do this **before** calling '
            '`list_images` or `list_machines`.\n'
            '- Only call `list_images` / `list_machines` when the loaded skill does not provide a '
            'default image or machine, or you need to verify current availability.\n'
            '- Python workflows that import ASE or use DPA/MACE/deepmd calculators should follow the '
            '`mlips` skill and use its recommended Bohrium image rather than guessing from memory.\n'
            '- For `submit`, the command should run directly inside the unpacked input directory and '
            'should write logs to `log`.\n'
        )

    def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
        try:
            params = self.parse_params(args_json)
        except Exception as exc:
            return f"Parameter validation error: {exc}", {"error": str(exc)}

        assert isinstance(params, BohriumJobToolParams)
        try:
            ctx = self._build_context(require_project=params.action in {"submit"})
            if params.action == "submit":
                return self._submit(session, ctx, params)
            if params.action == "poll":
                return self._poll(ctx, params)
            if params.action == "download":
                return self._download(session, ctx, params)
            if params.action == "kill":
                return self._kill(ctx, params)
            if params.action == "list_images":
                return self._list_images(ctx, params)
            if params.action == "list_machines":
                return self._list_machines(ctx, params)
            return f"Unsupported action: {params.action}", {"error": "unsupported_action"}
        except Exception as exc:
            self.logger.error("bohrium_job failed: %s", exc, exc_info=True)
            return f"bohrium_job error: {exc}", {"error": str(exc)}

    def _build_context(self, require_project: bool = False) -> dict[str, Any]:
        access_key = os.getenv("BOHRIUM_ACCESS_KEY", "").strip()
        if not access_key:
            raise ValueError("Missing BOHRIUM_ACCESS_KEY")
        try:
            project_id = int(os.getenv("BOHRIUM_PROJECT_ID", "-1"))
        except ValueError:
            project_id = -1
        if require_project and project_id <= 0:
            raise ValueError("Missing valid BOHRIUM_PROJECT_ID")
        base_url = (os.getenv("BOHRIUM_BASE_URL", "") or "").strip().rstrip("/")
        if not base_url:
            service_env = (os.getenv("SERVICE_ENV", "test") or "test").strip().lower()
            base_url = "https://openapi.dp.tech" if service_env == "prod" else f"https://openapi.{service_env}.dp.tech"
        sandbox = os.getenv("BOHRIUM_USE_SANDBOX", "1").strip() == "1"
        return {
            "access_key": access_key,
            "project_id": project_id,
            "base_url": base_url,
            "sandbox": sandbox,
        }

    def _headers(self, ctx: dict[str, Any]) -> dict[str, str]:
        return {
            "accessKey": ctx["access_key"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, ctx: dict[str, Any], path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = requests.get(f"{ctx['base_url']}{path}", headers=self._headers(ctx), params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _post(self, ctx: dict[str, Any], path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(f"{ctx['base_url']}{path}", headers=self._headers(ctx), json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _zip_input_dir(self, input_dir: Path) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="bohrium_submit_"))
        zip_path = tmp_dir / "input.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in input_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(input_dir))
        return zip_path

    def _upload_archive(self, create_data: dict[str, Any], zip_path: Path) -> dict[str, str]:
        try:
            from bohrium.resources.tiefblue import Tiefblue
        except ImportError as exc:
            raise RuntimeError("bohrium-sdk not installed. Run: pip install bohrium-sdk") from exc
        store_path = str(create_data["storePath"]).strip()
        if not store_path.endswith("/"):
            store_path += "/"
        store_host = str(create_data["storeHost"]).rstrip("/")
        token = str(create_data["token"]).strip()
        oss_key = f"{store_path}input.zip"
        client = Tiefblue(base_url=store_host)
        response = client.upload_From_file_multi_part(object_key=oss_key, file_path=str(zip_path), token=token, progress_bar=False)
        if response is not None and hasattr(response, "status_code") and response.status_code >= 400:
            raise RuntimeError(f"Upload failed: {response.text}")
        download_url = (
            f"{store_host}/api/download/{quote(oss_key, safe='/')}?token={token}"
            "&Response-Content-Type=application/octet-stream"
        )
        return {"oss_key": oss_key, "download_url": download_url}

    def _submit(self, session: BaseSession, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        input_dir = Path(params.input_dir).expanduser().resolve()
        if not input_dir.exists() or not input_dir.is_dir():
            raise ValueError(f"input_dir not found or not a directory: {params.input_dir}")
        cmd = params.cmd.rstrip()
        if not cmd.endswith("> log 2>&1"):
            cmd = cmd + " > log 2>&1"
        create_path = "/openapi/v1/sandbox/job/create" if ctx["sandbox"] else "/openapi/v1/job/create"
        create_payload = {"projectId": ctx["project_id"], "name": params.job_name} if ctx["sandbox"] else {"projectId": ctx["project_id"], "jobName": params.job_name}
        create_resp = self._post(ctx, create_path, create_payload)
        if create_resp.get("code") != 0:
            raise RuntimeError(f"job/create failed: {create_resp}")
        create_data = create_resp["data"]
        zip_path = self._zip_input_dir(input_dir)
        try:
            upload = self._upload_archive(create_data, zip_path)
        finally:
            shutil.rmtree(zip_path.parent, ignore_errors=True)
        if ctx["sandbox"]:
            add_path = "/openapi/v1/sandbox/job/add"
            add_payload = {
                "imageName": params.image,
                "scassType": params.machine,
                "jobName": params.job_name,
                "cmd": cmd,
                "jobId": str(create_data["jobId"]).strip(),
                "ossPath": [upload["download_url"]],
            }
        else:
            add_path = "/openapi/v2/job/add"
            add_payload = {
                "projectId": ctx["project_id"],
                "jobName": params.job_name,
                "jobType": "indicate",
                "scassType": params.machine,
                "cmd": cmd,
                "imageName": params.image,
                "ossPath": [upload["oss_key"]],
                "inputFileMethod": 1,
                "inputFileType": 3,
                "diskSize": params.disk_size,
                "logFiles": ["log"],
            }
        add_resp = self._post(ctx, add_path, add_payload)
        if add_resp.get("code") != 0:
            raise RuntimeError(f"job/add failed: {add_resp}")
        data = add_resp["data"]
        job_id = str(data.get("jobId") or "").strip()
        bohr_job_id = str(data.get("bohrJobId") or job_id).strip()
        msg = (
            f"Bohrium job submitted successfully. job_id={job_id}, bohr_job_id={bohr_job_id}, "
            f"image={params.image}, machine={params.machine}"
        )
        return msg, {"action": "submit", "job_id": job_id, "bohr_job_id": bohr_job_id, "job_name": params.job_name}

    def _poll(self, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        if not params.job_id.strip():
            raise ValueError("job_id is required for poll")
        path = f"/openapi/v1/sandbox/job/{params.job_id}" if ctx["sandbox"] else f"/openapi/v1/job/{params.job_id}"
        detail = self._get(ctx, path).get("data") or {}
        status_code = int(detail.get("status", 0))
        status = STATUS_MAP.get(status_code, f"Unknown({status_code})")
        msg = f"Bohrium job {params.job_id} status: {status} ({status_code})"
        return msg, {"action": "poll", "job_id": params.job_id, "status": status, "status_code": status_code, "detail": detail}

    def _download(self, session: BaseSession, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        if not params.job_id.strip() or not params.result_dir.strip():
            raise ValueError("job_id and result_dir are required for download")
        detail_path = f"/openapi/v1/sandbox/job/{params.job_id}" if ctx["sandbox"] else f"/openapi/v1/job/{params.job_id}"
        detail = self._get(ctx, detail_path).get("data") or {}
        result_dir = Path(params.result_dir).expanduser().resolve()
        result_dir.mkdir(parents=True, exist_ok=True)
        files = detail.get("outputFiles") or detail.get("files") or []
        downloaded = []
        for entry in files:
            file_path = entry.get("path") or entry.get("filePath")
            if not file_path:
                continue
            if ctx["sandbox"]:
                token_resp = self._post(ctx, "/openapi/v1/sandbox/job/file/token", {"filePath": file_path, "jobId": str(detail.get("bohrJobId") or params.job_id)})
                data = token_resp.get("data") or {}
                host = data.get("host", "")
                obj_path = data.get("path", "")
                token = data.get("token", "")
                if not host or not obj_path or not token:
                    continue
                url = f"{host}/api/download/{quote(obj_path, safe='/')}?token={token}&Response-Content-Type=application/octet-stream"
            else:
                url = entry.get("url") or entry.get("downloadUrl")
                if not url:
                    continue
            local_name = Path(file_path).name or f"artifact_{len(downloaded)+1}"
            dest = result_dir / local_name
            with requests.get(url, timeout=300, stream=True) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
            downloaded.append(str(dest))
        if downloaded:
            return f"Downloaded {len(downloaded)} artifacts to {result_dir}", {"action": "download", "job_id": params.job_id, "result_dir": str(result_dir), "files": downloaded}
        # Sandbox jobs can expose workspace outputs only via resultUrl zip
        # while outputFiles/files remains empty.
        result_url = str(detail.get("resultUrl") or "").strip()
        if result_url:
            archive_path = result_dir / f"{params.job_id}.zip"
            with requests.get(result_url, timeout=600, stream=True) as resp:
                resp.raise_for_status()
                with open(archive_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
            extracted_files: list[str] = []
            with zipfile.ZipFile(archive_path, "r") as zf:
                members: list[zipfile.ZipInfo] = []
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        continue
                    members.append(member)
                zf.extractall(result_dir, members=members)
                for member in members:
                    if not member.is_dir():
                        extracted_files.append(str(result_dir / member.filename))
            msg = f"Downloaded and extracted result archive to {result_dir} ({len(extracted_files)} files)"
            return msg, {
                "action": "download",
                "job_id": params.job_id,
                "result_dir": str(result_dir),
                "archive": str(archive_path),
                "files": extracted_files,
            }
        return "No downloadable artifacts found for this job.", {"action": "download", "job_id": params.job_id, "result_dir": str(result_dir), "files": []}

    def _kill(self, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        if not params.job_id.strip():
            raise ValueError("job_id is required for kill")
        if not ctx["sandbox"]:
            raise ValueError("kill is currently supported only when BOHRIUM_USE_SANDBOX=1")
        resp = self._post(ctx, f"/openapi/v1/sandbox/kill/{params.job_id}", {})
        if resp.get("code") != 0:
            raise RuntimeError(f"kill failed: {resp}")
        return f"Kill request sent for Bohrium job {params.job_id}", {"action": "kill", "job_id": params.job_id, "data": resp.get("data") or {}}

    def _list_images(self, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        data = self._get(ctx, "/openapi/v2/image/public", params={"page": 1, "pageSize": 200}).get("data") or {}
        items = data.get("items") or []
        keyword = params.keyword.strip().lower()
        if keyword:
            items = [x for x in items if keyword in str(x.get("name") or x.get("imageName") or "").lower() or keyword in str(x.get("description") or "").lower()]
        items = items[: max(1, params.max_results)]
        summary = []
        for item in items:
            name = item.get("name") or item.get("imageName") or ""
            desc = item.get("description") or ""
            summary.append({"id": item.get("id") or item.get("imageId"), "name": name, "description": desc})
        return f"Found {len(summary)} Bohrium images.", {"action": "list_images", "images": summary}

    def _list_machines(self, ctx: dict[str, Any], params: BohriumJobToolParams) -> tuple[str, dict[str, Any]]:
        data = self._get(
            ctx,
            "/openapi/v1/calc/list",
            params={
                "page": 1,
                "pageSize": 200,
                "scene": "job",
                "isVirtualNode": "false",
                "chooseType": params.machine_type,
                "productLine": "bohrium",
            },
        ).get("data") or {}
        items = data.get("items") or []
        keyword = params.keyword.strip().lower()
        if keyword:
            items = [x for x in items if keyword in str(x.get("skuEnName") or x.get("skuName") or "").lower()]
        items = items[: max(1, params.max_results)]
        summary = []
        for item in items:
            summary.append({
                "name": item.get("skuEnName") or item.get("skuName"),
                "cpu": item.get("cpuCoreNum"),
                "memory": item.get("memory"),
                "gpu": item.get("gpu"),
                "gpu_count": item.get("gpuCoreNum"),
                "price": item.get("price"),
                "has_stock": item.get("hasStock"),
            })
        return f"Found {len(summary)} Bohrium machines.", {"action": "list_machines", "machine_type": params.machine_type, "machines": summary}
