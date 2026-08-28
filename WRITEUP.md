# Theta Shepherd — One-Page Write-Up

**Alpaca AI Trading Agents Hackathon · lablab.ai × Alpaca · Aug 28 – Sep 4 2026**
**Paper account ID:** `<fill in before submission>`

## What it is

Theta Shepherd is a fully autonomous options income agent. It sells defined-risk
vertical credit spreads (put and call sides; paired they form iron condors) on SPY and
QQQ in Alpaca's paper environment, harvesting theta over 1–7 day expiries — a strategy
chosen deliberately for a one-week P&L contest: high probability of profit, strictly
bounded downside, and daily compounding of small wins.

## AI logic

Decision-making is split between two layers that check each other:

1. **Quantitative scout (deterministic).** Pulls option chains with Greeks and IV from
   Alpaca's Market Data API, constructs $5-wide verticals with the short strike in the
   0.12–0.25 |delta| band and credit ≥ 15% of width, and ranks candidates by expected
   value per dollar of risk (POP proxied by 1 − |short delta|).
2. **LLM gatekeeper (Azure OpenAI).** Receives the ranked candidates, current account
   state, open positions, and the last 24 h of Benzinga headlines. It approves at most
   two trades per cycle, sizes them down (never up), vetoes structures that clash with
   the tape (e.g. call spreads into a rally, put spreads ahead of CPI/NFP/FOMC), and is
   explicitly told that approving zero trades is a good decision. Every rationale is
   journaled.

The LLM cannot invent trades, cannot exceed the scout's candidates, and cannot touch
exits — those are mechanical.

## Risk gates (hard-coded, LLM cannot override)

- **Per-trade cap:** worst-case loss ≤ $2,000 (2% of the $100k account); position size
  is derived from this cap, never from conviction.
- **Portfolio cap:** total committed worst-case risk ≤ $10,000 (10%).
- **Daily circuit breaker:** day P&L ≤ −$3,000 halts all new entries until tomorrow.
- **Concurrency cap:** at most 6 open spreads, at most 2 new per cycle.
- **Mechanical exits:** buy back at 50% of credit, stop out at 2× credit, force-close
  anything reaching expiration day. All entries are defined-risk — assignment risk is
  capped by the long leg by construction.

## Alpaca infrastructure

- **Trading API (`alpaca-py`):** account state, market clock, order reconciliation, and
  atomic **multi-leg MLEG limit orders** for both entry (negative limit = credit) and
  exit — legs can never be filled one-sided.
- **Market Data API:** option chain snapshots with Greeks/IV, latest option quotes for
  mark-to-market exit checks, stock trades, and Benzinga news.
- **Alpaca CLI (`alpaca-cli`):** the agent shells out every cycle for account and
  position snapshots journaled alongside its own state — operator-visible ground truth,
  and the same commands a human uses to audit it mid-run.
- **Paper environment:** the agent runs one decision cycle every 30 minutes during
  market hours (Windows scheduled task), fully unattended; an append-only JSONL journal
  records every observation, LLM rationale, order, and realized P&L.
