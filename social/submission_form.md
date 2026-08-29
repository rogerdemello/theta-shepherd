# lablab.ai submission form — copy-paste drafts

Fill 【】 with final numbers on Sep 4 before submitting (~6 PM IST buffer).

## Project title

Theta Shepherd — the options agent that argues with itself

## Short description (≤ ~200 chars)

An autonomous options premium-selling agent whose 3-persona AI committee debates
every trade, learns from its own journal nightly, and knew to go flat before NFP.
Built on Alpaca's Trading API + MCP + CLI.

## Long description

Theta Shepherd is a fully autonomous options income agent trading defined-risk
credit spreads (iron condors) on SPY, QQQ and IWM in Alpaca's paper environment.

A deterministic quant scout pulls option chains with Greeks from Alpaca's Market
Data API and ranks delta-targeted verticals by expected value. But no single AI
decides: a Trading Committee of three personas — a Macro Analyst, a Vol Trader
(running on an open-source model via Featherless AI), and a Risk Officer — reviews
every candidate in independent model calls, and a Chair synthesizes their votes.
Approving zero trades is an explicitly good outcome. When all three independently
agree on market direction — rare by design — the agent may spend that conviction on
one small directional debit spread (the "satellite sleeve", ≤ $2k risk).

Above every AI sits pure Python it cannot override: a $2k per-trade cap, a risk
ladder that starts at $4k and earns headroom only on green days, a daily loss
circuit breaker, a 5% drawdown kill switch, econ-calendar entry blackouts, and a
hard-coded flatten-all before nonfarm payrolls — which landed two hours before this
hackathon's deadline. The equity curve was frozen flat and green through the
week's biggest event, on purpose, decided on day 0.

Every night the shepherd re-reads its own decision journal and writes concrete
lessons that are injected into the next day's committee prompts — the agent that
traded Wednesday is provably smarter than the one that traded Monday.

Full Alpaca stack: atomic multi-leg MLEG orders on the Trading API, Greeks/news
from Market Data, journaled alpaca-cli snapshots every cycle, and the official
Alpaca MCP server as the human overseer's window ("how is the flock doing?" —
answered by Claude against the live account). Append-only JSONL audit journal,
69 pytest tests, static dashboard generated from the journal, MIT licensed.

Results: 【N trades, win rate, P&L, max drawdown】.

## Technology & category tags

Alpaca Trading API · Alpaca MCP Server · Alpaca CLI · Options Trading ·
Azure OpenAI (GPT-4o) · Featherless AI · Python · Multi-Agent / AI Committee ·
Autonomous Agent

## Links & assets

- Public GitHub repo: https://github.com/rogerdemello/theta-shepherd
- Demo URL: https://rogerdemello.github.io/theta-shepherd/
- Alpaca paper account ID: PA31OBPWA7MW
- Cover image: docs/cover.png (1280×720)
- Video: 【upload — script in presentation/video_script.md】
- Slides: 【build from presentation/slides.md】
- Social posts (up to 5): 【links after posting — drafts in social/posts.md】
- One-page write-up: WRITEUP.md
