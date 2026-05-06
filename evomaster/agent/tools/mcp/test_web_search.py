import json
import os
from unittest.mock import Mock, patch

from evomaster.agent.tools import create_registry


def _tool():
    from evomaster.agent.tools.mcp import WebSearchTool
    registry = create_registry(builtin_names=[])
    registry.register(WebSearchTool())
    return registry.get_tool('web_search')


def test_web_search_requires_api_key():
    tool = _tool()
    with patch.dict(os.environ, {}, clear=True):
        obs, info = tool.execute(None, json.dumps({'query': 'copper fcc'}))
    assert 'Missing SearchApi key' in obs
    assert info['error'] == 'missing_api_key'


def test_web_search_returns_compact_results():
    tool = _tool()
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        'organic_results': [
            {'title': 'Result A', 'link': 'https://a.test', 'snippet': 'Snippet A'},
            {'title': 'Result B', 'link': 'https://b.test', 'snippet': 'Snippet B'},
        ]
    }

    with patch.dict(os.environ, {'SEARCHAPI_API_KEY': 'dummy'}, clear=False):
        with patch('evomaster.agent.tools.mcp.web_search.httpx.Client') as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.return_value = mock_response
            obs, info = tool.execute(
                None,
                json.dumps({'query': 'copper', 'allowed_domains': ['example.com']}),
            )

    payload = json.loads(obs)
    assert len(payload['results']) == 2
    assert payload['results'][0]['link'] == 'https://a.test'
    assert info['result_count'] == 2
    assert 'site:example.com' in info['query']
