"""Google Gemini adapter."""
from __future__ import annotations

import base64
import os
from typing import Optional

import google.generativeai as genai

from .adapter import LLMAdapter, LLMResponse, LLMParseError, SYSTEM_PROMPT


class GeminiAdapter(LLMAdapter):
    def __init__(self) -> None:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )

    async def complete(
        self,
        wiki_context: dict[str, str],
        image_bytes: Optional[bytes] = None,
    ) -> LLMResponse:
        parts = []

        if image_bytes:
            parts.append({"mime_type": "image/png", "data": image_bytes})

        wiki_text = "\n\n---\n\n".join(
            f"# {fname}\n\n{content}" for fname, content in wiki_context.items()
        )
        parts.append(f"<wiki_context>\n{wiki_text}\n</wiki_context>")

        response = await self._model.generate_content_async(parts)

        text = response.text or ""
        if not text:
            raise LLMParseError("Gemini returned an empty response.")

        parsed = self._parse_response(text)

        usage = response.usage_metadata
        return LLMResponse(
            content=text,
            parsed=parsed,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )
