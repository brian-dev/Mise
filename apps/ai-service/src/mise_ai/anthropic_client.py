"""Thin wrapper over the Anthropic SDK for forced-tool structured output.

Centralizes the call shape used by every generation operation:
  * forced tool_choice so the model must return structured data (no prose),
  * prompt caching on the tool schema + system prompt (the stable prefix),
  * thinking disabled (deterministic structured extraction; keeps the
    benchmark's token accounting clean),
  * streaming (plans can exceed the ~16k non-streaming ceiling),
  * token-usage capture for the cost benchmark (AI_LAYER §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import anthropic

from .config import settings


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass
class ToolCallResult:
    tool_input: dict[str, Any]
    usage: Usage
    raw_content: list[Any]  # full assistant content, for a repair follow-up turn


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY from the env; settings value overrides if set.
        if settings.anthropic_api_key:
            _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        else:
            _client = anthropic.Anthropic()
    return _client


def call_tool(
    *,
    model: str,
    system_prompt: str,
    tool: dict[str, Any],
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
) -> ToolCallResult:
    """Force `tool` and return its parsed input + token usage.

    `tool` and `system_prompt` are cached (ephemeral). `messages` is the volatile
    suffix (the context block, plus any repair turns) and is never cached.
    """
    client = _get_client()
    tool_name = tool["name"]

    # cache_control on the tool schema caches tools+system together (render order
    # is tools -> system -> messages, AI_LAYER §3 / prompt-caching).
    cached_tool = {**tool, "cache_control": {"type": "ephemeral"}}
    cached_system = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    # The SDK expects TypedDict params; our payloads are plain dicts built at
    # runtime (incl. tool_result repair turns). cast at this single boundary.
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens or settings.max_output_tokens,
        thinking={"type": "disabled"},
        system=cast(Any, cached_system),
        tools=cast(Any, [cached_tool]),
        tool_choice={"type": "tool", "name": tool_name},
        messages=cast(Any, messages),
    ) as stream:
        message = stream.get_final_message()

    tool_input: dict[str, Any] | None = None
    for block in message.content:
        if block.type == "tool_use" and block.name == tool_name:
            tool_input = cast("dict[str, Any]", block.input)
            break
    if tool_input is None:
        raise RuntimeError(
            f"Model did not return the forced tool {tool_name!r} "
            f"(stop_reason={message.stop_reason})."
        )

    u = message.usage
    usage = Usage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )
    return ToolCallResult(tool_input=tool_input, usage=usage, raw_content=message.content)
