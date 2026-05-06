"""MCP (Model Context Protocol) tools module.

Provides MCP protocol support, allowing Agents to use tools from external MCP servers.
"""

from .mcp import MCPTool
from .mcp_manager import MCPToolManager
from .mcp_connection import MCPConnection, create_connection
from .web_search import WebSearchTool, WebSearchToolParams
from .paper_search import PaperSearchTool, PaperSearchToolParams

__all__ = [
    "MCPTool",
    "MCPToolManager",
    "MCPConnection",
    "create_connection",
    "WebSearchTool",
    "WebSearchToolParams",
    "PaperSearchTool",
    "PaperSearchToolParams",
]
