from evomaster.utils.llm import LLMResponse
from playground.materials_playground.web.session_runner import _dict_step_to_events


def test_llm_response_preserves_reasoning_content():
    response = LLMResponse(content="answer", reasoning_content="hidden thinking", finish_reason="stop")
    msg = response.to_assistant_message()
    assert msg.reasoning_content == "hidden thinking"


def test_saved_trajectory_step_emits_reasoning_event():
    step = {
        "step_id": 1,
        "assistant_message": {
            "content": "final answer",
            "reasoning_content": "native reasoning here",
            "tool_calls": [],
        },
        "tool_responses": [],
    }
    events = _dict_step_to_events(step, 1)
    assert any(ev.get("type") == "assistant" and ev.get("is_reasoning") for ev in events)
    assert any(ev.get("content") == "native reasoning here" for ev in events)
