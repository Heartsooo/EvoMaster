"""Materials Playground Implementation.

Lightweight single-agent playground for computational materials workflows.
Suitable for structure analysis, simulation planning, input generation,
result summarization, and literature-assisted materials tasks.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from evomaster.core import BasePlayground, register_playground
from evomaster.agent.tools import MCPToolManager


@register_playground("materials_playground")
class MaterialsPlayground(BasePlayground):
    """Minimal computational-materials playground."""

    def __init__(self, config_dir: Path = None, config_path: Path = None):
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "materials_playground"

        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _configure_mcp_manager(self, manager: MCPToolManager, mcp_config: Dict[str, Any]) -> None:
        include_only = mcp_config.get("tool_include_only")
        if include_only and isinstance(include_only, dict):
            manager.tool_include_only = {
                key: list(value) if isinstance(value, (list, tuple)) else []
                for key, value in include_only.items()
            }
            self.logger.info("MCP tool_include_only set for servers: %s", list(manager.tool_include_only.keys()))
