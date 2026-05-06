from pathlib import Path
from types import SimpleNamespace

from evomaster.agent.tools.mcp.mcp import MCPTool


class _DummyConn:
    pass


def test_materialize_result_artifacts_copies_local_paths(tmp_path):
    src_dir = tmp_path / 'remote_src'
    src_dir.mkdir()
    src_file = src_dir / 'a.cif'
    src_file.write_text('data', encoding='utf-8')

    workspace = tmp_path / 'workspace'
    workspace.mkdir()

    tool = MCPTool(_DummyConn(), 'mat_struct_db_fetch_structures_from_db', 'desc', {})
    session = SimpleNamespace(
        get_workspace_path=lambda: str(workspace),
        config=SimpleNamespace(workspace_path=str(workspace)),
    )

    result = {
        'output_dir': f'local://{src_dir}',
        'structure_files': [f'local://{src_file}'],
        'results': [{'structure_file': str(src_file)}],
    }

    materialized = tool._materialize_result_artifacts(session, result)

    copied_dir = workspace / 'downloads' / 'mcp' / 'mat_struct_db_fetch_structures_from_db' / 'remote_src'
    copied_file = workspace / 'downloads' / 'mcp' / 'mat_struct_db_fetch_structures_from_db' / 'a.cif'

    assert copied_dir.exists()
    assert copied_file.exists()
    assert materialized['output_dir'] == str(copied_dir)
    assert materialized['structure_files'][0] == str(copied_file)
    assert materialized['results'][0]['structure_file'] == str(copied_file)


def test_extract_structured_result_parses_single_text_block():
    tool = MCPTool(_DummyConn(), 'mat_struct_db_fetch_structures_from_db', 'desc', {})
    result = [{'type': 'text', 'text': '{"output_dir":"https://example.com/a.tgz","files":["https://example.com/f.cif"]}'}]
    parsed = tool._extract_structured_result(result)
    assert parsed['output_dir'] == 'https://example.com/a.tgz'
    assert parsed['files'][0] == 'https://example.com/f.cif'


def test_rewrite_mat_sn_parse_file_to_parse_url(tmp_path, monkeypatch):
    pdf = tmp_path / 'proof.pdf'
    pdf.write_bytes(b'%PDF-1.4 test')

    def _fake_upload(local_path, workspace_root, oss_prefix=""):
        assert Path(local_path) == pdf
        assert Path(workspace_root) == tmp_path.resolve()
        return 'https://example.com/uploaded/proof.pdf'

    monkeypatch.setattr(
        'playground.mat_master.adaptors.calculation.oss_upload.upload_file_to_oss',
        _fake_upload,
    )

    tool = MCPTool(_DummyConn(), 'mat_sn_parse-file', 'desc', {})
    tool._mcp_server = 'mat_sn'
    tool._remote_tool_name = 'parse-file'
    session = SimpleNamespace(
        get_workspace_path=lambda: str(tmp_path),
        config=SimpleNamespace(workspace_path=str(tmp_path)),
    )
    args, remote = tool._rewrite_remote_tool_args(
        session,
        {
            'file_path': str(pdf),
            'sync': True,
            'textual': True,
            'table': True,
        },
    )
    assert remote == 'parse-url'
    assert 'file_path' not in args
    assert args['url'] == 'https://example.com/uploaded/proof.pdf'
    assert args['sync'] is True
