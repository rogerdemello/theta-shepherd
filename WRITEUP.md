# Theta Shepherd — One-Page Write-Up

**Alpaca AI Trading Agents Hackathon · lablab.ai × Alpaca · Aug 28 – Sep 4 2026**
**Paper account ID:** `PA31OBPWA7MW` · **Repo:** github.com/rogerdemello/theta-shepherd · **Live dashboard:** rogerdemello.github.io/theta-shepherd

## What it is

Theta Shepherd is a fully autonomous options income agent. It sells defined-risk
vertical credit spreads (put and call sides; paired they form iron condors) on SPY,
QQQ and IWM in Alpaca's paper environment, harvesting theta over 1–7 day expiries — a
strategy chosen deliberately for a one-week P&L contest: high probability of profit,
strictly bounded downside, and daily compounding of small wins. It runs unattended on
a 20-minute schedule and nobody approves its trades. Final result:
**【P&L, win rate, trades — `python run_agent.py --stats` on Sep 4】**.

## AI logic — a committee, not a chatbot

1. **Quantitative scout (deterministic).** Pulls option chains with Greeks/IV from
   Alpaca's Market Data API and builds verticals with the short strike at 0.15–0.25
   |delta| ($5 wide; $3 on IWM), ranked by expected value per dollar of risk. The EV
   model prices *the exit policy the agent actually runs* — win 50% of the credit,
   lose one credit at the stop — not a hold-to-expiry fantasy it never takes, and
   candidates with EV ≤ 0 are dropped before any model sees them. Nothing is opened
   that expires after the contest's mandatory flatten, so no premium is sold that
   must be bought back early.
2. **The Trading Committee.** Three personas review every candidate in *independent*
   model calls so they cannot anchor on each other: a **Macro Analyst** (calendar and
   event-gap risk), a **Vol Trader** (is the premium worth selling?), and a **Risk
   Officer** (concentration, correlation, path risk — their veto weighs heaviest). A
   **Chair** reads all three opinions and rules; approving zero trades is an
   explicitly good outcome. Every debate is journaled and replayable on the
   dashboard.
3. **The satellite sleeve.** Only when all three personas independently call the same
   market direction may the agent buy one directional debit spread (≤ $4,000 risk,
   +50%/−50% exits, never held into its final day). The engine re-verifies that
   unanimity itself — the Chair's say-so is not enough. Unanimity among adversarial
   personas is rare by design: conviction is the scarce resource being spent.
4. **The shepherd learns.** After each close, a retrospective LLM reads the day's
   full journal and writes concrete, falsifiable lessons to `lessons.md`, which is
   injected into the next day's committee prompts. Wednesday's agent is provably
   smarter than Monday's — and on Sep 1 the retrospective independently flagged the
   same book-concentration problem the author found by hand.

The LLMs cannot invent trades, cannot exceed the scout's candidates, can only size
*down*, and cannot touch exits — those are mechanical.

## Risk gates (hard-coded, no LLM can override)

- **Per-trade cap:** worst-case loss ≤ $4,000; size derives from the cap, never conviction.
- **Risk ladder:** the portfolio risk cap earns +$5,000 per *green day* up to $25,000 —
  risk is a privilege the book pays for, and every position is defined-risk and
  stop-checked every 20 minutes.
- **Directional balance:** no more than two same-side spreads without the other side
  on the book. A book of nothing but put spreads is a levered bet that the market
  stops falling, not the market-neutral premium harvest this agent claims to run;
  diversifying by underlying does nothing for it.
- **Daily circuit breaker** (−$5,000 halts entries) · **5% drawdown kill switch**
  (flattens everything) · max 12 spreads, 3 new per cycle · a `STOP` file in the repo
  root as a human's manual brake.
- **Econ-calendar guard:** entry blackouts around ISM/ADP/Claims releases, and a
  hard-coded **flatten-all at Sep 3, 3:30 PM ET** — the agent refuses to hold risk
  through nonfarm payrolls, which lands two hours before this contest's deadline.
- **Mechanical exits:** +50% profit target, 2× credit stop; expiry-day spreads ride
  the morning's accelerated theta and hard-close from 2 PM ET (never the
  final-hours gamma).

## Alpaca infrastructure — all four pillars

- **Trading API:** atomic multi-leg **MLEG** limit orders for entries and exits (legs
  can never fill one-sided), broker-truth reconciliation each cycle, order working
  (unfilled entries repriced one step, never churned).
- **Market Data API:** chains with Greeks/IV, option quotes for mark-to-market,
  Benzinga news fed to the committee.
- **Alpaca CLI:** account, positions and option-Greeks snapshots journaled every
  cycle — operator-visible ground truth from the same commands a human runs.
- **MCP server:** the official `alpaca-mcp-server` connected to the same account, so
  a human can ask Claude *"how is the flock doing?"* while the agent works — the CLI
  is the agent's hands, MCP is the human's window (real transcript in
  `docs/mcp_demo.md`).

## Running unattended is the hard part

Four Windows scheduled tasks (cycle, health watchdog, nightly retrospective,
dashboard publish) keep the agent trading and the demo page live with no server. The
engineering that matters is what happens when something breaks mid-session: a cycle
lockfile and atomic state writes, every submitted order persisted before the next API
call, per-spread fault isolation so one unquotable leg cannot cost the rest of the
book its stops, cancel-confirmation before any reprice or re-close (a cancel is a
request, not an event), retries with backoff on idempotent reads only, and a
9-point preflight that verifies the machine itself can run the schedule — registered
tasks that cannot actually launch are how the agent silently died for two hours on
day 1. All decisions land in an append-only JSONL journal; **130 pytest tests** cover
spread math, EV, risk gates, OCC parsing, the calendar guard, broker reconciliation
against a fake client, and every one of those failure modes.
