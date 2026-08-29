# Theta Shepherd — 3-minute video script

> Record after Sep 3 flatten. Fill every 【】 with final numbers.
> Screen recording + voiceover; keep cuts fast. Target 2:50.

---

## 0:00–0:20 — The hook (dashboard equity curve, full screen)

**Show:** dashboard equity curve, then slow zoom on the flat final segment.

> "This is a week of autonomous options trading — 【$XXX】 of profit on a
> $100,000 paper account, and not one human decision. But the part I'm
> proudest of is the flat line at the end. On September 3rd, my agent closed
> every position and refused to trade — because it knew the jobs report was
> coming two hours before this competition's deadline. Meet Theta Shepherd."

## 0:20–0:50 — What it does (architecture slide / mermaid diagram)

**Show:** slide 3 (architecture), cursor tracing the flow.

> "Theta Shepherd sells defined-risk options credit spreads on SPY and QQQ —
> boring, high-probability theta harvesting. Every 20 minutes a quant engine
> scans Alpaca's option chains, builds delta-targeted spreads, and ranks them
> by expected value. But the quant engine doesn't decide. Neither does one AI.
> A committee does."

## 0:50–1:30 — The committee (dashboard debate viewer)

**Show:** a real committee_debate card — ideally one where personas disagree.

> "Three AI personas review every candidate independently — separate model
> calls, so they can't anchor on each other. A Macro Analyst who worries
> about the economic calendar. A Vol Trader who asks if the premium is worth
> selling. A Risk Officer whose veto weighs heaviest. A Chair reads the
> debate and rules. Here's a real one: the Vol Trader liked this SPY spread —
> the Macro Analyst killed it, because it expired right after the ISM print.
> No trade. Every debate is journaled and replayable. And when all three
> agree on market direction — which is rare by design — the agent is allowed
> one small directional bet: the satellite sleeve, capped at $2,000 of risk."

## 1:30–2:00 — The shepherd learns (lessons.md diff / dashboard lessons panel)

**Show:** lessons.md sections from two different days, side by side.

> "Every night, the agent re-reads its own journal and writes lessons —
> concrete ones, like 'start put spreads closer to mid-price, the fill took
> two reprices.' Those lessons are injected into the committee's prompts the
> next morning. The shepherd that traded on Wednesday is provably smarter
> than the one that traded on Monday."

## 2:00–2:30 — Guardrails + full Alpaca stack (terminal + MCP)

**Show:** terminal: one live cycle running; then Claude answering "how is the
flock doing?" via the Alpaca MCP server; a pytest run (62 green).

> "Above every AI sits pure Python the models can't override: a per-trade
> cap, a risk ladder that starts at four thousand dollars and earns headroom
> only on green days, a daily loss circuit breaker, a drawdown kill switch,
> and a hard-coded flatten before nonfarm payrolls. It's all Alpaca, end to
> end — atomic multi-leg orders on the Trading API, Greeks from Market Data,
> the CLI for journaled ops snapshots, and the MCP server so a human can ask
> Claude how the flock is doing while the agent works."

## 2:30–2:50 — Close (final dashboard + numbers slide)

**Show:** slide 7 (results), then repo URL.

> "Final tally: 【N】 trades, 【N】 committee debates, 【$XXX】 collected,
> 【win rate】, maximum drawdown 【X%】 — and an equity curve that was flat
> and green before the market's biggest event of the week. The best trade of
> the week was the one the committee argued itself out of.
> Theta Shepherd — github.com/rogerdemello/theta-shepherd."

---

**B-roll checklist:** dashboard (light + dark), debate card, lessons diff,
terminal cycle, MCP conversation, pytest run, Alpaca web dashboard equity.
