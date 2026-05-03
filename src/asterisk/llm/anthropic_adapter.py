"""Anthropic Claude adapter with prompt caching on the system prompt."""
from __future__ import annotations

import os
from typing import Optional

import anthropic

from .adapter import LLMAdapter, LLMResponse, LLMParseError, SYSTEM_PROMPT


class AnthropicAdapter(LLMAdapter):
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    async def complete(
        self,
        wiki_context: dict[str, str],
        image_bytes: Optional[bytes] = None,
    ) -> LLMResponse:
        user_content = self._build_user_message(wiki_context, image_bytes)

        # Cache the system prompt — it is identical across every step in a session.
        # On the first call this pays the 1.25× write premium; subsequent calls
        # read it at ~0.1× cost, which is the core cost-saving mechanism.
        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )

        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        if not text:
            raise LLMParseError("Anthropic returned an empty text response.")

        parsed = self._parse_response(text)
        usage = response.usage

        return LLMResponse(
            content=text,
            parsed=parsed,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
