"""Playwright browser controller — manages a single persistent browser context."""
from __future__ import annotations

from typing import Literal, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BrowserController:
    """Async context manager wrapping a Playwright browser session."""

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> None:
        self._headless = headless
        self._slow_mo = slow_mo
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "BrowserController":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            slow_mo=self._slow_mo,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": self._viewport_width, "height": self._viewport_height},
        )
        self._page = await self._context.new_page()
        # Ensure there is a rendered page before the first screenshot
        await self._page.goto("about:blank", wait_until="domcontentloaded")
        return self

    async def __aexit__(self, *_) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    async def navigate(self, url: str, wait_until: str = "networkidle") -> None:
        await self._page.goto(url, wait_until=wait_until)

    async def screenshot(self) -> bytes:
        """Return a PNG screenshot of the current page as bytes."""
        return await self._page.screenshot(type="png", full_page=False)

    async def click(self, selector: str) -> None:
        """Click an element with three fallback levels.

        1. Playwright wait_for_selector + click (standard path)
        2. document.querySelector JS click (handles hidden/overlay elements)
        3. Text-content search across buttons/links (handles :contains() selectors
           that the LLM sometimes produces, which are not valid CSS)
        """
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=10_000)
            await self._page.click(selector)
            return
        except Exception:
            pass

        # Fallback 2: querySelector JS click
        try:
            clicked = await self._page.evaluate(
                "(sel) => { const el = document.querySelector(sel); if (el) { el.click(); return true; } return false; }",
                selector,
            )
            if clicked:
                return
        except Exception:
            pass

        # Fallback 3: text-content search — handles :contains('...') patterns the LLM produces
        import re as _re
        text_match = _re.search(r":contains\(['\"](.+?)['\"]\)", selector, _re.IGNORECASE)
        search_text = text_match.group(1) if text_match else selector
        clicked = await self._page.evaluate(
            """(text) => {
                const tags = ['button', 'a', '[role="button"]', 'input[type="submit"]'];
                for (const tag of tags) {
                    const els = Array.from(document.querySelectorAll(tag));
                    const el = els.find(e => e.innerText.trim().toLowerCase().includes(text.toLowerCase()));
                    if (el) { el.click(); return true; }
                }
                return false;
            }""",
            search_text,
        )
        if not clicked:
            raise RuntimeError(f"Could not find element matching {selector!r}")

    async def type(self, selector: str, text: str, delay: int = 50) -> None:
        """Clear a field and type text into it."""
        await self._page.wait_for_selector(selector, state="visible", timeout=10_000)
        await self._page.fill(selector, "")
        await self._page.type(selector, text, delay=delay)

    async def scroll(
        self,
        direction: Literal["down", "up"] = "down",
        pixels: int = 300,
    ) -> None:
        delta = pixels if direction == "down" else -pixels
        await self._page.evaluate(f"window.scrollBy(0, {delta})")

    async def wait(self, milliseconds: int = 1000) -> None:
        await self._page.wait_for_timeout(milliseconds)

    async def get_page_title(self) -> str:
        return await self._page.title()
