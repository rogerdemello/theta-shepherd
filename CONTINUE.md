# CONTINUE.md — Session handoff for Theta Shepherd

> Read this first in a new session. Full plan: `C:\Users\AGAE2-LPT2324007\.claude\plans\fuzzy-puzzling-bird.md`

## What this is

**Theta Shepherd** — autonomous options premium-selling agent for the **Alpaca AI Trading Agents Hackathon** (lablab.ai × Alpaca). Goal: win the $6,300 pool.

- **Deadline: Thu Sep 4, 8:30 PM IST (= 11:00 AM ET)** — submission on lablab.ai
- Judging: P&L performance, tech implementation (Trading API + MCP/CLI + options mandatory), creativity, presentation, social engagement
- Repo (public): **https://github.com/rogerdemello/theta-shepherd** (MIT, main branch)
- Alpaca paper account: **PA31OBPWA7MW** (fresh, $100k start, options Level 3) — this ID goes in the submission form

## Live state (as of Mon Aug 31 ~21:40 IST, session 1 in progress)

Equity **~$100,007** (+$7 total). Realized winner today: the 728/733 call spread closed at the
50% profit target. Open book:
- QQQ **704/699** put spread x2, exp Sep 4 — last leg of the original condor (grandfathered
  past the contest horizon; exits/flatten handle it)
- QQQ **707/702** put spread x9, exp Sep 3 — opened 21:01
- IWM **291/288** x16 @ ~0.51, exp Sep 3 — filled 21:4x

No open orders. Committed risk ~$8.6k against the $10k ladder rung, so the hard risk gate is
now vetoing new candidates (`portfolio_risk_cap`) — working as designed; the ladder steps up
+$5k per green day toward the $25k ceiling.

Day P/L swings ±$70 intraday on mark-to-market noise in short options — not a signal.

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

## Done Sat Aug 29 block 4 ✅ — CONTEST MODE (user: "earn more than others")

Research-backed P&L push (50%-manage-and-redeploy beats hold; expiry-day AM theta is the richest, PM gamma is the casino; 0.25–0.30Δ short-DTE still ~70% POP):
- **Capital deployment up ~2.5x**: ladder $10k base +$5k/green → $25k ceiling; per-trade $4k; daily loss halt $5k; 12 spreads max, 3/cycle; delta band 0.15–0.30; satellite $4k. Persisted ladder auto-rebases (base is a floor).
- **Contest-horizon expiry cap**: `effective_max_dte()` — nothing opened expiring after Sep 3 (the flatten). Existing Sep 4 condor is grandfathered; exits/flatten handle it.
- **Expiry-day theta capture**: `should_force_close()` — dte==0 spreads ride until 14:00 ET (stops still every 20 min) instead of closing at open.
- **Committee rebalanced for the contest**: prompts now say idle book ≈ losing book, veto needs a *named* danger; `sessions_remaining_before_mandatory_flatten` fed into evidence. Live smoke: committee approved the good SPY put spread 0.9-confidence full-size (previously vetoed everything) while still rejecting the weak call spread for concentration. **77 tests green.**
- Docs synced (README/WRITEUP numbers). ⚠️ Risk posture now: worst-case book $25k+$4k satellite = 29% of account, mitigated by stops/kill switch/flatten — this was the user's explicit choice to chase P&L.

## Done Sat Aug 29 block 5 ✅ — enterprise hardening

- Atomic state writes (+`.bak` fallback on corruption); cycle lockfile (15-min stale break); escalating exit pads (0.03→0.15 by retry, `close_attempts` tracked); **STOP file** in repo root = manual brake.
- **`--preflight`** (8 checks, live run: all PASS / GO) and **`--health`** self-healing watchdog: third scheduled task "ThetaShepherd Health" (Mon–Fri 19:35 IST, every 30 min ×6h) runs a cycle itself if the 20-min schedule dies mid-session.
- Nightly retro task now also regenerates the dashboard and pushes docs/ → Pages auto-updates.
- **84 tests green.** Monday morning routine: just run `--preflight` before 19:00 IST.

## Done Sat Aug 29 block 6 ✅ — full dry run PASSED

New `--dry-run` mode (full pipeline rehearsal, zero side effects — verified by state.json md5 unchanged). Live results:
- Broker truth: put spread journal=pending_fill / broker=FILLED @0.76 — Monday's first reconcile will adopt it (expected).
- Positions in sync (4 legs, no orphans). Exit engine: both sides "hold" (marks 0.895/0.725 vs targets ~0.51/0.38, stops 2.02/1.52) — correct.
- Ladder rebased 4k→10k; sessions_left=4; no blackout/flatten/STOP.
- Scout: 8 candidates, all expiries ≤ Sep 3 (contest horizon ✓), IWM $3-width present ✓, deltas in 0.15–0.30 ✓.
- Committee live debate: rejected QQQ adds (concentration — Risk Officer), approved SPY 775/780 x9 ($3.7k) + IWM 299/302 x7 ($1.8k) for diversification. Sizing within per-trade $4k and $10k ladder ✓.
- pytest 84 ✓, preflight 8/8 GO ✓, health OK ✓, dashboard regenerated ✓.

## Done Sat Aug 29 block 7 ✅ — near-live frontend

4th scheduled task "ThetaShepherd Publish" (Mon–Fri 19:40 IST, every 30 min ×6h): regenerates dashboard + pushes docs/ → the Pages URL is near-live during sessions without any server. Preflight now checks all 4 tasks (GO ✓). Architecture framing documented in README (headless scheduled backend + generated static frontend = 100% demo uptime).

## Done Mon Aug 31 ✅ — session 1 live, scheduler rescued

**The autonomous system was dead for the first 2 hours of the session and preflight said GO.**
Two independent faults, both now fixed:

1. **Unquoted action path.** `schtasks /TR "E:\Alapaca hackathon\scheduler_cycle.bat"` stored the
   path unquoted, so Windows tried to launch `E:\Alapaca` → `0x80070002` every 20 min from 19:00.
2. **Battery gate.** `DisallowStartIfOnBatteries=true` (the schtasks default) left every task
   `Queued` forever — this is a laptop and it was unplugged at 39%.

Fix: all four tasks re-registered via `Set-ScheduledTask` with `-Execute <bat path>` directly
(a clean `<Command>` XML field — **no `cmd.exe /c` wrapper**, that reintroduces quoting hell and
died with `0xC000013A`) plus `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
-StartWhenAvailable`. Verified: Publish and Health both return `0` and do real work.

- **Preflight hardened** (`_check_schtasks`): registration is not readiness. Now also verifies the
  task is enabled, its target script exists, the space-bearing path survives unwrapping, and the
  last run didn't fail to launch. **93 tests green** (+9 in `tests/test_preflight_tasks.py`).
- Trading today: closed the QQQ 728/733 call spread at **50% profit target** (0.475 vs 1.01
  credit); opened **QQQ 707/702 x9** @ ~0.84 and **IWM 291/288 x16** @ ~0.51 (committee chose
  IWM explicitly to diversify away from QQQ concentration).
- ⚠️ **Laptop must stay plugged in and awake during 19:00–01:30 IST.** The battery gate is off
  now, but sleep/hibernate still stops the schedule dead. This is the single biggest operational
  risk left for Tue/Wed.

## Done Tue Sep 1 ✅ — session 1 closed green, strategy corrected

**Session 1 finished at +$506** (equity $100,506). The intraday "we're down" moment was a
transient mark: overnight theta flipped all three spreads to +$404 unrealized. Scheduler ran
unattended all night — Cycle/Health/Publish all `result=0`.

Two substantive strategy defects found and fixed (see commit `333f617`):

1. **EV modelled hold-to-expiry**, an outcome the agent never takes — it stops at 2× credit
   first. Every candidate on the board scored negative (−26 to −69/lot), so the committee
   reasoned against uniformly scary numbers and EV/risk ranking was biased toward low delta.
   EV now models the real policy (win `profit_target_frac` of credit, lose
   `stop_loss_mult − 1` credits, capped by true max loss). Break-even is **POP > 2/3**, i.e.
   short delta < ~0.333 — which the 0.15–0.30 band satisfies.
2. **Candidates with EV ≤ 0 are now dropped.** The credit floor never implied positive EV:
   break-even needs `credit ≥ |delta| × width`, but `min_credit_frac` only asks 15% of width.
3. **Directional balance gate** (`max_same_direction_spreads = 2`): the book had gone to 100%
   put credit spreads — net long delta, every leg losing together on a selloff, which is
   exactly what three down sessions delivered. Diversifying QQQ → IWM did nothing for this.
   The gate never blocks the trade that would rebalance.

Live effect: board went **8 candidates all-negative → 5 all-positive, call spreads taking the
top three**. The nightly retro independently flagged the same concentration and EV problems.

Also fixed (commit `c4f70c4`): the 01:45 retro exited 1, wrote no lessons, and reported "No
journal events" — while that day's journal held 88 events. `run_retro()` returns `""` both for
"nothing happened" and "model returned nothing", and the caller printed the benign message for
both. Now retries once, distinguishes the cases, and exits 1 on real failure. Publish and Retro
both commit+push within seconds; the loser's push was rejected, so both now rebase-and-retry.

**99 tests green.**

## Done Tue Sep 1 (pre-open) ✅ — P&L tuning off the measured EV surface

User: "make it the best, most profit out of all." Measured rather than guessed — 96 live
candidates (SPY/QQQ/IWM, 1–2 DTE), expected dollars per **$10k of risk deployed**:

| delta | 0.10 | 0.15 | **0.20** | 0.25 | 0.30 | 0.35 | 0.40 | 0.45 |
|---|---|---|---|---|---|---|---|---|
| $/10k | 196 | 218 | **258** | 218 | 113 | −76 | −353 | −598 |

- **The credit floor was excluding the peak.** At delta 0.20 credit is ~10.9% of width, under
  the old `min_credit_frac = 0.15`. The agent was structurally confined to the 0.25–0.30
  shoulder. Floor → **0.08**, band → **0.15–0.25**. Edge is gone entirely past 0.35.
- **Ladder matched to the horizon.** +$5k/green day from $10k reaches the $25k ceiling on Sep 4,
  a day *after* the flatten — risk that arrives after the deadline is never deployed.
  `ladder_base_risk` → **$20k**; with the green-day step the live cap is now **$25k** vs $8.6k
  committed.

Result: 5 → 8 candidates, top score 0.034 → 0.036, deltas 0.227–0.294 → **0.175–0.218**, POP
0.70–0.77 → **0.78–0.825**. Better EV per dollar *and* a higher win rate.

⚠️ **Risk posture is now deliberately aggressive** — up to $25k of defined risk (25% of the
account) at the user's explicit direction. The circuit breakers are untouched and are what
bound the downside: $5k daily loss limit, 5% drawdown kill switch, 2× credit stops every
20 min, mandatory Sep 3 flatten. Realistic bad day ≈ −$3k (all spreads stopping at 2×), not
−$25k, since max loss requires gapping through both legs with no stop fill.

Dry run confirmed end-to-end: would open a SPY call spread to rebalance, directional gate
vetoing two put spreads, exits all holding. **99 tests green.**

## Done Tue Sep 1 (pre-open) ✅ — failure-mode hardening pass

Audited every path where the agent could lose money or lose track of a position
without anyone noticing until morning. **123 tests green** (+24 in
`tests/test_hardening_session2.py`), preflight **9/9 GO**, dry run clean.

1. **Timezone bug in every DTE calculation (silent, real P&L).** `date.today()`
   on an IST machine is a day *ahead* of the market from 00:00–01:30 IST — the
   last 90 minutes of every session. A spread expiring tomorrow read as
   `dte=0`, so the expiry-day rule (force close from 14:00 ET) would have
   liquidated the Sep-3 book on **Tue Sep 2 at 14:30 ET, a full day early**,
   surrendering the richest day of theta; `effective_max_dte` hit 0 in the same
   window and emptied the scout. New `econ_calendar.today_et()` is now the only
   date DTE is measured against (`market.OptionQuote.dte`, `market.chain`,
   `strategy.effective_max_dte`, exits, dry run, test fixtures).
2. **Crash safety.** Every submitted order is persisted before the next API
   call (`execute_approvals`, satellite, each exit, each flatten leg) and state
   is saved right after `reconcile`. Previously an exception between two
   submissions left a live order at the broker that state.json had never heard
   of — no stop, no profit target, no flatten.
3. **Fault containment.** `reconcile`, `manage_exits`, `flatten_all` and the
   entry loop handle each spread independently: one unreadable order or
   unquotable leg is journaled (`reconcile_error` / `exit_error` /
   `flatten_error` / `entry_submit_error`) and the rest of the book still gets
   managed. `cli_ops._run` now catches everything — it sits between the exit
   engine and the hard guards, so an escape there would have skipped the
   flatten and the kill switch.
4. **Cancel races.** A cancel is a request, not an event. `_cancel_and_confirm_dead`
   polls for a settled status; if the cancel never settles we do **not** reprice
   (two spreads, one journal entry) and do **not** re-close (a second close
   order that fills leaves us short the inverse). Journaled
   `entry_cancel_unconfirmed` / `exit_cancel_unconfirmed`.
5. **Eviction paranoia.** A single empty `get_all_positions()` read while state
   tracks open spreads no longer deletes them — a blank/partial response and a
   flat account are indistinguishable over one call, and an evicted spread is
   one the agent will never close again. Needs two consecutive empty reads.
6. **Directional gate integrity.** `risk.open_kinds` now updates *during* the
   cycle, so three put spreads approved in one cycle no longer all pass the
   gate that exists to stop exactly that.
7. **Transient-failure retries** (`resilience.retry`, 3 attempts, exponential
   backoff, journaled `api_retry`) on idempotent reads only — clock, account,
   positions, orders, quotes, chains. Never on submit/cancel.
8. **Stuck exits**: `exit_stuck` journaled after 5 failed close attempts, and
   the flatten now escalates its pad like any other exit (being flat by the
   deadline outranks the last cent).
9. **Liquidity floor**: legs quoted wider than `max(0.15, 0.5 × mid)` are
   dropped — the stop rule assumes the short leg can be bought back near its
   mark. Measured on the live board: **0 of 381 legs rejected, 8 candidates
   either way** — it costs nothing in normal markets and only bites in a
   stressed tape.
10. **Preflight check #9: power.** Sleep is the one failure the health watchdog
    cannot heal (a sleeping laptop runs no task). Verifies idle sleep and
    hibernate are disabled on AC; currently both 0 ✓. The residual risk is
    still manual sleep / lid close / unplugging.

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

- **Never call `date.today()` in this codebase.** The machine is IST, the market
  is ET, and local midnight lands at 14:30 ET — mid-session. Use
  `econ_calendar.today_et()` / `now_et()` for anything dated, including test
  fixtures.
- Windows: set `$env:PYTHONIOENCODING='utf-8'` before running (CLI box-drawing chars vs cp1252); `cli_ops.py` already handles its own subprocess encoding
- MLEG orders at mid often rest a few minutes — reprice logic handles it; don't panic-cancel
- `journal.log_event` uses key `event` (not `kind` — candidate dicts carry their own `kind`)
- `ContractType` imports from `alpaca.trading.enums`, not `alpaca.data.enums`
- LLM correctly declines trades citing macro events — that's designed behavior, not a bug
- **Scheduled tasks: never register with `schtasks /TR` when the path contains a space** — it
  stores it unquoted and every run dies `0x80070002`. Use `Set-ScheduledTask -Execute <path>`.
  Wrapping in `cmd.exe /c ""…""` is *not* the fix (dies `0xC000013A`); invoke the `.bat` directly.
- A task stuck in state `Queued` that never runs = a conditions problem (battery/idle/network),
  not a command problem. `schtasks /Query /XML` shows the real settings; `Last Result: 267011`
  just means "never run yet"
- A cycle killed mid-flight leaves `journal/cycle.lock`; the agent breaks it after 15 min, but
  delete it by hand to avoid skipping the next scheduled cycle
- **Never let two scheduled tasks `>>` the same log file.** Cycle (:00/:20/:40) and Publish
  (:10/:40) overlap at :40; the loser of the concurrent append dies with **exit 1 and no output
  whatsoever**, which reads like a phantom failure. Each task now writes
  `journal/scheduler_<task>.log`. Verified by triggering both at once: Cycle=0, Publish=0.
