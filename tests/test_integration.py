"""
Integration test: runs the full agent loop with a mock LLM and mock browser.
No real API calls, no real Playwright instance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from asterisk.agent import Agent
from asterisk.llm.adapter import LLMAdapter, LLMResponse


def _response(action_type: str, step: int, extra_action: dict | None = None) -> LLMResponse:
    """Build a minimal valid LLMResponse for a given action type."""
    action: dict = {"type": action_type, "description": f"step {step} action"}
    if extra_action:
        action.update(extra_action)
    parsed = {
        "action": action,
        "wiki_update": {
            "file": f"steps/test-task/step-{step:03d}.md",
            "content": "",
            "related": [],
        },
        "status_update": {"current_step": step, "progress": f"{step}/3"},
    }
    return LLMResponse(
        content=json.dumps(parsed),
        parsed=parsed,
        input_tokens=500,
        output_tokens=100,
        cache_read_tokens=200 if step > 1 else 0,
        cache_write_tokens=50,
    )


class MockLLMAdapter(LLMAdapter):
    """Cycles through canned responses then always returns done."""

    def __init__(self, responses: list[LLMResponse]):
        self._queue = list(responses)
        self._done_response = _response("done", 99)
        self.calls: list[dict] = []

    async def complete(
        self,
        wiki_context: dict[str, str],
        image_bytes: Optional[bytes] = None,
    ) -> LLMResponse:
        self.calls.append({"wiki_context": wiki_context, "has_image": image_bytes is not None})
        if self._queue:
            return self._queue.pop(0)
        return self._done_response


def _make_browser_mock() -> MagicMock:
    """
    Build an async-context-manager mock that looks enough like BrowserController
    for the agent loop to run.
    """
    page = MagicMock()
    page.url = "https://example.com"

    browser = AsyncMock()
    browser.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    browser.navigate = AsyncMock()
    browser.click = AsyncMock()
    browser.type = AsyncMock()
    browser.scroll = AsyncMock()
    browser.wait = AsyncMock()
    browser.current_url = "https://example.com"

    # Support `async with BrowserController(...) as browser:`
    ctx_mgr = AsyncMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=browser)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    return ctx_mgr, browser


@pytest.fixture()
def agent_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "wiki"
    vault.mkdir()
    (vault / "status.md").write_text("# Status\n- **task**: test\n- **step**: 0\n")
    (vault / "index.md").write_text(
        "# Index\n\n| Slug | Description | Status |\n|------|-------------|--------|\n| _(none yet)_ | | |\n"
    )
    return vault


@pytest.mark.asyncio
async def test_agent_runs_three_steps_and_stops_on_done(agent_vault: Path):
    mock_adapter = MockLLMAdapter([
        _response("navigate", 1, {"url": "https://example.com"}),
        _response("click", 2, {"selector": "#btn"}),
        # third call returns done (from queue pop → _done_response)
    ])

    ctx_mgr, browser = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=10)
        counter = await agent.run("test task")

    assert len(counter.steps) == 3
    assert counter.steps[0].step == 1
    assert counter.steps[2].step == 3


@pytest.mark.asyncio
async def test_agent_writes_step_files(agent_vault: Path):
    mock_adapter = MockLLMAdapter([])  # immediately returns done

    ctx_mgr, browser = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=5)
        await agent.run("test task")

    step_dir = agent_vault / "steps"
    assert step_dir.exists()
    step_files = list(step_dir.rglob("step-*.md"))
    assert len(step_files) == 1  # done on step 1


@pytest.mark.asyncio
async def test_agent_updates_status_md(agent_vault: Path):
    mock_adapter = MockLLMAdapter([])

    ctx_mgr, _ = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=5)
        await agent.run("buy oat milk")

    status_content = (agent_vault / "status.md").read_text()
    assert "buy oat milk" in status_content
    assert "step**: 1" in status_content


@pytest.mark.asyncio
async def test_agent_persists_observation(agent_vault: Path):
    """Observations in the LLM response should be written to observations/."""
    obs_response = LLMResponse(
        content="",
        parsed={
            "action": {"type": "done", "description": "done"},
            "wiki_update": {"file": "steps/t/step-001.md", "content": "", "related": []},
            "status_update": {"current_step": 1, "progress": "1/1"},
            "observation": {
                "slug": "site-selectors",
                "title": "Site selectors",
                "content": "Login uses id=email.",
            },
        },
        input_tokens=100,
        output_tokens=50,
    )
    mock_adapter = MockLLMAdapter([obs_response])

    ctx_mgr, _ = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=5)
        await agent.run("test obs task")

    obs_file = agent_vault / "observations/site-selectors.md"
    assert obs_file.exists()
    assert "id=email" in obs_file.read_text()


@pytest.mark.asyncio
async def test_agent_respects_max_steps(agent_vault: Path):
    """Agent should stop after max_steps even without a done action."""
    never_done = MockLLMAdapter([_response("click", i, {"selector": "#x"}) for i in range(1, 20)])

    ctx_mgr, _ = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=never_done),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=3)
        counter = await agent.run("infinite task")

    assert len(counter.steps) == 3


@pytest.mark.asyncio
async def test_agent_wiki_context_passed_to_llm(agent_vault: Path):
    """The LLM should receive wiki context including status.md on every call."""
    mock_adapter = MockLLMAdapter([])

    ctx_mgr, _ = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=5)
        await agent.run("check context")

    assert len(mock_adapter.calls) >= 1
    first_call_ctx = mock_adapter.calls[0]["wiki_context"]
    assert "status.md" in first_call_ctx


@pytest.mark.asyncio
async def test_agent_navigate_action_calls_browser(agent_vault: Path):
    mock_adapter = MockLLMAdapter([
        _response("navigate", 1, {"url": "https://example.com"}),
    ])

    ctx_mgr, browser = _make_browser_mock()

    with (
        patch("asterisk.agent.BrowserController", return_value=ctx_mgr),
        patch("asterisk.agent.get_adapter", return_value=mock_adapter),
    ):
        agent = Agent(vault_path=str(agent_vault), max_steps=5)
        await agent.run("navigate test")

    browser.navigate.assert_called_once_with("https://example.com")
