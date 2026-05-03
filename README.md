# anotherAsterisk

An agentic browser-automation framework that keeps LLM context cost at **O(N)** instead of the naive O(N²) by using a structured wiki as the state regulator.

```
screenshot_now + wiki/status.md + current step file + referenced observations
```

That's all the LLM ever sees — never the full raw history.

---

## Quick start

```bash
pip install -e ".[dev]"
playwright install chromium

cp .env.example .env
# fill in ANTHROPIC_API_KEY (or OPENAI_API_KEY / GEMINI_API_KEY)

asterisk run "search for anotherAsterisk on GitHub" --url https://github.com
```

### Other commands

```bash
asterisk status          # print the live wiki/status.md
asterisk lint            # check for broken [[wikilinks]] in the vault
asterisk wiki            # open the vault in Obsidian (if installed)
```

---

## Configuration

Edit `config.yaml` (copied from defaults on first run):

```yaml
agent:
  max_steps: 50
  token_budget: 100000
  headless: true

llm:
  anthropic:
    model: claude-sonnet-4-6
    max_tokens: 4096

browser:
  viewport_width: 1280
  viewport_height: 800
  slow_mo: 0          # ms delay between actions; set >0 to watch in headed mode

wiki:
  vault_path: ./wiki
```

CLI flags override config values:

```bash
asterisk run "task" --max-steps 20 --headed --provider openai
```

---

## How it works

```
┌──────────────────────────────────────────────────────────────┐
│                      Agent Loop                              │
│                                                              │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────┐  │
│  │  Browser    │───▶│   WikiReader     │───▶│    LLM     │  │
│  │ screenshot  │    │  (O(1) context)  │    │  adapter   │  │
│  └─────────────┘    └──────────────────┘    └────────────┘  │
│                             │                      │         │
│                             │                      ▼         │
│                      ┌──────────────┐     ┌──────────────┐  │
│                      │  WikiWriter  │◀────│ action +     │  │
│                      │  step file   │     │ wiki_update  │  │
│                      └──────────────┘     └──────────────┘  │
│                             │                                │
│                             ▼                                │
│                      ┌──────────────┐                        │
│                      │ status.md    │  (always-loaded anchor)│
│                      └──────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

Each iteration:

1. **Screenshot** — capture the current browser state as a PNG
2. **Load context** — `status.md` + `index.md` + previous step file + any observation files referenced by `[[wikilinks]]` in that step
3. **Call LLM** — send screenshot + context; receive a JSON response with `action`, `wiki_update`, `status_update`, and optional `observation`
4. **Write wiki** — persist the step file; extract and save any observation
5. **Execute action** — click / type / navigate / scroll / wait / done
6. **Update status.md** — so the next step always has fresh state

---

## Wiki vault structure

```
wiki/
├── status.md                    # always loaded — current task, step, URL
├── index.md                     # always loaded — task registry
├── steps/
│   └── buy-milk/
│       ├── step-001.md          # each step: action, outcome, related links
│       ├── step-001.png         # screenshot alongside step
│       └── step-002.md
└── observations/
    └── checkout-flow.md         # reusable facts persisted by the LLM
```

Wikilinks in step files (`[[observations/checkout-flow]]`) pull those pages into the next step's context. This is the selective-retrieval mechanism that keeps context small.

---

## LLM providers

Set `LLM_PROVIDER` in `.env` or pass `--provider` on the CLI:

| Value | SDK | Auth env var |
|---|---|---|
| `anthropic` (default) | `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `openai` | `OPENAI_API_KEY` |
| `gemini` | `google-generativeai` | `GEMINI_API_KEY` |

The Anthropic adapter caches the system prompt so steps 2+ pay only 0.1× on the prompt tokens.

---

## Running tests

```bash
pytest
pytest -v tests/test_integration.py   # just the mock-LLM integration test
```

No real API keys or browser required — the integration tests mock both the LLM and Playwright.

---

## Project layout

```
src/asterisk/
├── agent.py                # core loop
├── browser.py              # Playwright controller
├── config.py               # config.yaml loader
├── token_counter.py        # per-step cost tracking
├── llm/
│   ├── adapter.py          # base class + factory
│   ├── anthropic_adapter.py
│   ├── openai_adapter.py
│   └── gemini_adapter.py
└── wiki/
    ├── reader.py           # context assembler
    ├── writer.py           # step file + status writer
    ├── resolver.py         # [[wikilink]] → path resolver
    └── observation_extractor.py
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the cost model and design decisions.
