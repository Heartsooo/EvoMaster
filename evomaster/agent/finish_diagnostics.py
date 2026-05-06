from __future__ import annotations

from typing import Any

from evomaster.utils.llm import LLMResponse


def _visible_text(content: Any) -> str:
    if content is None:
        return ''
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def has_visible_content(response: LLMResponse | None) -> bool:
    if response is None:
        return False
    return bool(_visible_text(response.content))


def is_valid_natural_finish(response: LLMResponse | None) -> bool:
    if response is None:
        return False
    return not response.tool_calls and response.finish_reason == 'stop' and has_visible_content(response)


def build_finish_detail(response: LLMResponse | None) -> dict[str, Any]:
    if response is None:
        return {
            'kind': 'missing_llm_response',
            'message': 'LLM returned no response object.',
        }

    finish_reason = response.finish_reason
    has_visible = has_visible_content(response)
    has_reasoning = bool(getattr(response, 'reasoning_content', None))
    tool_calls = response.tool_calls or []
    base = {
        'provider_finish_reason': finish_reason,
        'content_chars': len(response.content or ''),
        'reasoning_chars': len(getattr(response, 'reasoning_content', None) or ''),
        'has_visible_content': has_visible,
        'has_reasoning': has_reasoning,
        'has_tool_calls': bool(tool_calls),
        'tool_call_count': len(tool_calls),
    }

    if finish_reason == 'length':
        return {
            'kind': 'output_length_exceeded',
            'message': 'Model output was truncated by output-token limit.',
            **base,
        }
    if finish_reason == 'stop' and not has_visible and has_reasoning:
        return {
            'kind': 'reasoning_only',
            'message': 'Model returned reasoning content without a visible final answer.',
            **base,
        }
    if finish_reason == 'stop' and not has_visible:
        return {
            'kind': 'empty_response',
            'message': 'Model stopped without a visible final answer.',
            **base,
        }
    if finish_reason != 'stop' and not tool_calls:
        return {
            'kind': 'non_stop_finish',
            'message': 'Model returned a non-stop finish without tool calls.',
            **base,
        }
    return {
        'kind': 'ok',
        'message': 'Natural finish is valid.',
        **base,
    }
