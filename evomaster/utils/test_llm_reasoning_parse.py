from types import SimpleNamespace

from evomaster.utils.llm import OpenAILLM
from evomaster.utils.llm import LLMConfig


def test_openai_parser_extracts_reasoning_content():
    llm = object.__new__(OpenAILLM)
    llm.config = LLMConfig(provider='openai', model='test', api_key='x')
    llm.logger = None
    llm.output_config = {}
    llm.show_in_console = False
    llm.log_to_file = False

    message = SimpleNamespace(content='final answer', reasoning_content='native thinking', tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason='stop')
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    response = SimpleNamespace(choices=[choice], usage=usage, model='test-model', id='resp_1')

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return response

    llm.client = FakeClient()
    out = llm._call(messages=[{'role': 'user', 'content': 'hi'}])
    assert out.reasoning_content == 'native thinking'
    assert out.content == 'final answer'
