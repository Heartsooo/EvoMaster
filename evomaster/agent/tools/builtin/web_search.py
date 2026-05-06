from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
from pydantic import Field

from ..base import BaseTool, BaseToolParams

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession


SEARCH_API_ENDPOINT = "https://www.searchapi.io/api/v1/search"


def _resolve_api_key() -> str:
    for var in ("SEARCHAPI_API_KEY", "SEARCHAPI_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


class WebSearchToolParams(BaseToolParams):
    """Search the web using a search query and return results.

    Before searching, first check loaded skills and tool descriptions.
    Use this only when the needed information is genuinely absent from
    local context, skills, or the current workspace.
    """

    name: ClassVar[str] = "web_search"

    query: str = Field(description="The search query to use")
    allowed_domains: list[str] = Field(
        default_factory=list,
        description="Only include search results from these domains",
    )
    blocked_domains: list[str] = Field(
        default_factory=list,
        description="Never include search results from these domains",
    )


class WebSearchTool(BaseTool):
    """Search the web via SearchApi.io and return compact results."""

    name: ClassVar[str] = "web_search"
    params_class: ClassVar[type[BaseToolParams]] = WebSearchToolParams

    def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
        try:
            params = self.parse_params(args_json)
        except Exception as e:
            return f"Parameter validation error: {str(e)}", {"error": str(e)}

        assert isinstance(params, WebSearchToolParams)

        query = (params.query or "").strip()
        if len(query) < 2:
            return "Error: query must be at least 2 characters.", {"error": "query_too_short"}

        api_key = _resolve_api_key()
        if not api_key:
            return (
                "Error: Missing SearchApi key. Set SEARCHAPI_API_KEY or SEARCHAPI_KEY.",
                {"error": "missing_api_key"},
            )

        allowed = params.allowed_domains or []
        blocked = params.blocked_domains or []
        if allowed and blocked:
            return (
                "Error: Cannot specify both allowed_domains and blocked_domains.",
                {"error": "conflicting_domain_filters"},
            )

        search_query = query
        if allowed:
            search_query += " " + " OR ".join(f"site:{d}" for d in allowed)
        for domain in blocked:
            search_query += f" -site:{domain}"

        request_params: dict[str, Any] = {
            "engine": "google",
            "q": search_query,
            "api_key": api_key,
        }

        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    SEARCH_API_ENDPOINT,
                    params=request_params,
                    headers={"User-Agent": "evomaster-web-search/1.0"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return f"Error: {type(exc).__name__}: {exc}", {"error": type(exc).__name__}

        organic = payload.get("organic_results", [])
        results = []
        for item in organic[:10]:
            if not isinstance(item, dict):
                continue
            link = str(item.get("link") or "").strip()
            if not link:
                continue
            results.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "link": link,
                    "snippet": str(item.get("snippet") or "").strip(),
                }
            )

        result_payload = {"results": results}
        return json.dumps(result_payload, ensure_ascii=False), {
            "result_count": len(results),
            "query": search_query,
        }
