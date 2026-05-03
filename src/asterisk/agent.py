"""Core agent loop — look → load wiki → ask → parse → act → write wiki → repeat."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .browser import BrowserController
from .llm.adapter import get_adapter, LLMParseError
from .token_counter import TokenCounter
from .tools import BashTool, ComputerTool, FileTool
from .wiki.observation_extractor import ObservationExtractor
from .wiki.reader import WikiReader
from .wiki.writer import WikiWriter, WikiWriteError

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert task description to a filesystem-safe slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60].strip("-") or "task"


class AgentError(Exception):
    """Raised when the agent cannot recover from an error."""


class Agent:
    """
    Runs the anotherAsterisk agentic loop for a single task.

    Each iteration:
      1. Take a screenshot
      2. Load wiki context (status.md + current step file + linked observations)
      3. Call the LLM with screenshot + context
      4. Parse the action + wiki_update + status_update from the response
      5. Execute the action (browser, desktop, bash, or file)
      6. Write the new step file to the wiki
      7. Update status.md

    mode: "browser" — Playwright only
          "desktop" — desktop screenshot + desktop click/type (ComputerTool)
          "hybrid"  — browser for web tasks, falls back to desktop on CAPTCHA/stuck
    """

    def __init__(
        self,
        vault_path: str = "./wiki",
        max_steps: int = 50,
        headless: bool = True,
        slow_mo: int = 0,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        mode: str = "browser",
    ) -> None:
        self._vault_path = vault_path
        self._max_steps = max_steps
        self._headless = headless
        self._slow_mo = slow_mo
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._mode = mode

        self._bash_tool = BashTool()
        self._computer_tool = ComputerTool()
        self._file_tool = FileTool()
        self._last_tool_result: dict | None = None  # fed back to LLM on next step

    async def run(self, task: str, start_url: Optional[str] = None) -> TokenCounter:
        """
        Execute the agent loop for *task*, optionally navigating to *start_url* first.
        Returns a TokenCounter with per-step usage for cost analysis.
        """
        task_slug = _slugify(task)
        reader = WikiReader(self._vault_path)
        writer = WikiWriter(self._vault_path)
        extractor = ObservationExtractor(self._vault_path)
        adapter = get_adapter()
        counter = TokenCounter()

        writer.update_index(task_slug, task)
        # Reset status before step 1 so the LLM sees the current task, not a stale one
        writer.update_status(
            task=task,
            step=0,
            url=start_url or "",
            progress=f"0/{self._max_steps}",
            last_action="Task started",
            next_hint="Begin",
        )

        async with BrowserController(
            headless=self._headless,
            slow_mo=self._slow_mo,
            viewport_width=self._viewport_width,
            viewport_height=self._viewport_height,
        ) as browser:
            if start_url:
                logger.info("Navigating to start URL: %s", start_url)
                await browser.navigate(start_url)

            for step_number in range(1, self._max_steps + 1):
                logger.info("─── Step %03d / %03d ───", step_number, self._max_steps)

                # 1. Screenshot — browser viewport or full desktop depending on mode
                if self._mode == "desktop":
                    screenshot = await self._computer_tool.screenshot()
                else:
                    screenshot = await browser.screenshot()

                # 2. Load wiki context
                context = reader.load_context(task_slug, step_number - 1)
                # Inject bash/file result from the previous step so the LLM can see it
                if self._last_tool_result is not None:
                    import json as _json
                    context["tool_result.md"] = (
                        "# Last Tool Result\n\n"
                        f"```json\n{_json.dumps(self._last_tool_result, indent=2)}\n```\n"
                    )
                    self._last_tool_result = None

                # 3. Ask the LLM (retry up to 2 times on parse errors)
                response = None
                for _attempt in range(3):
                    try:
                        response = await adapter.complete(
                            wiki_context=context,
                            image_bytes=screenshot,
                        )
                        break
                    except LLMParseError as e:
                        logger.warning(
                            "LLM parse error on step %d (attempt %d/3): %s",
                            step_number, _attempt + 1, e,
                        )
                        if _attempt == 2:
                            writer._vault.joinpath("blockers.md").write_text(
                                _blockers_content(str(e)), encoding="utf-8"
                            )
                            raise AgentError(f"LLM parse error after 3 attempts: {e}") from e

                # 4. Record tokens
                counter.record(
                    step=step_number,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cache_read_tokens=response.cache_read_tokens,
                    cache_write_tokens=response.cache_write_tokens,
                )

                action = response.parsed.get("action", {})
                wiki_update = response.parsed.get("wiki_update", {})
                status_update = response.parsed.get("status_update", {})

                # 5a. Extract and persist any observation the LLM flagged
                obs_slug = extractor.extract_and_save(response.parsed)
                if obs_slug:
                    related = wiki_update.get("related", [])
                    obs_link = f"[[observations/{obs_slug}]]"
                    if obs_link not in related:
                        wiki_update.setdefault("related", []).append(obs_link)

                # 5b. Write step file to wiki
                await self._write_step(
                    writer=writer,
                    task_slug=task_slug,
                    step_number=step_number,
                    action=action,
                    wiki_update=wiki_update,
                    url=browser.current_url,
                    screenshot=screenshot,
                    task=task,
                )

                # 6. Update status.md
                writer.update_status(
                    task=task,
                    step=step_number,
                    url=browser.current_url,
                    progress=status_update.get("progress", f"{step_number}/{self._max_steps}"),
                    last_action=action.get("description", ""),
                    next_hint=action.get("description", ""),
                )

                # 7. Check for completion
                if action.get("type") == "done":
                    logger.info("Task complete at step %d.", step_number)
                    logger.info(counter.summary())
                    final_answer = action.get("description", "").strip()
                    if final_answer:
                        print(f"\n=== Result ===\n{final_answer}\n")
                    return counter

                # 8. Execute action — result is fed back to LLM on next step
                try:
                    action_result = await self._execute_action(browser, action)
                    if action_result and action_result.get("status") != "ok":
                        self._last_tool_result = action_result
                except Exception as e:
                    logger.warning("Action execution error on step %d: %s", step_number, e)
                    self._last_tool_result = {
                        "action_type": action.get("type", "unknown"),
                        "status": "error",
                        "error": str(e),
                    }

        logger.warning("Reached max steps (%d) without completing task.", self._max_steps)
        logger.info(counter.summary())
        return counter

    async def _execute_action(self, browser: BrowserController, action: dict) -> dict:
        """Dispatch a parsed action dict to the appropriate tool.

        Always returns {"status": "ok"|"skipped"|"error", ...} so callers can
        feed failures back to the LLM via _last_tool_result.
        """
        action_type = action.get("type", "")

        def _ok(**kw) -> dict:
            return {"action_type": action_type, "status": "ok", **kw}

        def _skip(reason: str) -> dict:
            logger.warning("%s action skipped: %s — full action: %s", action_type, reason, action)
            return {"action_type": action_type, "status": "skipped", "reason": reason,
                    "received_fields": list(action.keys())}

        # --- Browser actions ---
        if action_type == "click":
            selector = action.get("selector", "")
            if not selector:
                return _skip("missing 'selector' field")
            await browser.click(selector)
            return _ok(selector=selector)

        elif action_type == "type":
            selector = action.get("selector", "")
            value = action.get("value", "")
            if not selector:
                return _skip("missing 'selector' field")
            await browser.type(selector, value)
            return _ok(selector=selector)

        elif action_type == "navigate":
            url = action.get("url", "")
            if not url:
                return _skip("missing 'url' field")
            await browser.navigate(url)
            return _ok(url=url)

        elif action_type == "scroll":
            direction = action.get("direction", "down")
            pixels = int(action.get("pixels", 300))
            await browser.scroll(direction=direction, pixels=pixels)
            return _ok()

        elif action_type == "wait":
            ms = int(action.get("milliseconds", 1000))
            await browser.wait(ms)
            return _ok()

        elif action_type == "done":
            return _ok()  # handled in the loop above

        # --- Desktop / computer-use actions ---
        elif action_type == "desktop_screenshot":
            return _ok()  # screenshot already taken at top of loop

        elif action_type == "desktop_click":
            x = int(action.get("x", 0))
            y = int(action.get("y", 0))
            await self._computer_tool.click(x, y)
            return _ok(x=x, y=y)

        elif action_type == "desktop_type":
            text = action.get("value", action.get("text", ""))
            await self._computer_tool.type_text(text)
            return _ok(text=text)

        elif action_type == "desktop_hotkey":
            # Accept many field name variants the LLM might produce
            keys = (
                action.get("keys") or action.get("key") or action.get("shortcut")
                or action.get("hotkey") or action.get("combination")
                or action.get("key_combination") or action.get("value") or ""
            )
            if not keys:
                return _skip(
                    "missing keys field — use 'keys' field with value like 'ctrl+k' or 'enter'. "
                    f"Fields received: {list(action.keys())}"
                )
            await self._computer_tool.hotkey(keys)
            return _ok(keys=keys)

        # --- Shell ---
        elif action_type == "bash":
            command = action.get("command", "")
            if not command:
                return _skip("missing 'command' field")
            result = await self._bash_tool.run(command)
            logger.info("bash result: %s", result)
            r = {"action": "bash", "command": command, **result}
            self._last_tool_result = r
            return _ok(**result)

        # --- File system ---
        elif action_type == "file_read":
            path = action.get("path", "")
            if not path:
                return _skip("missing 'path' field")
            result = await self._file_tool.read(path)
            logger.info("file_read result: %s", result)
            self._last_tool_result = {"action": "file_read", "path": path, **result}
            return _ok(**result)

        elif action_type == "file_write":
            path = action.get("path", "")
            content = action.get("content", "")
            if not path:
                return _skip("missing 'path' field")
            result = await self._file_tool.write(path, content)
            logger.info("file_write result: %s", result)
            self._last_tool_result = {"action": "file_write", "path": path, **result}
            return _ok(**result)

        # --- Open URL in real browser / launch app ---
        elif action_type == "open":
            target = action.get("url", action.get("path", ""))
            if not target:
                return _skip("missing 'url' or 'path' field")

            # Normalise common app names to URL protocol schemes
            _PROTO = {"discord": "discord://", "spotify": "spotify://",
                      "slack": "slack://", "zoom": "zoommtg://"}
            target = _PROTO.get(target.lower().strip(), target)

            import platform as _plat
            from .tools.computer_tool import _is_wsl
            _sys = _plat.system()
            if _sys == "Darwin":
                subprocess.Popen(["open", target])
            elif _sys == "Linux" and _is_wsl():
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{target}'"],
                    capture_output=True, text=True,
                )
                if proc.returncode != 0:
                    return {"action_type": action_type, "status": "error",
                            "error": proc.stderr.strip(), "target": target,
                            "hint": "Use a URL scheme like 'discord://' not just 'discord'"}
            elif _sys == "Linux":
                subprocess.Popen(["xdg-open", target])
            elif _sys == "Windows":
                subprocess.Popen(["start", target], shell=True)
            return _ok(target=target)

        else:
            return _skip(f"unknown action type '{action_type}'")

    async def _write_step(
        self,
        writer: WikiWriter,
        task_slug: str,
        step_number: int,
        action: dict,
        wiki_update: dict,
        url: str,
        screenshot: bytes,
        task: str,
    ) -> None:
        """Build and write the step file, falling back gracefully on validation errors."""
        related = wiki_update.get("related", [])
        step_data = {
            "step": step_number,
            "task": task,
            "action_taken": action.get("description", f"step {step_number}"),
            "element": action.get("selector"),
            "url": url,
            "outcome": "success",
            "next_hint": action.get("description", ""),
            "related": related,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        step_content = wiki_update.get("content", "")
        if step_content:
            _extract_step_fields(step_data, step_content)

        try:
            writer.write_step(
                task_slug=task_slug,
                step_number=step_number,
                data=step_data,
                screenshot_bytes=screenshot,
            )
        except WikiWriteError as e:
            logger.warning("Wiki write error on step %d: %s", step_number, e)


def _extract_step_fields(step_data: dict, content: str) -> None:
    """
    Try to pull outcome/next_hint out of freeform step content.
    Only updates fields that are present and non-empty in the content.
    """
    import json, re as _re
    if not isinstance(content, str):
        return
    match = _re.search(r"```json\s*(\{.*?\})\s*```", content, _re.DOTALL)
    if not match:
        return
    try:
        parsed = json.loads(match.group(1))
        for key in ("outcome", "next_hint", "related"):
            if key in parsed and parsed[key]:
                step_data[key] = parsed[key]
    except (json.JSONDecodeError, KeyError):
        pass


def _blockers_content(error_msg: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return f"""# Blockers

## Active Blockers

### LLM Parse Error — {now}

```
{error_msg}
```

## Resolved Blockers

_(none)_
"""
