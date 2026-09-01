# Build-in-public post drafts

Tag targets — X: @lablabai @AlpacaHQ · LinkedIn: lablab.ai, Alpaca

> **Numbers check before posting.** Posts 1 and 2 were written on Aug 28–29 and
> quote the risk limits *as they were then* ($2k per trade, $4k→$10k ladder,
> 0.12–0.25 delta, 48/62 tests). If either is still unposted, update it to the
> current configuration below — or post it as the day-0 snapshot it is.
>
> **Current (Sep 1):** SPY/QQQ/IWM · 0.15–0.25 delta · $5 wide ($3 IWM) ·
> $4k per trade · risk ladder → $25k on green days · daily loss breaker $5k ·
> 5% drawdown kill switch · max 12 spreads · satellite ≤$4k · 130 tests.
> Live P&L numbers: `python run_agent.py --stats`.

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

---

## Post 3 — Tue/Wed: The agent found a flaw I'd missed (post with the equity-curve screenshot)

Attach: dashboard equity curve with trade markers + the lessons.md panel.
Numbers below are from session 1 — refresh from `python run_agent.py --stats`
before posting.

**X:**

> Night 2 of my agent trading autonomously in the @AlpacaHQ × @lablabai hackathon: +$506, and the interesting part isn't the number.
>
> Its own nightly retrospective read the day's journal and flagged that the book had drifted to 100% put credit spreads — net long delta, every leg losing together on a selloff. Diversifying QQQ → IWM had done nothing for that.
>
> So the agent now refuses to stack a third same-side spread without the other side on the book.
>
> The AI didn't just trade. It reviewed itself, and I shipped its finding.
>
> 🐑 github.com/rogerdemello/theta-shepherd
> #AITrading #BuildInPublic #OptionsTrading

**LinkedIn:**

> Theta Shepherd 🐑 closed its first full autonomous session at +$506 on a $100k paper account (Alpaca AI Trading Agents Hackathon, with lablab.ai). The number is fine. What happened next is the reason I built it.
>
> Every night the agent re-reads its own decision journal and writes lessons for the next day's committee. Last night's retrospective flagged something I hadn't: the book had become 100% put credit spreads. That's net long delta — every position losing together in a selloff — which is a directional bet, not the market-neutral premium harvest the agent claims to run. Diversifying across QQQ and IWM did nothing about it, because correlation isn't diversification.
>
> Two changes shipped this morning as a result:
> • A directional-balance gate: no more than two same-side spreads without the other side on the book. The gate never blocks the trade that would rebalance.
> • A corrected expected-value model. The old one priced a hold-to-expiry loss the agent never actually takes — it stops out at 2× credit long before that — so every candidate scored negative and the committee was reasoning against uniformly scary numbers. Now it prices the exit policy the agent really runs, and candidates with negative EV are dropped before any model sees them.
>
> The board went from 8 candidates all scoring negative to 5 all positive, with the previously-invisible call spreads taking the top three.
>
> An agent that trades is a script. An agent that audits itself and hands you a diff is starting to be a colleague.
>
> Repo: github.com/rogerdemello/theta-shepherd
> @Alpaca @lablab.ai #AITrading #AIAgents #AlgorithmicTrading

---

## Post 4 — Wed Sep 3 evening: The agent knew when NOT to trade

Attach: dashboard equity curve showing the flat final segment + the
`flatten_all` / `entry_blackout` journal entries.

**X:**

> My trading agent just went completely flat and stopped trading — exactly as designed. 🐑
>
> Nonfarm payrolls prints Thursday 8:30am ET, two hours before the @lablabai × @AlpacaHQ hackathon deadline. A week ago I hard-coded a flatten-all for 3:30pm ET the day before, above every AI in the system.
>
> No model was asked. No model could have overruled it.
>
> The equity curve is frozen 【+$XXX】 green through the biggest event of the week. Knowing when not to trade is the whole strategy.
>
> #AITrading #OptionsTrading #BuildInPublic

**LinkedIn:**

> Theta Shepherd 🐑 stopped trading this afternoon and closed every position. That was the plan from day 0.
>
> Nonfarm payrolls releases Thursday at 8:30am ET — two hours before the Alpaca AI Trading Agents Hackathon deadline. Short options through a tier-1 macro print is how a good week becomes a bad one in ninety seconds. So the very first commit of this project contained a hard-coded flatten-all at 3:30pm ET on Sep 3, sitting above the entire AI stack: the three-persona committee, the chair, the scout. None of them were consulted. None of them could have overridden it.
>
> The week's other refusals were smaller but the same idea: econ-calendar entry blackouts before ISM and ADP, 【N】 hard risk-gate vetoes, and 【N】 cycles where the committee argued itself into no trade at all.
>
> Final result 【+$XXX】 (【X.XX%】), max drawdown 【X.XX%】, 【N】 spreads closed at a 【N】% win rate — and a flat, green equity curve through the event that decided everyone else's week.
>
> The best trade of the week was the one the committee argued itself out of.
>
> Repo: github.com/rogerdemello/theta-shepherd · Live dashboard: rogerdemello.github.io/theta-shepherd
> @Alpaca @lablab.ai #AITrading #AIAgents #RiskManagement

---

## Post 5 — Thu Sep 4: Results + submission

Attach: final dashboard screenshot (equity curve hero) + demo video link.

**X:**

> Submitted 🐑 Theta Shepherd to the @AlpacaHQ × @lablabai AI Trading Agents Hackathon.
>
> One week, fully autonomous, zero human trade approvals:
> 📈 【+$XXX】 (【X.XX%】) · max drawdown 【X.XX%】
> 🎯 【N】 spreads closed, 【N】% wins, 【$X,XXX】 premium collected
> 🧠 【N】 committee debates · 【N】 no-trade rulings
> 🚧 【N】 hard risk-gate vetoes the AI couldn't override
> 😴 flat and green before NFP, by design
>
> Demo: rogerdemello.github.io/theta-shepherd
> Code (MIT): github.com/rogerdemello/theta-shepherd
> Video: 【link】
>
> #AITrading #AIAgents #OptionsTrading #BuildInPublic

**LinkedIn:**

> Theta Shepherd 🐑 is submitted. One week of fully autonomous options trading on an Alpaca paper account, with zero human trade approvals — my entry in the Alpaca AI Trading Agents Hackathon with lablab.ai.
>
> The result: 【+$XXX】 (【X.XX%】 on $100k), 【N】 spreads closed at a 【N】% win rate, 【$X,XXX】 of premium collected, 【X.XX%】 maximum drawdown — and a flat equity curve through Thursday's jobs report, because the agent was hard-coded to refuse that risk.
>
> What I'd want a judge (or a colleague) to look at:
> • A three-persona AI committee — Macro Analyst, Vol Trader, Risk Officer — reviewing every candidate in independent model calls so they can't anchor on each other, with a Chair that rules. 【N】 debates, all journaled and replayable on the dashboard.
> • Hard risk gates in plain Python that no model can loosen: per-trade cap, a risk ladder that earns headroom only on green days, directional balance, daily loss breaker, drawdown kill switch, econ-calendar blackouts, pre-NFP flatten.
> • A nightly retrospective that reads the day's journal and rewrites the next day's prompts — and which caught a real strategy flaw in my book before I did.
> • The unglamorous half: 130 tests, a 9-point preflight, a self-healing watchdog, atomic state, and cancel-confirmation logic — because an agent that trades unattended is only as good as its behaviour at 1am when an API call fails.
>
> Everything is MIT licensed and the full decision journal is in the repo. If you build agents that touch real systems, the interesting engineering isn't the prompt — it's what happens when something breaks and nobody's watching.
>
> Demo: rogerdemello.github.io/theta-shepherd
> Repo: github.com/rogerdemello/theta-shepherd
> Video: 【link】
>
> @Alpaca @lablab.ai #AITrading #AIAgents #AlgorithmicTrading #BuildInPublic
