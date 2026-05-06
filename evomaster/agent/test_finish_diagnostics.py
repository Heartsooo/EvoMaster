from evomaster.agent.finish_diagnostics import build_finish_detail, is_valid_natural_finish
from evomaster.utils.llm import LLMResponse


def test_reasoning_only_is_invalid_natural_finish():
    response = LLMResponse(content='', reasoning_content='thinking', finish_reason='stop')
    assert not is_valid_natural_finish(response)
    detail = build_finish_detail(response)
    assert detail['kind'] == 'reasoning_only'


def test_visible_stop_without_tool_calls_is_valid_natural_finish():
    response = LLMResponse(content='done', reasoning_content=None, finish_reason='stop')
    assert is_valid_natural_finish(response)
