"""MCP tool integration.

Wraps MCP (Model Context Protocol) server tools as EvoMaster tools.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..base import BaseTool, ToolError

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession
    from evomaster.utils.types import ToolSpec


class MCPTool(BaseTool):
    """MCP tool wrapper.

    Wraps a single MCP tool as an EvoMaster BaseTool.

    Features:
    - Dynamic tools: Obtained from MCP servers at runtime
    - Async-to-sync: MCP is asynchronous and needs conversion
    - Schema conversion: MCP schema -> ToolSpec
    - Metadata tagging: Tags tool origin (MCP server)

    Usage example:
        mcp_tool = MCPTool(
            mcp_connection=connection,
            tool_name="github_create_issue",
            tool_description="Create a new GitHub issue",
            input_schema={...}
        )
        observation, info = mcp_tool.execute(session, args_json)
    """

    # Class attributes (required by BaseTool)
    name: ClassVar[str] = "mcp_tool"  # Will be overridden by instance attribute
    params_class: ClassVar[type] = None  # MCP tools do not use params_class

    def __init__(
        self,
        mcp_connection,  # MCPConnection instance
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        remote_tool_name: str | None = None,
    ):
        """Initialize the MCP tool.

        Args:
            mcp_connection: MCP connection instance.
            tool_name: Tool name (with server prefix added).
            tool_description: Tool description.
            input_schema: Input parameter schema (JSON Schema format).
        """
        super().__init__()

        # MCP-related attributes
        self.mcp_connection = mcp_connection
        self._tool_name = tool_name
        self._tool_description = tool_description
        self._input_schema = input_schema
        self._remote_tool_name = remote_tool_name
        # Dedicated MCP event loop (injected by MCPToolManager or Playground)
        self._mcp_loop = None

        # Override class attribute
        self.name = tool_name

        # Metadata tags (set by MCPToolManager)
        self._is_mcp_tool = True
        self._mcp_server = None  # Server name

        # Statistics
        self._call_count = 0
        self._last_error = None

    def execute(
        self,
        session: BaseSession,
        args_json: str
    ) -> tuple[str, dict[str, Any]]:
        """Execute the MCP tool.

        Args:
            session: Session instance (not used by MCP tools, kept for interface consistency).
            args_json: JSON-formatted arguments.

        Returns:
            (observation, info) tuple:
            - observation: Observation result returned to the Agent.
            - info: Additional information (including MCP metadata).
        """
        try:
            # 1. Parse arguments
            args = json.loads(args_json)
            self.logger.debug(f"Executing MCP tool {self._tool_name} with args: {args}")

            # 2. Apply path adaptor (if configured via playground hook)
            # Transforms arguments before sending to MCP tool (e.g., path conversion, credential injection)
            path_adaptor = getattr(self, "_path_adaptor", None)
            if path_adaptor is not None:
                workspace_path = (
                    getattr(getattr(session, "config", None), "workspace_path", None)
                    if session
                    else None
                ) or ""
                args = path_adaptor.resolve_args(
                    workspace_path,
                    args,
                    self._tool_name,
                    self._mcp_server or "",
                    input_schema=getattr(self, "_input_schema", None),
                )

            # 2.5 Compatibility rewrite for parse-file on remote MCP servers.
            # If caller passes local file_path, upload to OSS and switch to parse-url.
            args, remote_tool_override = self._rewrite_remote_tool_args(session, args)

            # 3. Call MCP tool (async-to-sync)
            result = self._call_mcp_tool_sync(args, remote_tool_name=remote_tool_override)

            # 3.5 Materialize MCP artifacts into current workspace when possible.
            result = self._materialize_result_artifacts(session, result)

            # 4. Format output
            observation = self._format_mcp_result(result)
            parsed_result = self._extract_structured_result(result)

            # 5. Update statistics
            self._call_count += 1
            self._last_error = None

            info = {
                "mcp_tool": self._tool_name,
                "mcp_server": self._mcp_server,
                "success": True,
                "call_count": self._call_count,
            }
            if parsed_result is not None:
                info["parsed_result"] = parsed_result

            return observation, info

        except json.JSONDecodeError as e:
            self._last_error = str(e)
            raise ToolError(f"Invalid JSON arguments: {str(e)}")
        except Exception as e:
            self._last_error = str(e)
            self.logger.error(f"MCP tool {self._tool_name} failed: {e}")
            raise ToolError(f"MCP tool execution failed: {str(e)}")

    def _call_mcp_tool_sync(self, args: dict, remote_tool_name: str | None = None) -> Any:
        """Synchronously call an MCP tool (handles async internally).

        IMPORTANT: Do not use asyncio.run() which creates a temporary loop. The coroutine
        must be submitted to the same long-lived loop to avoid anyio/mcp stream deadlocks,
        ClosedResourceError, and cancel scope misalignment.
        """
        # 1) A persistent MCP loop must have been injected
        loop = getattr(self, "_mcp_loop", None)
        if loop is None:
            raise ToolError(
                "MCP loop not injected into MCPTool. "
                "Please set mcp_tool._mcp_loop = <persistent_event_loop> when creating tools."
            )
        if loop.is_closed():
            raise ToolError("MCP loop is closed; cannot call MCP tool")

        target_tool_name = remote_tool_name or self._remote_tool_name
        coro = self.mcp_connection.call_tool(target_tool_name, args)

        try:
            # 2) If the loop is not currently running (most common: synchronous Agent scenario), run directly
            if not loop.is_running():
                return loop.run_until_complete(coro)

            # 3) If the loop is running (e.g. run_forever in a background thread), use thread-safe submission
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result(timeout=60)

        except concurrent.futures.TimeoutError:
            raise ToolError("MCP tool call timed out after 60 seconds")
        except Exception as e:
            raise ToolError(f"Failed to call MCP tool: {str(e)}")

    def _rewrite_remote_tool_args(
        self,
        session: BaseSession | None,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        """Rewrite tool args for server-specific compatibility.

        Current rule:
        - mat_sn.parse-file with local `file_path` -> upload to OSS and call parse-url.
        """
        if (self._mcp_server or "") != "mat_sn":
            return args, None
        if (self._remote_tool_name or "") != "parse-file":
            return args, None
        file_path = args.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            return args, None
        file_path = file_path.strip()
        if file_path.startswith(("http://", "https://")):
            return args, None

        workspace_root = self._get_workspace_root(session)
        if workspace_root is None:
            return args, None

        local_path = Path(file_path)
        if not local_path.is_absolute():
            local_path = (workspace_root / local_path).resolve()
        if not local_path.exists() or not local_path.is_file():
            return args, None

        try:
            from playground.mat_master.adaptors.calculation.oss_upload import upload_file_to_oss

            url = upload_file_to_oss(local_path, workspace_root, oss_prefix="evomaster/mat_sn_parse")
            rewritten = dict(args)
            rewritten.pop("file_path", None)
            rewritten["url"] = url
            self.logger.info(
                "Rewrote mat_sn parse-file to parse-url via OSS upload: %s -> %s",
                local_path,
                url,
            )
            return rewritten, "parse-url"
        except Exception as e:
            self.logger.warning("Failed to rewrite mat_sn parse-file args: %s", e)
            return args, None

    def _format_mcp_result(self, result: Any) -> str:
        """Format the MCP tool return result.

        MCP returns a content list; text content needs to be extracted.
        Supports multiple content types: text, json, image, etc.

        Args:
            result: Raw result returned by the MCP tool.

        Returns:
            Formatted string.
        """
        if isinstance(result, list):
            # MCP returns a content list
            parts = []
            for item in result:
                # Handle different content types
                if hasattr(item, 'text'):
                    # Pydantic model
                    parts.append(item.text)
                elif isinstance(item, dict):
                    if 'text' in item:
                        parts.append(item['text'])
                    elif 'type' in item and item['type'] == 'text':
                        parts.append(item.get('text', ''))
                    else:
                        # Other content types, convert to JSON
                        parts.append(json.dumps(item, indent=2))
                else:
                    parts.append(str(item))
            return "\n".join(parts) if parts else ""
        elif isinstance(result, str):
            return result
        elif result is None:
            return ""
        else:
            # Other types, convert to JSON
            return json.dumps(result, indent=2, default=str)

    def _extract_structured_result(self, result: Any) -> Any:
        if isinstance(result, list):
            if len(result) == 1:
                item = result[0]
                if hasattr(item, 'text'):
                    return self._extract_structured_result(item.text)
                if isinstance(item, dict) and 'text' in item:
                    return self._extract_structured_result(item.get('text'))
            return json.loads(json.dumps(result, default=str))

        if isinstance(result, dict):
            return json.loads(json.dumps(result, default=str))

        if isinstance(result, str):
            text = result.strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                return None

        try:
            return json.loads(json.dumps(result, default=str))
        except Exception:
            return None

    def _get_workspace_root(self, session: BaseSession | None) -> Path | None:
        if session is None:
            return None
        workspace = None
        getter = getattr(session, 'get_workspace_path', None)
        if callable(getter):
            try:
                workspace = getter()
            except Exception:
                workspace = None
        if not workspace:
            workspace = getattr(getattr(session, 'config', None), 'workspace_path', None)
        if not workspace:
            return None
        try:
            return Path(str(workspace)).resolve()
        except Exception:
            return None

    def _looks_like_local_path(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        if text.startswith(('http://', 'https://')):
            return False
        if text.startswith('local://'):
            text = text[len('local://'):]
        path = Path(text)
        return path.is_absolute()

    def _copy_one_artifact(self, source_value: str, workspace_root: Path, tool_slug: str) -> str:
        raw = source_value.strip()
        display = raw
        if raw.startswith('local://'):
            raw = raw[len('local://'):]
        src = Path(raw)
        if not src.exists():
            if display.startswith('local://'):
                return 'remote://' + raw
            if src.is_absolute():
                return 'remote://' + raw
            return display

        target_root = workspace_root / 'downloads' / 'mcp' / tool_slug
        target_root.mkdir(parents=True, exist_ok=True)

        if src.is_file():
            target = target_root / src.name
            if not target.exists():
                shutil.copy2(src, target)
            return str(target)

        if src.is_dir():
            target = target_root / src.name
            if not target.exists():
                shutil.copytree(src, target)
            return str(target)

        return display

    def _materialize_result_artifacts(self, session: BaseSession | None, result: Any) -> Any:
        workspace_root = self._get_workspace_root(session)
        if workspace_root is None:
            return result

        tool_slug = (self._tool_name or 'mcp_tool').replace('/', '_').replace(':', '_')

        def walk(value: Any, key: str | None = None) -> Any:
            artifact_keys = {'output_dir', 'files', 'structure_files', 'structure_file'}
            if isinstance(value, dict):
                return {k: walk(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [walk(v, key) for v in value]
            if isinstance(value, Path):
                return self._copy_one_artifact(str(value), workspace_root, tool_slug)
            if isinstance(value, str) and (key in artifact_keys or self._looks_like_local_path(value)):
                return self._copy_one_artifact(value, workspace_root, tool_slug)
            return value

        try:
            return walk(result)
        except Exception as e:
            self.logger.warning('Failed to materialize MCP artifacts for %s: %s', self._tool_name, e)
            return result

    def get_tool_spec(self) -> ToolSpec:
        """Get tool specification (used for LLM function calling).

        Converts MCP schema to EvoMaster ToolSpec.

        Returns:
            ToolSpec instance.
        """
        from evomaster.utils.types import FunctionSpec, ToolSpec

        return ToolSpec(
            type="function",
            function=FunctionSpec(
                name=self._tool_name,
                description=self._tool_description,
                parameters=self._input_schema,
                strict=None,
            )
        )

    def get_stats(self) -> dict[str, Any]:
        """Get tool statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "tool_name": self._tool_name,
            "mcp_server": self._mcp_server,
            "call_count": self._call_count,
            "last_error": self._last_error,
        }
