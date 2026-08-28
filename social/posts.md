# Build-in-public post drafts

Tag targets — X: @lablabai @AlpacaHQ · LinkedIn: lablab.ai, Alpaca

---

## Post 1 — Day 0: Meet Theta Shepherd (post tonight, Aug 28)

**X:**

> Meet Theta Shepherd 🐑 — my agent for the @AlpacaHQ AI Trading Agents Hackathon with @lablabai.
>
> It herds a flock of defined-risk options credit spreads on $QQQ / $SPY:
> 🔍 a quant scout finds delta-targeted spreads
> 🧠 an AI gatekeeper vets them against live news
> 🚧 hard-coded risk gates the AI can never override
>
> First iron condor is already live on the paper account — $202 of premium collected on day 0.
>
> Repo: github.com/rogerdemello/theta-shepherd
> #AITrading #OptionsTrading #BuildInPublic

**LinkedIn:**

> This week I'm competing in the Alpaca AI Trading Agents Hackathon (lablab.ai × Alpaca), and I'd like you to meet Theta Shepherd 🐑
>
> It's a fully autonomous options trading agent with a philosophy: the AI decides *whether* to trade, but hard-coded risk gates decide *whether it's allowed to*.
>
> The architecture:
> • A quantitative scout pulls option chains with Greeks from Alpaca's Market Data API and builds defined-risk credit spreads (0.12–0.25 delta shorts, 1–7 DTE)
> • An Azure OpenAI gatekeeper reviews every candidate against live news and the macro calendar — and is explicitly rewarded for saying "no trade today"
> • Hard risk gates (2% per trade, 10% portfolio cap, daily loss circuit breaker, drawdown kill switch) that the LLM cannot touch
> • Atomic multi-leg orders via Alpaca's Trading API, ops snapshots via their new CLI, every decision journaled to an append-only audit log
>
> Day 0: the agent opened its first QQQ iron condor and then — my favorite part — *declined* to add more risk, citing this week's jobs data. That's the behavior I built it for.
>
> Following along all week as it trades the paper account autonomously. Repo: github.com/rogerdemello/theta-shepherd
>
> @Alpaca @lablab.ai #AITrading #AlgorithmicTrading #AIAgents

---

## Post 2 — Weekend: The Trading Committee (draft after B lands)
(placeholder: 3-persona debate screenshot + "my agent argues with itself so I don't have to")

## Post 3 — Day 2/3: Equity curve + what filled
(placeholder: dashboard screenshot, realized P&L, one lesson from lessons.md)

## Post 4 — Sep 3: The agent knew when NOT to trade
(placeholder: flatten-before-NFP story, blackout journal entry screenshot)

## Post 5 — Sep 4: Results + submission
(placeholder: final equity curve, stats table, link to demo video)
