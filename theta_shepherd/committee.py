"""The Trading Committee: three AI personas debate every candidate list, a
Chair synthesizes the final decision.

Macro Analyst, Vol Trader and Risk Officer each review the same evidence in
independent Azure OpenAI calls (no anchoring on each other), then the Chair
reads their votes and issues the decision in the gatekeeper's schema — so
hard risk gates in risk.py still run after it, unchanged.

The full debate is journaled per cycle: this transcript is the audit trail
("why did the agent trade / refuse to trade at 19:42?") and the demo.
"""

import json

from .config import settings
from .journal import log_event
from .llm import azure_client, chat_json, sanitize_approvals
from .retro import load_lessons

_CONTEXT = """The agent sells defined-risk credit spreads (1-7 DTE,
~0.12-0.25 short delta) on liquid ETFs in an Alpaca PAPER account during a
one-week P&L competition, exiting at 50% profit or a 2x-credit stop. You
receive: account state, open spreads, ranked candidates (delta, credit, POP,
EV), recent headlines, the upcoming macro calendar, and lessons the agent
wrote after prior sessions. Capital preservation beats overtrading in a
one-week contest.

Respond ONLY with JSON:
{"stance": "risk_on" | "neutral" | "risk_off",
 "votes": [{"index": <candidate index>, "vote": "approve" | "reject",
            "reason": "<one sentence>"}],
 "view": "<2-3 sentence assessment from your seat>"}
Vote on EVERY candidate index you were given."""

PERSONAS = {
    "macro_analyst": "You are the committee's MACRO ANALYST. You care about "
    "the economic calendar, headline risk, and event-driven gap risk. A credit "
    "spread that expires across a tier-1 release (NFP, CPI, FOMC, ISM) needs a "
    "much better reason to exist. Judge each candidate through that lens.\n\n"
    + _CONTEXT,
    "vol_trader": "You are the committee's VOL TRADER. You care about whether "
    "the premium is worth selling: implied vol vs. likely realized moves, "
    "credit relative to width, POP vs. EV, and whether strikes sit outside "
    "the expected move. Reject thin credit and strikes inside the likely "
    "range. Judge each candidate through that lens.\n\n" + _CONTEXT,
    "risk_officer": "You are the committee's RISK OFFICER. You care about "
    "concentration, correlation and path risk: how much is already committed, "
    "same-underlying/same-expiry stacking, drawdown proximity, and whether "
    "adding risk now could force bad exits later. When in doubt, reject — "
    "your veto protects the book. Judge each candidate through that lens.\n\n"
    + _CONTEXT,
}

CHAIR_PROMPT = """You are the CHAIR of an AI trading committee for an
autonomous options premium-selling agent (Alpaca PAPER account, one-week P&L
competition). Three members — a Macro Analyst, a Vol Trader and a Risk
Officer — have independently reviewed the same candidate credit spreads and
voted. You receive the evidence they saw plus their full opinions.

Synthesize their debate into a decision:
1. Approve a candidate only when the case is strong; weigh a Risk Officer
   rejection heavily. Approving zero trades is a perfectly good outcome.
2. Approve at most {max_new} new trades. You may size down (size_factor) when
   members disagree; you may never size up beyond 1.0.
3. A put spread + call spread on the same underlying/expiry forms an iron
   condor — fine when members see a range-bound market.

Respond ONLY with JSON:
{{"approved": [{{"index": <candidate index>, "confidence": 0-1,
   "size_factor": 0.25-1.0, "rationale": "<one sentence citing the debate>"}}],
  "market_view": "<2-3 sentence synthesis>",
  "debate_summary": "<2-3 sentences: where members agreed/clashed and why the
   decision came out this way>"}}"""


class Committee:
    def __init__(self) -> None:
        self.client = azure_client()

    def decide(self, account: dict, open_spreads: list[dict], candidates: list[dict],
               headlines: list[str]) -> dict:
        evidence = {
            "account": account,
            "open_spreads": open_spreads,
            "candidates": [{"index": i, **c} for i, c in enumerate(candidates)],
            "recent_headlines": headlines,
            "lessons_from_prior_sessions": load_lessons(),
        }
        evidence_json = json.dumps(evidence, indent=2)

        opinions: dict[str, dict] = {}
        for name, prompt in PERSONAS.items():
            opinions[name] = chat_json(self.client, prompt, evidence_json, temperature=0.4)

        chair_payload = json.dumps({**evidence, "committee_opinions": opinions}, indent=2)
        decision = chat_json(
            self.client,
            CHAIR_PROMPT.format(max_new=settings.max_new_trades_per_run),
            chair_payload,
        )
        if "_error" in decision:
            decision = {"approved": [], "market_view": decision["_error"],
                        "debate_summary": "chair output unparseable — no trades"}
        decision = sanitize_approvals(decision, len(candidates))

        for a in decision["approved"]:
            a["unanimous"] = _is_unanimous(opinions, a["index"])

        log_event("committee_debate", {"opinions": opinions, "decision": decision})
        return decision


def _is_unanimous(opinions: dict[str, dict], index: int) -> bool:
    """True when every persona explicitly voted approve on this candidate."""
    for op in opinions.values():
        votes = {v.get("index"): v.get("vote") for v in op.get("votes", [])
                 if isinstance(v, dict)}
        if votes.get(index) != "approve":
            return False
    return True
