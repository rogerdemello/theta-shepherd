# Theta Shepherd — One-Page Write-Up

**Alpaca AI Trading Agents Hackathon · lablab.ai × Alpaca · Aug 28 – Sep 4 2026**
**Paper account ID:** `PA31OBPWA7MW` · **Repo:** github.com/rogerdemello/theta-shepherd · **Live dashboard:** rogerdemello.github.io/theta-shepherd

## What it is

Theta Shepherd is a fully autonomous options income agent. It sells defined-risk
vertical credit spreads (put and call sides; paired they form iron condors) on SPY,
QQQ and IWM in Alpaca's paper environment, harvesting theta over 1–7 day expiries — a
strategy chosen deliberately for a one-week P&L contest: high probability of profit,
strictly bounded downside, and daily compounding of small wins. Final result:
**【P&L, win rate, trades — filled Sep 4】**.

## AI logic — a committee, not a chatbot

1. **Quantitative scout (deterministic).** Pulls option chains with Greeks/IV from
   Alpaca's Market Data API, builds verticals with the short strike at 0.12–0.25
   |delta| ($5 wide; $3 on IWM) and credit ≥ 15% of width, ranked by EV per dollar
   of risk.
2. **The Trading Committee.** Three personas review every candidate in *independent*
   model calls so they cannot anchor on each other: a **Macro Analyst** (calendar and
   event-gap risk), a **Vol Trader** (is the premium worth selling?), and a **Risk
   Officer** (concentration, correlation, path risk — their veto weighs heaviest). A
   **Chair** reads all three opinions and rules; approving zero trades is an
   explicitly good outcome. Every debate is journaled and replayable on the
   dashboard.
3. **The satellite sleeve.** Only when all three personas independently call the same
   market direction may the agent buy one directional debit spread (≤ $2,000 risk,
   +50%/−50% exits, never held into its final day). Unanimity among adversarial
   personas is rare by design — conviction is the scarce resource being spent.
4. **The shepherd learns.** After each close, a retrospective LLM reads the day's
   full journal and writes concrete, falsifiable lessons to `lessons.md`, which is
   injected into the next day's committee prompts. Wednesday's agent is provably
   smarter than Monday's.

The LLMs cannot invent trades, cannot exceed the scout's candidates, can only size
*down*, and cannot touch exits — those are mechanical.

## Risk gates (hard-coded, no LLM can override)

- **Per-trade cap:** worst-case loss ≤ $2,000; size derives from the cap, never conviction.
- **Risk ladder:** portfolio cap starts at $4,000 and earns +$2,000 per *green day*
  up to $10,000 — risk is a privilege the book pays for.
- **Daily circuit breaker** (−$3,000 halts entries) · **5% drawdown kill switch**
  (flattens everything) · max 6 spreads, 2 new per cycle.
- **Econ-calendar guard:** entry blackouts around ISM/ADP/Claims releases, and a
  hard-coded **flatten-all at Sep 3, 3:30 PM ET** — the agent refuses to hold risk
  through nonfarm payrolls, which lands two hours before this contest's deadline.
- **Mechanical exits:** +50% profit target, 2× credit stop, expiry-day force close.

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

Cycles run every 20 minutes via scheduler, fully unattended; the retrospective runs
nightly. An append-only JSONL journal records every observation, debate, order and
realized P&L; 69 pytest tests cover spread math, risk gates, OCC parsing, the
calendar guard, and broker reconciliation against a fake client.
