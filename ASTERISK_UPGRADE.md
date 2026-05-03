# anotherAsterisk — Upgrade System Prompt for Claude Code

Paste this entire file as your first message to Claude Code inside the anotherAsterisk project.

---

## CONTEXT: WHO YOU ARE AND WHAT EXISTS

You are working on **anotherAsterisk** — an agentic automation framework that keeps LLM
context cost at O(N) via a wiki-regulated state store (Obsidian vault). The project lives
at `https://github.com/4kaws/anotherAsterisk`. The core loop is:

```
screenshot + wiki/status.md + current step file → LLM → action + wiki_update
```

Two problems need to be fixed. Read both before touching any code. Fix them in order.

Before doing anything, update `PROJECT_CHECKLIST.md` with the two problem sections below,
and write a brief entry to `sessions/session-<today-date>.md` so we have a log.

---

## PROBLEM 1 — BROWSER GETS STUCK ON COOKIE/POPUP WALLS

### Root cause

Playwright launches a clean, cookieless Chromium instance every run. Real websites detect
this and immediately throw cookie consent popups, GDPR walls, "allow all" banners, and
anti-bot CAPTCHAs. Because the agent's action loop needs to ask the LLM what to do next
before clicking anything, it stalls on step 1 of every real-world task.

### How OpenClaw avoids this

OpenClaw does **not** use an isolated headless browser for most tasks. It uses:

1. **Computer use on the user's actual desktop** — it takes a screenshot of the real
   running OS, which has a real browser (Chrome/Safari/Firefox) already logged in, with
   cookies, sessions, and extensions intact. Cookie banners are already dismissed because
   the user's real browser handles them.

2. **A real browser profile** — when it does launch a browser programmatically, it mounts
   the user's existing Chrome profile directory so all cookies, localStorage, and
   saved passwords carry over.

3. **Bash tool for pre-navigation** — it can run `open https://example.com` on macOS or
   `xdg-open` on Linux to open URLs in the user's default browser, then screenshot the
   desktop to see the result.

### What to implement in anotherAsterisk

Do all three of the following inside `src/asterisk/browser.py`:

#### Fix A — Persistent profile directory

```python
# Instead of launching a fresh context every time, mount a persistent profile.
# This preserves cookies, sessions, and extension state across runs.

PROFILE_DIR = Path.home() / ".asterisk" / "browser-profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

context = await browser.new_context(
    user_data_dir=str(PROFILE_DIR),  # persistent cookies & sessions
    viewport={"width": 1280, "height": 800},
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36",
    locale="en-US",
    timezone_id="Europe/Bucharest",
)
```

Use `playwright.chromium.launch_persistent_context(PROFILE_DIR, ...)` instead of
`browser.new_context()` — this is the correct Playwright API for a persistent profile.

#### Fix B — Auto-dismiss common cookie banners BEFORE taking the screenshot

Add a `dismiss_popups()` method that runs after every navigation, before the screenshot
is taken. This runs silently and writes an observation to the wiki if it dismissed
something.

```python
COOKIE_SELECTORS = [
    # Generic accept buttons
    "button[id*='accept']", "button[id*='cookie']", "button[id*='consent']",
    "button[class*='accept']", "button[class*='cookie']",
    # Common text patterns
    "button:has-text('Accept all')", "button:has-text('Accept All')",
    "button:has-text('Allow all')", "button:has-text('Allow All')",
    "button:has-text('Accept cookies')", "button:has-text('I agree')",
    "button:has-text('OK')", "button:has-text('Got it')",
    "button:has-text('Agree')", "button:has-text('Continue')",
    # GDPR specific
    "[aria-label*='Accept']", "[data-testid*='accept']",
    "#onetrust-accept-btn-handler",   # OneTrust (massive CDN)
    ".cc-accept", ".cc-btn",          # CookieConsent lib
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # Cookiebot
    "[data-gdpr-expression='acceptAll']",
]

async def dismiss_popups(self, page) -> bool:
    """Try to click known cookie/consent buttons. Returns True if something was clicked."""
    for selector in COOKIE_SELECTORS:
        try:
            el = await page.wait_for_selector(selector, timeout=800, state="visible")
            if el:
                await el.click()
                await page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False
```

Call `dismiss_popups()` in the main loop AFTER `page.goto()` completes and BEFORE
calling `page.screenshot()`. If it returns True, log an observation to the wiki:
`wiki/observations/cookie-banner-dismissed.md`.

#### Fix C — Handle Playwright dialogs (alert/confirm/prompt)

Add a dialog handler to auto-accept browser-native dialogs (not webpage popups, but
actual `window.alert()` etc.):

```python
page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
```

Add this right after the page is created.

#### Fix D — Stealth mode (optional but recommended)

Install `playwright-stealth` and apply it to avoid bot detection:

```bash
pip install playwright-stealth
```

```python
from playwright_stealth import stealth_async
await stealth_async(page)
```

Apply after page creation, before navigation.

### Checklist for Problem 1

- [ ] Switch `browser.py` to `launch_persistent_context` with `~/.asterisk/browser-profile`
- [ ] Add `COOKIE_SELECTORS` list and `dismiss_popups()` method
- [ ] Call `dismiss_popups()` after every `page.goto()` before screenshot
- [ ] Add dialog auto-accept handler
- [ ] Add `playwright-stealth` to `pyproject.toml` and apply it
- [ ] Write a `wiki/observations/cookie-handling.md` documenting what was added
- [ ] Update `skills/browser/SKILL.md` with the new methods

---

## PROBLEM 2 — LIMITED TO BROWSER ONLY (WANTS OPENCLAW-LEVEL CAPABILITIES)

### What OpenClaw can actually do (that anotherAsterisk cannot)

OpenClaw is fundamentally different from a browser automation tool. It does not launch
a controlled browser — it operates as a **general computer use agent** on the user's
actual machine. Its capability surface is:

| Capability | OpenClaw method | anotherAsterisk current |
|---|---|---|
| Browse web | Desktop screenshot of real browser | Playwright headless |
| Run shell commands | `bash` tool | ❌ None |
| Open desktop apps | `bash` / `process` tool | ❌ None |
| Read/write files | `read` / `write` / `edit` tools | ❌ None |
| Use any GUI app | Computer use (full OS screenshot) | ❌ Browser only |
| Send messages (WhatsApp, Slack…) | Channel integrations | ❌ None |
| Talk/listen (voice) | Voice nodes | ❌ None |

The core architectural difference: OpenClaw screenshots the **entire desktop** (or uses
the OS accessibility APIs), not just a browser viewport. So it can interact with any app
that is visible on screen — Finder, Excel, Spotify, terminal, anything.

### The upgrade path for anotherAsterisk

This is a significant expansion. Implement it as a new **tool layer** alongside the
existing browser tool. The LLM's action JSON will gain new action types.

#### Step 1 — Add a `bash` tool

Create `src/asterisk/tools/bash_tool.py`:

```python
import asyncio
import subprocess
from pathlib import Path

class BashTool:
    """Execute shell commands. Returns stdout, stderr, and exit code."""

    TIMEOUT = 30  # seconds

    async def run(self, command: str, working_dir: str = None) -> dict:
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                ),
                timeout=self.TIMEOUT,
            )
            stdout, stderr = await result.communicate()
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": result.returncode,
                "success": result.returncode == 0,
            }
        except asyncio.TimeoutError:
            return {"error": f"Command timed out after {self.TIMEOUT}s", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}
```

#### Step 2 — Add a computer use screenshot (full desktop)

Create `src/asterisk/tools/computer_tool.py`:

```python
import asyncio
import base64
import platform
from pathlib import Path

class ComputerTool:
    """
    Takes a screenshot of the full desktop (not just a browser).
    This is how OpenClaw sees the world — it can see any app on screen.
    """

    async def screenshot(self) -> bytes:
        system = platform.system()
        if system == "Darwin":  # macOS
            # screencapture is built into macOS
            result = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-t", "png", "/tmp/asterisk_screen.png",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.wait()
            return Path("/tmp/asterisk_screen.png").read_bytes()

        elif system == "Linux":
            # Try scrot, then gnome-screenshot, then import (ImageMagick)
            for cmd in [
                ["scrot", "/tmp/asterisk_screen.png"],
                ["gnome-screenshot", "-f", "/tmp/asterisk_screen.png"],
                ["import", "-window", "root", "/tmp/asterisk_screen.png"],
            ]:
                try:
                    result = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await result.wait()
                    if Path("/tmp/asterisk_screen.png").exists():
                        return Path("/tmp/asterisk_screen.png").read_bytes()
                except FileNotFoundError:
                    continue
            raise RuntimeError("No screenshot tool found. Install scrot: sudo apt install scrot")

        elif system == "Windows":
            # Use PowerShell
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Screen]::PrimaryScreen | ForEach-Object { "
                "$bmp = New-Object System.Drawing.Bitmap($_.Bounds.Width, $_.Bounds.Height); "
                "$g = [System.Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen($_.Bounds.Location, [System.Drawing.Point]::Empty, $_.Bounds.Size); "
                "$bmp.Save('C:/temp/asterisk_screen.png') }"
            )
            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command", ps_cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await result.wait()
            return Path("C:/temp/asterisk_screen.png").read_bytes()

    async def click(self, x: int, y: int):
        """Click at absolute desktop coordinates."""
        system = platform.system()
        if system == "Darwin":
            # Use cliclick (brew install cliclick) or osascript
            script = f'tell application "System Events" to click at {{{x}, {y}}}'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "mousemove", str(x), str(y), "click", "1",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

    async def type_text(self, text: str):
        """Type text at the current cursor position."""
        system = platform.system()
        if system == "Darwin":
            script = f'tell application "System Events" to keystroke "{text}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "type", "--", text,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
```

#### Step 3 — Add file read/write tools

Create `src/asterisk/tools/file_tool.py`:

```python
from pathlib import Path

class FileTool:
    async def read(self, path: str) -> dict:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return {"content": content, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    async def write(self, path: str, content: str, append: bool = False) -> dict:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if append:
                p.open("a").write(content)
            else:
                p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p.resolve())}
        except Exception as e:
            return {"error": str(e), "success": False}
```

#### Step 4 — Expand the action schema

In `agent.py`, expand the action types the LLM can return and the executor handles:

```python
ACTION_TYPES = {
    # Existing browser actions
    "click": executor.browser_click,
    "type": executor.browser_type,
    "navigate": executor.browser_navigate,
    "scroll": executor.browser_scroll,
    "wait": executor.browser_wait,
    "done": executor.done,

    # NEW: Computer use actions (full desktop)
    "desktop_screenshot": executor.desktop_screenshot,
    "desktop_click": executor.desktop_click,    # x, y coordinates on screen
    "desktop_type": executor.desktop_type,

    # NEW: Shell
    "bash": executor.bash,                      # command string

    # NEW: File system
    "file_read": executor.file_read,            # path
    "file_write": executor.file_write,          # path + content

    # NEW: Open app / URL in real browser
    "open": executor.open_app,                  # "open https://..." or "open /Applications/Spotify.app"
}
```

#### Step 5 — Update the LLM system prompt

The agent system prompt (inside `llm/adapter.py` or wherever you build the system
prompt) must tell the LLM about the new action types. Add:

```
Available action types:
- browser actions: click, type, navigate, scroll, wait (use Playwright-controlled browser)
- desktop_screenshot: take a screenshot of the full desktop to see any app
- desktop_click: click at pixel coordinates {x, y} on the real desktop
- desktop_type: type text at the current cursor position on the desktop
- bash: run a shell command, get stdout/stderr back
- file_read: read a file from disk
- file_write: write content to a file on disk
- open: open a URL in the real browser or launch a desktop app by path
- done: task is complete

Choose browser actions when you've navigated to a URL in the controlled browser.
Choose desktop actions when you need to interact with the real desktop or any native app.
Choose bash when you need to run system commands, scripts, or check system state.
```

#### Step 6 — Add mode config to config.yaml

```yaml
agent:
  mode: "browser"   # "browser" (Playwright only) | "desktop" (full computer use) | "hybrid"
  max_steps: 50
  token_budget: 100000
```

In hybrid mode: start with browser for web tasks, switch to desktop_screenshot if the
browser gets stuck (e.g., CAPTCHA detected, popup not auto-dismissed).

### Checklist for Problem 2

- [ ] Create `src/asterisk/tools/bash_tool.py`
- [ ] Create `src/asterisk/tools/computer_tool.py` (screenshot + click + type)
- [ ] Create `src/asterisk/tools/file_tool.py`
- [ ] Expand `ACTION_TYPES` in `agent.py`
- [ ] Update LLM system prompt to describe new action types
- [ ] Add `mode` to `config.yaml` and wire it in the agent
- [ ] Write `skills/computer-use/SKILL.md` documenting the desktop tools
- [ ] Write `skills/bash/SKILL.md` documenting the bash tool
- [ ] Write `skills/file-tool/SKILL.md` documenting read/write
- [ ] Update `ARCHITECTURE.md` to reflect the expanded capability surface
- [ ] Update `README.md` with the new action types and mode flag

---

## SELF-MAINTENANCE RULES (do not skip)

After every file you create or modify:
1. Tick the relevant checkbox in `PROJECT_CHECKLIST.md`
2. Update `CLAUDE.md` → CURRENT STATUS and NEXT STEP sections
3. If you discover a non-obvious decision, write it to `decisions/<topic>.md`
4. Before context gets full, write `sessions/session-<timestamp>.md`

Wiki observations to write during this session:
- `wiki/observations/cookie-handling.md` — what popup selectors work and why
- `wiki/observations/desktop-vs-browser.md` — when to use each mode
- `wiki/observations/bash-tool-safety.md` — note any commands to avoid

---

## START HERE

1. Update `PROJECT_CHECKLIST.md` with the two checklists above.
2. Fix Problem 1 completely before starting Problem 2.
3. Run the existing test suite after Problem 1 to make sure nothing broke: `pytest`
4. Then implement Problem 2 tool by tool, testing each in isolation before wiring
   into the agent loop.

Go.
