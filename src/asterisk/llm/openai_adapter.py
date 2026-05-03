"""OpenAI adapter."""
from __future__ import annotations

import base64
import os
from typing import Optional

from openai import AsyncOpenAI

from .adapter import LLMAdapter, LLMResponse, LLMParseError, SYSTEM_PROMPT


class OpenAIAdapter(LLMAdapter):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    def _build_user_message(
        self, wiki_context: dict[str, str], image_bytes: Optional[bytes]
    ) -> list[dict]:
        blocks: list[dict] = []

        if image_bytes:
            b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
            })

        wiki_text = "\n\n---\n\n".join(
            f"# {fname}\n\n{content}" for fname, content in wiki_context.items()
        )
        blocks.append({"type": "text", "text": f"<wiki_context>\n{wiki_text}\n</wiki_context>"})

        return blocks

    async def complete(
        self,
        wiki_context: dict[str, str],
        image_bytes: Optional[bytes] = None,
    ) -> LLMResponse:
        user_content = self._build_user_message(wiki_context, image_bytes)

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        text = response.choices[0].message.content or ""
        if not text:
            raise LLMParseError("OpenAI returned an empty response.")

        parsed = self._parse_response(text)
        usage = response.usage

        return LLMResponse(
            content=text,
            parsed=parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
