# Theta Shepherd — 7-slide deck

> Build in Google Slides / PowerPoint from this outline. One idea per slide,
> big type, dashboard screenshots as backgrounds. Fill 【】 after Sep 3.

---

## Slide 1 — Title

**🐑 Theta Shepherd**
*An autonomous options premium-selling agent that argues with itself,
learns from its journal, and knows when not to trade.*

Alpaca AI Trading Agents Hackathon · lablab.ai × Alpaca
Paper account PA31OBPWA7MW · github.com/rogerdemello/theta-shepherd

---

## Slide 2 — The strategy (one sentence each)

- **Sell** defined-risk credit spreads on SPY/QQQ — 1–7 DTE, short strike at
  0.12–0.25 delta, $5 wide, credit ≥ 15% of width
- **Exit** mechanically: +50% profit target, 2× credit stop, never hold to expiry day
- **Edge** isn't the spread — it's discipline: what the agent *refuses* to do
- Satellite sleeve: one ≤$2k directional debit spread, only on unanimous AI conviction

---

## Slide 3 — Architecture (mermaid diagram from README as image)

Scout (chains + Greeks, EV-ranked) → **AI Trading Committee** → hard risk
gates (pure Python, veto-only) → atomic MLEG orders → journal → nightly
retrospective → tomorrow's prompts

Callout: **the LLM can size down or veto — it can never loosen a limit.**

---

## Slide 4 — The Trading Committee (screenshot: real debate card)

- Macro Analyst · Vol Trader · Risk Officer — independent calls, no anchoring
- Chair synthesizes; Risk Officer's veto weighs heaviest; zero trades is a valid ruling
- Every debate journaled + replayable on the dashboard
- Real example on screen: Vol Trader approves SPY put spread → Macro Analyst
  vetoes (ISM release) → no trade

---

## Slide 5 — The shepherd learns (screenshot: lessons.md, two days side by side)

- Nightly retrospective LLM reads the day's full decision journal
- Writes falsifiable lessons ("start put spreads nearer mid — fill needed 2 reprices")
- Lessons injected into the next day's committee prompts
- Monday's mistakes are Tuesday's rules

---

## Slide 6 — Guardrails & the full Alpaca stack

| Guardrail | Alpaca stack |
|---|---|
| $2k per-trade cap | Trading API — atomic MLEG spreads |
| Risk ladder $4k → $10k (green days only) | Market Data — chains, Greeks, news |
| Daily loss circuit breaker · 5% kill switch | CLI — journaled ops + Greeks spot-checks |
| Econ-calendar blackouts · **pre-NFP flatten** | MCP server — human overseer via Claude |

62 pytest tests · append-only JSONL audit trail · MIT

---

## Slide 7 — Results (screenshot: final dashboard, equity curve hero)

- Final P&L: 【+$XXX】 (【X.XX%】 on $100k) · max drawdown 【X%】
- 【N】 spreads traded · 【N】% wins · 【$XXX】 premium collected
- 【N】 committee debates · 【N】 vetoes · 【N】 lessons learned
- **Flat and green before NFP — by design, decided on day 0**

*"The best trade of the week was the one the committee argued itself out of."*
