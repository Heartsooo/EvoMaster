from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..base import BaseTool, BaseToolParams

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession


MAT_SN_SERVER = 'mat_sn'
REMOTE_TOOL = 'search-papers-enhanced'
_SLIM_EXTRA_KEYS = frozenset({
    'doi',
    'authors',
    'coverDateStart',
    'title',
    'publicationEnName',
    'citationNums',
    'impactFactor',
})
_ABSTRACT_MAX = 500


def _s(val: Any) -> str:
    return val.strip() if isinstance(val, str) else ''


def _truncate(text: str, max_chars: int) -> str:
    if not text:
        return ''
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(' ', 1)[0] + ' [...]'


def _mcp_content_to_text(result_content: list[Any]) -> str:
    parts: list[str] = []
    for item in result_content:
        if hasattr(item, 'text'):
            parts.append(item.text)
        elif isinstance(item, dict) and 'text' in item:
            parts.append(item['text'])
        else:
            parts.append(str(item))
    if not parts:
        return ''
    if len(parts) == 1:
        text = parts[0].strip()
        if text.startswith('{') or text.startswith('['):
            try:
                parsed = json.loads(text)
                return json.dumps(parsed, ensure_ascii=False, default=str)
            except json.JSONDecodeError:
                return text
        return text
    return '\n'.join(parts)


def _slim_paper_item(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    title = _s(item.get('enName')) or _s(item.get('zhName'))
    if title:
        out['enName'] = title
    abstract = _s(item.get('enAbstract')) or _s(item.get('zhAbstract'))
    if abstract:
        out['enAbstract'] = _truncate(abstract, _ABSTRACT_MAX)
    for key in _SLIM_EXTRA_KEYS:
        if key not in item:
            continue
        value = item[key]
        if value in (None, '', []):
            continue
        out[key] = value
    return out


class PaperSearchToolParams(BaseToolParams):
    """Search academic papers by keywords and a research question.

    Returns a compact list: one title and one abstract per item, plus DOI,
    date, authors, journal name, impact factor, and citation count.
    Uses the configured mat_sn MCP server.
    """

    name: ClassVar[str] = 'paper_search'

    words: list[str] = Field(default_factory=list, description='Core keywords.')
    question: str = Field(description='Natural-language research question or search intent.')
    start_time: str | None = Field(default=None, description='Start date YYYY-MM-DD.')
    end_time: str | None = Field(default=None, description='End date YYYY-MM-DD.')
    n: int | None = Field(default=20, description='Maximum number of results (1-100).')
    rerank: int | None = Field(default=1, description='Whether to rerank results, 0 or 1.')


class PaperSearchTool(BaseTool):
    name: ClassVar[str] = 'paper_search'
    params_class: ClassVar[type[BaseToolParams]] = PaperSearchToolParams

    def _default_date_range(self) -> tuple[str, str]:
        return '2000-01-01', date.today().isoformat()

    def _build_mcp_arguments(self, params: PaperSearchToolParams) -> dict[str, Any]:
        start_default, end_default = self._default_date_range()
        payload: dict[str, Any] = {
            'words': [w for w in (params.words or []) if isinstance(w, str) and w.strip()],
            'question': (params.question or '').strip(),
            'start_time': params.start_time or start_default,
            'end_time': params.end_time or end_default,
        }
        if not payload['question']:
            raise ValueError('question is required')

        n = params.n
        if n is not None:
            payload['page_size'] = max(1, min(100, int(n)))
        else:
            payload['page_size'] = 20

        rerank = params.rerank
        if rerank is not None:
            payload['rerank'] = 1 if int(rerank) else 0

        return payload

    def _slim_payload(self, raw: dict[str, Any]) -> dict[str, Any]:
        data = raw.get('data')
        if not isinstance(data, list):
            return {'data': []}
        return {'data': [_slim_paper_item(item) for item in data if isinstance(item, dict)]}

    def _resolve_mcp_connection(self, session: BaseSession):
        manager = getattr(session, '_mcp_manager', None)
        if manager is None:
            raise RuntimeError('paper_search requires session._mcp_manager to be set')
        conn = getattr(manager, 'connections', {}).get(MAT_SN_SERVER)
        if conn is None:
            raise RuntimeError("paper_search requires MCP server 'mat_sn' to be configured")
        return conn, getattr(manager, 'loop', None)

    def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
        try:
            params = self.parse_params(args_json)
            assert isinstance(params, PaperSearchToolParams)
            mcp_args = self._build_mcp_arguments(params)
            conn, loop = self._resolve_mcp_connection(session)
        except Exception as e:
            return f'Error: {e}', {'error': type(e).__name__}

        coro = conn.call_tool(REMOTE_TOOL, mcp_args)
        try:
            if loop is None:
                raw_content = asyncio.run(coro)
            elif not loop.is_running():
                raw_content = loop.run_until_complete(coro)
            else:
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                raw_content = future.result(timeout=60)
        except Exception as e:
            return f'Error: {type(e).__name__}: {e}', {'error': type(e).__name__}

        text = _mcp_content_to_text(raw_content)
        if not text.strip():
            return json.dumps({'data': []}, ensure_ascii=False), {'result_count': 0}

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text, {'raw_text': True}

        if not isinstance(parsed, dict):
            return text, {'raw_text': True}

        slim = self._slim_payload(parsed)
        return json.dumps(slim, ensure_ascii=False), {
            'result_count': len(slim.get('data', [])),
            'mcp_server': MAT_SN_SERVER,
            'remote_tool': REMOTE_TOOL,
        }
