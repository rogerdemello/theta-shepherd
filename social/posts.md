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

## Post 2 — Weekend: The Trading Committee (ready — post Sat/Sun with debate screenshot)

Attach: screenshot of the "Committee debates" card on the dashboard (docs/dashboard.html)
showing the three personas + chair verdict from Aug 29.

**X:**

> My trading agent now argues with itself so I don't have to 🐑
>
> Theta Shepherd upgrade for the @AlpacaHQ × @lablabai hackathon: the single AI gatekeeper is now a 3-persona Trading Committee — a Macro Analyst, a Vol Trader and a Risk Officer vote independently, then a Chair rules.
>
> First real debate: the Vol Trader liked a SPY put spread ("POP 0.82, strikes outside the expected move"). The Macro Analyst and Risk Officer both vetoed — jobs week + concentration risk.
>
> Chair's verdict: no trades. Sometimes the best trade is the argument that stops one.
>
> Every debate is journaled and replayable. And each night the shepherd re-reads its own journal and writes lessons that change how the committee argues tomorrow.
>
> #AITrading #BuildInPublic #OptionsTrading

**LinkedIn:**

> Weekend upgrade to Theta Shepherd 🐑 (my entry in the Alpaca AI Trading Agents Hackathon with lablab.ai): I fired the AI gatekeeper and hired a committee.
>
> Instead of one LLM saying yes/no to trades, three personas now review every candidate independently — in separate model calls, so they can't anchor on each other:
> • The Macro Analyst worries about the economic calendar and event-gap risk
> • The Vol Trader asks whether the premium is actually worth selling
> • The Risk Officer watches concentration, correlation and path risk — and their veto weighs heaviest
> A Chair reads all three opinions and issues the final decision. Hard-coded risk gates still sit above everyone; no LLM can override them.
>
> Their first real debate this weekend was exactly what I hoped for. The Vol Trader approved a SPY put credit spread on the numbers (probability of profit 0.82, strikes outside the expected move). The Macro Analyst rejected it — it expires right after the ISM release, into a week that ends with nonfarm payrolls. The Risk Officer rejected it too: the book already holds a QQQ iron condor on the same expiry. The Chair ruled: no new trades.
>
> Two more things shipped this weekend:
> • A nightly retrospective — the agent re-reads its full decision journal after each close and writes concrete lessons ("start put spreads closer to mid-price; the call side filled instantly at 0.22 delta") that are injected into the next day's committee prompts. The shepherd provably learns across the week.
> • A risk ladder — the portfolio risk cap starts at $4k and earns +$2k of headroom per green day, up to $10k. Risk is a privilege the book pays for.
>
> 48 unit tests, every debate journaled, dashboard rendering it all. Markets reopen Monday; the committee will be arguing every 20 minutes.
>
> Repo: github.com/rogerdemello/theta-shepherd
>
> @Alpaca @lablab.ai #AITrading #AIAgents #AlgorithmicTrading

## Post 3 — Day 2/3: Equity curve + what filled
(placeholder: dashboard screenshot, realized P&L, one lesson from lessons.md)

## Post 4 — Sep 3: The agent knew when NOT to trade
(placeholder: flatten-before-NFP story, blackout journal entry screenshot)

## Post 5 — Sep 4: Results + submission
(placeholder: final equity curve, stats table, link to demo video)
