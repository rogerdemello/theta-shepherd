"""Azure OpenAI gatekeeper: reviews quantitatively pre-screened spread
candidates against market context and news, and decides which to trade.

The LLM can only select from candidates the strategy engine produced and can
only reduce size — hard risk gates in risk.py always run after it.
"""

import json

from openai import AzureOpenAI

from .config import settings
from .journal import log_event

SYSTEM_PROMPT = """You are the risk-aware gatekeeper of an autonomous options
premium-selling agent trading an Alpaca PAPER account in a one-week competition.
The engine sells defined-risk credit spreads (1-7 DTE, ~0.12-0.25 short delta)
on liquid ETFs and exits at 50% profit or a 2x-credit stop.

You receive: account state, current open spreads, ranked spread candidates
(with delta, credit, POP, EV), and recent headlines.

Your job:
1. Veto candidates that look dangerous given the news/context (e.g. selling
   call spreads into a strong rally, put spreads hours before a major macro
   release like CPI/NFP/FOMC, or on days with unusually elevated risk).
2. Prefer diversification across underlyings/sides; approving a put spread and
   a call spread on the same underlying/expiry forms an iron condor, which is
   fine when the market looks range-bound.
3. Approve at most {max_new} new trades this run. Approving zero is a
   perfectly good decision — capital preservation wins a one-week P&L contest
   more often than overtrading.

Respond ONLY with JSON:
{{"approved": [{{"index": <candidate index>, "confidence": 0-1,
   "size_factor": 0.25-1.0, "rationale": "<one sentence>"}}],
  "market_view": "<2-3 sentence assessment>"}}"""


class Gatekeeper:
    def __init__(self) -> None:
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
        )

    def decide(self, account: dict, open_spreads: list[dict], candidates: list[dict],
               headlines: list[str]) -> dict:
        user_payload = json.dumps({
            "account": account,
            "open_spreads": open_spreads,
            "candidates": [{"index": i, **c} for i, c in enumerate(candidates)],
            "recent_headlines": headlines,
        }, indent=2)

        response = self.client.chat.completions.create(
            model=settings.azure_deployment,
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(max_new=settings.max_new_trades_per_run)},
                {"role": "user", "content": user_payload},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            decision = {"approved": [], "market_view": f"unparseable LLM output: {raw[:200]}"}

        approved = []
        for a in decision.get("approved", []):
            idx = a.get("index")
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                a["size_factor"] = min(1.0, max(0.25, float(a.get("size_factor", 1.0))))
                approved.append(a)
        decision["approved"] = approved[: settings.max_new_trades_per_run]

        log_event("llm_decision", {"decision": decision})
        return decision
