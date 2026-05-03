# anotherAsterisk — Architecture

## The core problem

Most agentic loops accumulate context by appending every prior message to each new LLM call:

```
Step 1:  [system] [user: screenshot₁]                     → ~1K tokens
Step 2:  [system] [user: screenshot₁] [assistant: a₁] [user: screenshot₂]  → ~2K tokens
Step N:  [system] [user: s₁] … [user: sₙ]                → ~N·K tokens
```

Cost is **O(N²)** in the number of steps. A 50-step task with 2K tokens per step produces a 50th step that sends ~100K tokens. With prompt caching the constant shrinks but the quadratic shape holds.

---

## The regulator model

anotherAsterisk replaces raw history with a **wiki vault** that acts as a state regulator. Each LLM call receives a fixed-size context window regardless of how many steps have elapsed:

```
context = screenshot_now
        + wiki/status.md          (always: current task, step, URL)
        + wiki/index.md           (always: task registry)
        + steps/<task>/step-N.md  (the single previous step)
        + observations/*.md       (only pages linked from that step)
```

Step N sees roughly the same number of tokens as step 1. Cost is **O(N)**.

```
Naive accumulation:   cost = K · N²/2
Wiki-regulated:       cost = K · N · C    (C = avg context pages per step, typically 3–5)

At N=50, C=4:         naive = 1250·K,  regulated = 200·K   →  6× cheaper
At N=100, C=4:        naive = 5000·K,  regulated = 400·K   →  12.5× cheaper
```

---

## Selective retrieval via wikilinks

The step file written after each action contains a `related` field:

```json
{
  "related": ["[[observations/checkout-flow]]", "[[steps/buy-milk/step-001]]"]
}
```

On the next step the `WikiReader` resolves those links and injects those files into the context. This is how the agent recalls relevant prior knowledge without replaying everything:

- A page is only loaded if the immediately preceding step references it
- Retrieval is one hop — no recursive following
- The agent itself decides what to link, so it acts as its own retrieval controller

---

## Prompt caching (Anthropic)

The Anthropic adapter marks the system prompt with `cache_control: {"type": "ephemeral"}`. Because the system prompt is identical on every step, all tokens after the first step are served from cache at 0.1× the normal input price.

Combined with wiki regulation, a typical 20-step run looks like:

| Token type | Step 1 | Steps 2–20 |
|---|---|---|
| System prompt (~800 tokens) | write (1.25×) | read (0.1×) |
| Wiki context (~2000 tokens) | full price | full price |
| Output (~300 tokens) | full price | full price |

The `TokenCounter` records both `cache_read_tokens` and `cache_write_tokens` per step and reports total actual cost vs. naive cost in its `summary()`.

---

## Data contract: the step file

Every step produces one markdown file. The canonical source of truth is the JSON block embedded in it:

```json
{
  "step": 3,
  "task": "buy groceries",
  "action_taken": "clicked Add to Cart on milk",
  "element": "#add-to-cart-btn",
  "url": "https://store.example.com/milk",
  "outcome": "success | failure | pending",
  "next_hint": "proceed to checkout",
  "related": ["[[steps/buy-groceries/step-001]]", "[[observations/checkout-flow]]"],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

`WikiWriter.write_step()` validates this through Pydantic's `StepSchema` before writing. Invalid data raises `WikiWriteError` rather than writing a malformed file.

---

## Observations

When the LLM notices something reusable — a stable selector, a login pattern, a rate-limit behaviour — it can include an optional `observation` block in its response:

```json
{
  "observation": {
    "slug": "checkout-flow",
    "title": "Checkout flow",
    "content": "The checkout button is always #btn-checkout. CSRF token is in a hidden input."
  }
}
```

`ObservationExtractor` persists this to `wiki/observations/<slug>.md`. If the file already exists the new content is appended under a `---` separator, so the full history of observations for a site is preserved.

The agent then links the observation into the step's `related` list automatically, making it available to any future step that references it.

---

## Wikilink resolution

`WikilinkResolver` uses a three-level fallback that mirrors Obsidian's own resolution order:

1. **Exact match** — `vault/steps/task/step-001.md`
2. **Case-insensitive full-path match** — `STEPS/TASK/STEP-001` resolves to the same file
3. **Basename-only match** — `step-001` resolves if exactly one file named `step-001.md` exists anywhere in the vault (Obsidian "shortest path" behaviour)

The index is rebuilt on each `WikiReader.load_context()` call so step files written during the current run are immediately visible for resolution.

---

## Action execution

The agent supports three capability tiers:

### Browser actions (Playwright)

| Type | Implementation | Required fields |
|---|---|---|
| `click` | `page.click(selector)` with 3-level fallback | `selector` |
| `type` | `page.fill` + `page.type` | `selector`, `value` |
| `navigate` | `page.goto(url)` + auto cookie dismissal | `url` |
| `scroll` | `page.evaluate(window.scrollBy)` | `direction`, `pixels` |
| `wait` | `page.wait_for_timeout(ms)` | `milliseconds` |
| `done` | exits the loop | — |

Anti-detection features:
- **Persistent profile** at `~/.asterisk/browser-profile` — cookies/sessions survive across runs
- **`dismiss_popups()`** — 16 COOKIE_SELECTORS tried after every `navigate()` before screenshot
- **Dialog auto-accept** — `page.on("dialog", ...)` handles `window.alert()` / `confirm()`
- **`playwright-stealth`** — patches `navigator.webdriver` and related fingerprint vectors

### Desktop / computer-use actions (ComputerTool)

| Type | Implementation | Required fields |
|---|---|---|
| `desktop_screenshot` | `screencapture` / `scrot` / PowerShell | — |
| `desktop_click` | `osascript` / `xdotool` | `x`, `y` |
| `desktop_type` | `osascript keystroke` / `xdotool type` | `value` |
| `open` | `open` / `xdg-open` / `start` | `url` or `path` |

### Shell and file system

| Type | Implementation | Required fields |
|---|---|---|
| `bash` | `asyncio.create_subprocess_shell` (30s timeout) | `command` |
| `file_read` | `Path.read_text` | `path` |
| `file_write` | `Path.write_text` (creates dirs) | `path`, `content` |

### Agent modes

Configured via `agent.mode` in `config.yaml` or `--mode` CLI flag:

- `browser` (default) — Playwright only; screenshot = browser viewport
- `desktop` — desktop screenshot + desktop actions; Playwright browser still available for navigation
- `hybrid` — browser for web tasks, desktop when stuck on CAPTCHA or native apps

Action errors are caught, logged, and the loop continues. The agent self-corrects by observing the result in the next screenshot.

---

## Component dependencies

```
cli.py
  └─ config.py           (load config.yaml)
  └─ agent.py
       ├─ browser.py     (Playwright persistent context + cookie dismissal)
       ├─ tools/
       │    ├─ bash_tool.py
       │    ├─ computer_tool.py
       │    └─ file_tool.py
       ├─ llm/adapter.py (LLM provider abstraction)
       ├─ token_counter.py
       └─ wiki/
            ├─ reader.py
            │    └─ resolver.py
            ├─ writer.py
            └─ observation_extractor.py
                 └─ writer.py
```

There are no circular imports. `resolver.py` has no dependencies within the package. `writer.py` depends only on Pydantic.
