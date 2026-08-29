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

## Done Sat Aug 29 ✅ (weekend block 1)

- **B1 Trading Committee** (`committee.py`): Macro Analyst + Vol Trader + Risk Officer (independent Azure calls) + Chair; drop-in replacement for Gatekeeper (kept as fallback); full debate journaled as `committee_debate`; `unanimous` flag per approval (satellite-sleeve plumbing ready). Live-tested: personas disagreed, chair ruled no-trade — sensible.
- **B2 Retro** (`retro.py`): `--retro [date]` → `journal/lessons.md` (day sections, re-run replaces); `load_lessons()` injected into committee prompts. Ran for Aug 28 — real lessons written.
- **A5 Risk ladder**: cap $4k base +$2k/green day → $10k ceiling, ET-date stepped, in `state.json` `ladder`, journaled `risk_ladder`; `entry_gates(..., portfolio_cap)`.
- **E pytest**: 48 tests green (`python -m pytest tests/`), incl. fake-broker reconcile.
- **E schedulers registered**: "ThetaShepherd Cycle" (Mon–Fri 19:00 IST, every 20 min for 6.5h → next fire Mon Aug 31 19:00) and "ThetaShepherd Retro" (Tue–Sat 01:45 IST). Wrappers: `scheduler_cycle.bat` / `scheduler_retro.bat` (log → `journal/scheduler.log`).
- **C MCP**: official `alpaca-mcp-server` (PyPI, via uvx) registered in Claude Code local scope with `--env-file` → ✔ Connected. `.mcp.json.example` committed; README documents it.
- **D Dashboard**: `dashboard.py` + `dashboard_template.html` → `docs/dashboard.html` (self-contained, light+dark, equity curve w/ hover, risk-ladder meter, flock, debate viewer, lessons, timeline). **GitHub Pages enabled** (main:/docs): https://rogerdemello.github.io/theta-shepherd/ (demo URL for submission — user said don't use Claude artifacts). Regenerate after each session: `python dashboard.py` then commit docs/.
- **F Post #2** drafted in `social/posts.md` (committee debate; attach dashboard debate-card screenshot). Posts #1/#2 may still be unposted — check with user.
- Journal gotcha handled: first-session events used `kind` as event key; `dashboard.py::_normalize` adapts them. `entry_filled` now logs qty+short_symbol.
- Account is green: equity ~$100,016 (+$16 day) as of Sat.

## Done Sat Aug 29 block 2 ✅ ("I want to win" push)

- **A6 satellite sleeve SHIPPED**: personas emit `directional_view`; chair may propose `satellite` only on 3-way non-neutral unanimity (engine re-verifies in `committee.py::unanimous_direction`); `find_satellite_candidate` (long ~0.55Δ, $5 wide, debit ≤60% width, 2–7 DTE); `open_satellite`/`close_satellite` (positive MLEG limit = debit); exits +50%/−50%/DTE≤1; one at a time, ≤$2k (`satellite_gates`); unfilled entries abandoned not chased. **62 tests green.**
- CLI options snapshot spot-checks each cycle (`cli_ops.snapshot_options`, short legs, journaled `cli_options_snapshot`) — verified live.
- README: mermaid architecture diagram + satellite paragraph.
- `presentation/video_script.md` (3-min, timed, 【】 placeholders) + `presentation/slides.md` (7 slides).
- **Cover image**: `docs/cover.png` (1280×720, regenerate from `presentation/cover.html` via headless Edge).
- **Claude artifacts are OUT** (user asked to delete them — deletion only possible by user at claude.ai/code/artifacts; do NOT publish new ones). Demo URL for the submission is GitHub Pages only: **https://rogerdemello.github.io/theta-shepherd/** (regenerate with `python dashboard.py`, commit docs/, push — Pages redeploys automatically).

## Done Sat Aug 29 block 3 ✅ (approved plan `linear-churning-plum`)

- **IWM added** (3rd underlying) with per-underlying width: `settings.width_for()` — $5 default, $3 IWM. Verify IWM candidates appear in Monday's `--scout`.
- **Featherless multi-model committee**: Vol Trader runs on `FEATHERLESS_MODEL` (default Qwen2.5-72B) via OpenAI-compatible API **when `FEATHERLESS_API_KEY` lands in `.env`** (per-seat Azure fallback; opinion journaled with `_model`). `chat_json` now client-agnostic with tolerant JSON extraction. **Live-smoke the committee once the user provides the key.** 69 tests green.
- **Dashboard**: trade markers on equity curve (hollow=open, filled=close, tooltips), win-rate + debates tiles, model name shown per persona card.
- **README hero**: cover + dashboard screenshot (`docs/dashboard_screenshot.png`) + live-dashboard link at top.
- **`docs/mcp_demo.md`**: REAL MCP transcript (alpaca-mcp-server v3.4.7 over stdio: 72 tools, account, positions leg-by-leg net +$16 unrealized, clock).
- **WRITEUP.md** fully refreshed (committee/satellite/ladder/learning + all 4 Alpaca pillars; 【】 for Thu numbers). **`social/submission_form.md`**: copy-paste form fields.
- ⚠️ Gotcha learned: alpaca-mcp-server exposes destructive tools (`close_all_positions` etc.) — a name-heuristic demo script accidentally called it (all 4 legs rejected 422, market closed, zero harm; verified 0 open orders, positions intact). **Never pick MCP tools by heuristic; use exact read-only names.**

## Still TODO

- ~~Featherless persona~~ — user declined (no API). Code stays dormant (activates only if a key ever lands in .env); all claims scrubbed from WRITEUP/submission form. Committee is Azure-only.
- Mon–Wed: daily verify fills / regenerate+push dashboard (Pages) / post; Wed flatten check; Thu video+slides+writeup+regenerate keys+submit
- User actions pending: post #1 and #2 on X/LinkedIn; delete the two private dashboard artifacts at claude.ai/code/artifacts

## Done ✅ (Fri Aug 28)

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
