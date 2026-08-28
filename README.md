# 🐑 Theta Shepherd

An autonomous options premium-selling agent for the **Alpaca AI Trading Agents Hackathon**
(lablab.ai × Alpaca, Aug 28 – Sep 4 2026).

Theta Shepherd herds a flock of defined-risk credit spreads on liquid ETFs (SPY, QQQ):
a quantitative engine scouts delta-targeted verticals, an **Azure OpenAI** gatekeeper
approves or vetoes them against live news and market context, and **hard-coded risk
gates** — which the LLM can never override — make the final call before any order
reaches Alpaca's paper Trading API.

## Architecture

```
       ┌─────────────────────────────────────────────────────────┐
       │                    run_agent.py (cycle)                 │
       └─────────────────────────────────────────────────────────┘
   1. reconcile      orders vs. broker state        (Trading API)
   2. manage exits   50% profit / 2x stop / expiry  (Options data + MLEG orders)
   3. scout          delta-targeted credit spreads  (Option chains + Greeks)
   4. LLM gate       Azure OpenAI approves/vetoes   (news + account context)
   5. risk gate      hard limits, can only veto     (pure Python, no LLM)
   6. execute        atomic multi-leg MLEG orders   (Trading API)
   7. journal        every decision → JSONL         (audit trail)
       + alpaca-cli account/positions snapshots each cycle
```

| Module | Role |
|---|---|
| `theta_shepherd/strategy.py` | Builds 1–7 DTE vertical credit spreads, short strike at 0.12–0.25 delta, ranks by EV per dollar of risk |
| `theta_shepherd/llm.py` | Azure OpenAI gatekeeper — selects/vetoes/sizes candidates, can approve zero |
| `theta_shepherd/risk.py` | Hard gates: per-trade risk cap, portfolio risk cap, daily loss limit, max open spreads |
| `theta_shepherd/execution.py` | Atomic MLEG limit orders (negative limit = credit) via `alpaca-py` |
| `theta_shepherd/market.py` | Option chains with Greeks/IV, quotes, Benzinga news via Market Data API |
| `theta_shepherd/cli_ops.py` | `alpaca-cli` account & positions snapshots journaled every cycle |
| `theta_shepherd/journal.py` | Append-only JSONL decision journal + open-spread state |

## Setup

```powershell
# 1. Python deps (Python 3.12+)
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

# 2. Alpaca CLI (needs Python 3.14 — uv handles it)
uv tool install alpaca-cli --python 3.14

# 3. Credentials
copy .env.example .env      # then fill in Alpaca + Azure OpenAI keys
```

**Alpaca account:** create a paper account, set the starting balance to **$100,000**
(hackathon requirement: a brand-new account for the final submission), and make sure
options trading is enabled at **Level 3** (needed for spreads) in the paper account
settings. Generate API keys from the dashboard.

The `alpaca-cli` reads the same keys — run `alpaca-cli config verify` once to confirm.

## Running

```powershell
.\.venv\Scripts\python.exe run_agent.py --scout    # dry run: show ranked candidates
.\.venv\Scripts\python.exe run_agent.py            # one full decision cycle
.\.venv\Scripts\python.exe run_agent.py --loop     # continuous, one cycle / 30 min
```

To run unattended on Windows, register a scheduled task that fires during US
market hours (9:30–16:00 ET):

```powershell
schtasks /Create /TN "ThetaShepherd" /SC MINUTE /MO 30 `
  /TR "\"E:\Alapaca hackathon\.venv\Scripts\python.exe\" \"E:\Alapaca hackathon\run_agent.py\"" `
  /ST 19:00
```

(The agent checks Alpaca's market clock itself and no-ops when closed.)

## Strategy in one paragraph

Sell out-of-the-money vertical credit spreads (put side and call side; both sides on
one expiry form an iron condor) on SPY/QQQ at 1–7 days to expiry, short strike in the
0.12–0.25 delta band, $5 wide, only when the credit is ≥ 15% of width. Exit at 50% of
max profit, stop out if the spread doubles against us, and never hold to same-day
expiration. The LLM decides *whether* and *which* — the risk gates decide *how much*
and *whether it's allowed at all*.

## Journal

Every cycle appends structured events (`llm_decision`, `order_submitted`,
`spread_closed`, `risk_veto`, …) to `journal/YYYY-MM-DD.jsonl` — the full audit
trail of what the agent saw, thought, and did.
