"""Azure OpenAI plumbing shared by the single gatekeeper (fallback) and the
Trading Committee, plus the gatekeeper itself.

Every LLM in this system can only select from candidates the strategy engine
produced and can only reduce size — hard risk gates in risk.py always run
after it.
"""

import json

from openai import AzureOpenAI

from .config import settings
from .journal import log_event


def azure_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=settings.azure_endpoint,
        api_key=settings.azure_api_key,
        api_version=settings.azure_api_version,
    )


def featherless_client():
    """OpenAI-compatible client for Featherless AI (open-source models)."""
    from openai import OpenAI
    return OpenAI(base_url=settings.featherless_base_url,
                  api_key=settings.featherless_api_key)


def extract_json(raw: str) -> dict:
    """Parse a JSON object out of model output, tolerating code fences and
    surrounding prose (open-source models sometimes ignore JSON mode)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {"_error": f"unparseable LLM output: {raw[:200]}"}


def chat_json(client, system: str, user_payload: str,
              temperature: float = 0.2, model: str | None = None) -> dict:
    """One JSON chat completion against any OpenAI-compatible client; returns
    a dict even on bad output. Falls back to plain mode for servers that
    reject response_format."""
    kwargs = dict(
        model=model or settings.azure_deployment,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_payload},
        ],
    )
    try:
        response = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs)
    except Exception:
        response = client.chat.completions.create(**kwargs)
    return extract_json(response.choices[0].message.content or "{}")


def sanitize_approvals(decision: dict, n_candidates: int) -> dict:
    """Clamp an LLM decision to the allowed action space: valid candidate
    indices, size_factor in [0.25, 1.0], at most max_new_trades_per_run."""
    approved = []
    for a in decision.get("approved", []):
        idx = a.get("index")
        if isinstance(idx, int) and 0 <= idx < n_candidates:
            a["size_factor"] = min(1.0, max(0.25, float(a.get("size_factor", 1.0))))
            approved.append(a)
    decision["approved"] = approved[: settings.max_new_trades_per_run]
    return decision


SYSTEM_PROMPT = """You are the risk-aware gatekeeper of an autonomous options
premium-selling agent trading an Alpaca PAPER account in a one-week competition.
The engine sells defined-risk credit spreads (1-7 DTE, ~0.15-0.30 short delta)
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
3. Approve at most {max_new} new trades this run. Few sessions remain and
   positions are defined-risk and stop-managed every cycle — an idle book
   cannot win a P&L contest. Approve when conditions are normal; reject only
   when you can name the specific danger.

Respond ONLY with JSON:
{{"approved": [{{"index": <candidate index>, "confidence": 0-1,
   "size_factor": 0.25-1.0, "rationale": "<one sentence>"}}],
  "market_view": "<2-3 sentence assessment>"}}"""


class Gatekeeper:
    """Single-LLM fallback used when the committee is unavailable."""

    def __init__(self) -> None:
        self.client = azure_client()

    def decide(self, account: dict, open_spreads: list[dict], candidates: list[dict],
               headlines: list[str]) -> dict:
        user_payload = json.dumps({
            "account": account,
            "open_spreads": open_spreads,
            "candidates": [{"index": i, **c} for i, c in enumerate(candidates)],
            "recent_headlines": headlines,
        }, indent=2)

        decision = chat_json(
            self.client,
            SYSTEM_PROMPT.format(max_new=settings.max_new_trades_per_run),
            user_payload,
        )
        if "_error" in decision:
            decision = {"approved": [], "market_view": decision["_error"]}
        decision = sanitize_approvals(decision, len(candidates))
        log_event("llm_decision", {"decision": decision})
        return decision
