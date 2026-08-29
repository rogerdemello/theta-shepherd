# CONTINUE.md — Session handoff for Theta Shepherd

> Read this first in a new session. Full plan: `C:\Users\AGAE2-LPT2324007\.claude\plans\fuzzy-puzzling-bird.md`

## What this is

**Theta Shepherd** — autonomous options premium-selling agent for the **Alpaca AI Trading Agents Hackathon** (lablab.ai × Alpaca). Goal: win the $6,300 pool.

- **Deadline: Thu Sep 4, 8:30 PM IST (= 11:00 AM ET)** — submission on lablab.ai
- Judging: P&L performance, tech implementation (Trading API + MCP/CLI + options mandatory), creativity, presentation, social engagement
- Repo (public): **https://github.com/rogerdemello/theta-shepherd** (MIT, main branch)
- Alpaca paper account: **PA31OBPWA7MW** (fresh, $100k start, options Level 3) — this ID goes in the submission form

## Live state (as of Fri Aug 28 ~23:00 IST)

**Open position:** QQQ iron condor, exp **Sep 4 2026**, 2 lots each side, filled:
- Call credit spread 728/733 @ $1.01 credit ($202 collected)
- Put credit spread 704/699 @ $0.76 credit ($152 collected, filled after auto-reprice)
- Total premium $354, worst case ~$1,646. Equity ~$99,984 (entry mark noise, normal).
- ⚠️ `journal/state.json` may still show the put as `pending_fill` — the next cycle's `reconcile()` will flip it to `open` automatically (it filled after the last cycle ran).

**Exits are mechanical:** buy back at 50% of credit, stop at 2× credit, force-close at expiry day. Hard-coded **flatten-all at Sep 3, 3:30 PM ET** (NFP lands 8:30 AM ET Sep 4, 2h before the deadline — book must be flat and the equity curve frozen green).

## How to run

```powershell
cd "E:\Alapaca hackathon"
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe run_agent.py --scout     # dry run, ranked candidates
.\.venv\Scripts\python.exe run_agent.py             # one full cycle (the normal thing)
.\.venv\Scripts\python.exe run_agent.py --loop      # continuous, 30-min cycles
.\.venv\Scripts\python.exe run_agent.py --flatten   # close everything now
```

Market hours: 19:00–01:30 IST (Mon–Fri). Next open: **Mon Aug 31, 19:00 IST**.
During market days, run cycles every ~20–30 min (`--loop` or Task Scheduler — not yet registered).

## Environment (all working, verified)

- Project venv: `.venv` (Python 3.12) — alpaca-py 0.44, openai 3.5, dotenv, rich
- `alpaca-cli` v0.4.0b1 installed globally via `uv tool install alpaca-cli --python 3.14` (needs Python ≥3.14 **stable**; 3.14 beta breaks pydantic; uv was upgraded to 0.12.7 for this)
- Credentials: `.env` (Alpaca + Azure OpenAI, gitignored) and `~/.alpaca.json` (for the CLI). Azure deployment: `gpt-4o`, api version `2024-12-01-preview`, endpoint `openai-04.openai.azure.com`
- GitHub: `gh` authed as `rogerdemello`
- Journal: `journal/YYYY-MM-DD.jsonl` (audit trail) + `journal/state.json` (open spreads, peak equity). Gitignored.

## Architecture (files in `theta_shepherd/`)

`strategy.py` scout (0.12–0.25Δ shorts, $5 wide, 1–7 DTE, credit ≥15% width, EV-ranked) → `llm.py` Azure OpenAI gatekeeper (approves ≤2/cycle, sizes down only, sees news + macro calendar) → `risk.py` hard gates ($2k/trade, $10k portfolio, $3k daily loss, 6 spreads max) → `execution.py` atomic MLEG limit orders (**negative limit = credit**) → `agent.py` cycle: reconcile → broker sync → exits → guards (NFP flatten, 5% drawdown kill switch, blackouts in `econ_calendar.py`) → scout → LLM → gates → execute. `cli_ops.py` shells to `alpaca-cli` each cycle (CLI requirement). `journal.py` logs everything.

## Done ✅

- Full agent working end-to-end, live-tested during market hours (2 cycles, real fills)
- Hardening: broker-truth sync, order working (reprice $0.03/cycle toward executable), `--flatten`, drawdown kill switch, econ calendar guard (ISM Sep 1, ADP Sep 2, Claims/ISM-Svc Sep 3, NFP Sep 4)
- Git repo public with MIT license, 2 commits pushed
- Post #1 drafted in `social/posts.md` (X + LinkedIn) — **user may not have posted it yet, check**
- README.md + WRITEUP.md (one-pager, needs final numbers later)

## TODO (from approved plan — weekend work, market closed Sat/Sun)

| # | Task | Notes |
|---|---|---|
| A5 | Risk ladder | portfolio cap $4k → +$2k per green day → $10k, config-driven, journaled |
| A6 | Satellite sleeve | ≤$2k directional debit spread, only on unanimous committee |
| B1 | **Trading Committee** | replace single gatekeeper: Macro Analyst + Vol Trader + Risk Officer personas (separate Azure calls) + Chair synthesis in new `committee.py`; journal full debate — demo gold |
| B2 | **Nightly retrospective** | `retro.py`: LLM reads day's journal → `journal/lessons.md` → injected into next-day prompts ("the shepherd learns") |
| C | MCP server | install `alpacahq/alpaca-mcp-server` against same paper account = human overseer console narrative; also add `alpaca-cli data options snapshot` spot-checks |
| E | pytest suite | strategy pairing, EV math, risk gates, OCC parser, reconcile with fake broker |
| E | Scheduled task | `schtasks` every 20 min, 19:00–01:30 IST window |
| D | Dashboard | `dashboard.py` → static HTML from journal + account: equity curve, flock table, debate viewer, risk gauge (use dataviz skill) |
| D | Video script + slides | 3-min video, 7 slides; hook = equity curve + "agent knew when NOT to trade" (NFP story) |
| F | Posts 2–5 | drafts in `social/posts.md`, fill as milestones land |

## Day-by-day remaining

- **Sat–Sun Aug 29–30:** all weekend TODO above (committee, retro, MCP, tests, dashboard v1), post #2
- **Mon Aug 31 – Wed Sep 3:** agent trades autonomously every session; daily: verify fills, run retro, screenshot dashboard, post; ladder risk up on green days
- **Wed Sep 3:** flatten-all fires at 3:30 PM ET automatically (verify!); freeze code; dashboard final
- **Thu Sep 4:** video, slides, WRITEUP final numbers, **regenerate Alpaca + Azure keys** (current ones passed through chat), submit by ~6 PM IST buffer

## Submission checklist (lablab.ai form)

- [ ] Alpaca account ID: PA31OBPWA7MW
- [ ] GitHub repo URL (public, MIT) ✅ exists
- [ ] Video presentation + slide presentation
- [ ] Cover image
- [ ] Demo/app URL (dashboard artifact can serve)
- [ ] Up to 5 social post links (X/LinkedIn, tagging @lablabai + @AlpacaHQ)
- [ ] One-page write-up = WRITEUP.md (AI logic, risk gates, infrastructure)

## Gotchas learned

- Windows: set `$env:PYTHONIOENCODING='utf-8'` before running (CLI box-drawing chars vs cp1252); `cli_ops.py` already handles its own subprocess encoding
- MLEG orders at mid often rest a few minutes — reprice logic handles it; don't panic-cancel
- `journal.log_event` uses key `event` (not `kind` — candidate dicts carry their own `kind`)
- `ContractType` imports from `alpaca.trading.enums`, not `alpaca.data.enums`
- LLM correctly declines trades citing macro events — that's designed behavior, not a bug
