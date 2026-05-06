import json
from types import SimpleNamespace

from evomaster.agent.tools import create_registry


class DummyConn:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == 'search-papers-enhanced'
        assert arguments['question'] == 'nfpp photocatalyst'
        return [{
            'text': json.dumps({
                'data': [
                    {
                        'enName': 'Paper A',
                        'enAbstract': 'A' * 80,
                        'doi': '10.1/abc',
                        'publicationEnName': 'Journal X',
                        'impactFactor': 12.3,
                        'citationNums': 45,
                        'authors': ['Alice', 'Bob'],
                        'coverDateStart': '2024-01-01',
                    },
                    {
                        'zhName': '论文B',
                        'zhAbstract': '中文摘要',
                        'doi': '10.1/def',
                    },
                ]
            }, ensure_ascii=False)
        }]


def _tool():
    from evomaster.agent.tools.mcp import PaperSearchTool
    registry = create_registry(builtin_names=[])
    registry.register(PaperSearchTool())
    return registry.get_tool('paper_search')


def test_paper_search_requires_mcp_manager():
    tool = _tool()
    session = SimpleNamespace()
    obs, info = tool.execute(session, json.dumps({'question': 'nfpp photocatalyst'}))
    assert 'requires session._mcp_manager' in obs
    assert info['error'] == 'RuntimeError'


def test_paper_search_returns_slimmed_payload():
    tool = _tool()
    manager = SimpleNamespace(connections={'mat_sn': DummyConn()}, loop=None)
    session = SimpleNamespace(_mcp_manager=manager)
    obs, info = tool.execute(
        session,
        json.dumps({'question': 'nfpp photocatalyst', 'words': ['NFPP', 'photocatalyst'], 'n': 5}),
    )
    payload = json.loads(obs)
    assert len(payload['data']) == 2
    assert payload['data'][0]['enName'] == 'Paper A'
    assert payload['data'][0]['publicationEnName'] == 'Journal X'
    assert payload['data'][1]['enName'] == '论文B'
    assert payload['data'][1]['enAbstract'] == '中文摘要'
    assert info['result_count'] == 2
    assert info['mcp_server'] == 'mat_sn'
