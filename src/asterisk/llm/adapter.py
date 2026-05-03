"""Base adapter class and factory for LLM providers."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


SYSTEM_PROMPT = """\
You are an agentic computer-use controller. On each turn you receive:
1. A screenshot of the current state (browser viewport or full desktop)
2. The current wiki context (status, current step, relevant observations)

You must respond with a single JSON object matching this exact schema:
{
  "action": {
    "type": "<action type — see list below>",
    "selector": "#css-selector (for click/type browser actions)",
    "value": "text to type (for type or desktop_type)",
    "url": "url (for navigate or open)",
    "direction": "down | up (for scroll)",
    "pixels": 300,
    "x": 0,
    "y": 0,
    "command": "shell command string (for bash)",
    "path": "file path (for file_read / file_write / open app)",
    "content": "file content (for file_write)",
    "description": "human-readable description of this action"
  },
  "wiki_update": {
    "file": "steps/<task-slug>/step-NNN.md",
    "content": "<full step file content>",
    "related": ["[[wikilinks to prior steps or observations]]"]
  },
  "status_update": {
    "current_step": <int>,
    "progress": "<N/M steps estimated>"
  },
  "observation": {
    "slug": "short-kebab-case-id",
    "title": "Human readable title",
    "content": "Reusable fact about this site that will help on future tasks."
  }
}

Available action types:
- Browser actions (Playwright-controlled browser):
    click       — click element by CSS selector
    type        — type text into element by CSS selector
    navigate    — navigate to a URL
    scroll      — scroll the page (direction + pixels)
    wait        — wait N milliseconds
- Desktop / computer-use actions (full OS desktop):
    desktop_screenshot — take a full desktop screenshot (use when browser is stuck)
    desktop_click      — click at pixel coordinates {x, y} on the real desktop
    desktop_type       — type text at the current cursor position on the desktop
- Shell:
    bash        — run a shell command, observe stdout/stderr on the next step
- File system:
    file_read   — read a file from disk (path)
    file_write  — write content to a file on disk (path + content)
- App launch:
    open        — open a URL in the real browser or launch a desktop app by path
- Completion:
    done        — task is complete; put the full answer in "description"

Choose browser actions when you have navigated to a URL in the controlled browser.
Choose desktop actions when you need to interact with the real desktop or any native app,
or when the browser is stuck (CAPTCHA, anti-bot wall, complex popup).
Choose bash when you need to run system commands, scripts, or check system state.

The "observation" field is OPTIONAL. Only include it when you notice something
reusable about this website that would help on future tasks.
Do NOT include it on every step; only when genuinely useful.

The step file content MUST contain a JSON block with this schema:
{
  "step": <int>,
  "task": "<task name>",
  "action_taken": "<description of what was just done>",
  "element": "<selector or null>",
  "url": "<current url>",
  "outcome": "success | failure | pending",
  "next_hint": "<what to do next>",
  "related": ["[[wikilinks]]"],
  "timestamp": "<ISO 8601>"
}

RULES:
- If the screenshot shows a blank page (about:blank) or a page unrelated to the task,
  your FIRST action MUST be "navigate" to the correct URL. Never call "done" from a blank page.
- Only call "done" once you have actually observed the information requested by the task on screen.
  When you call "done", put the full answer to the task in the "description" field.
- If you cannot find what is requested after navigating and looking around, call "done" with
  a clear explanation of what you found and why the task could not be completed.
- Never invent information. Only report what you can see in the screenshot.
Never include anything outside the JSON object in your response.
"""


@dataclass
class LLMResponse:
    content: str
    parsed: dict
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMParseError(Exception):
    """Raised when the LLM response cannot be parsed as valid action JSON."""


class LLMAdapter(ABC):
    """Base class for all LLM provider adapters."""

    @abstractmethod
    async def complete(
        self,
        wiki_context: dict[str, str],
        image_bytes: Optional[bytes] = None,
    ) -> LLMResponse:
        """
        Send a single agent step to the LLM.

        Args:
            wiki_context: Mapping of filename → content for all loaded wiki pages.
            image_bytes: PNG screenshot bytes. None for text-only calls.

        Returns:
            LLMResponse with parsed action, wiki_update, and status_update.

        Raises:
            LLMParseError: If the model response is not valid JSON or missing keys.
        """

    def _build_user_message(
        self, wiki_context: dict[str, str], image_bytes: Optional[bytes]
    ) -> list[dict]:
        """Assemble the user message content blocks."""
        blocks: list[dict] = []

        if image_bytes:
            import base64
            b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            })

        wiki_text = "\n\n---\n\n".join(
            f"# {fname}\n\n{content}" for fname, content in wiki_context.items()
        )
        blocks.append({"type": "text", "text": f"<wiki_context>\n{wiki_text}\n</wiki_context>"})

        return blocks

    def _parse_response(self, text: str) -> dict:
        """Extract and validate the JSON action from the model's text output."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMParseError(f"Response is not valid JSON: {e}\n---\n{text[:500]}") from e

        for key in ("action", "wiki_update", "status_update"):
            if key not in data:
                raise LLMParseError(f"Response missing required key '{key}': {data}")

        return data


def get_adapter() -> LLMAdapter:
    """Return the configured LLM adapter based on LLM_PROVIDER env var."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        from .anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter()
    elif provider == "openai":
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter()
    elif provider == "gemini":
        from .gemini_adapter import GeminiAdapter
        return GeminiAdapter()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use anthropic, openai, or gemini.")
