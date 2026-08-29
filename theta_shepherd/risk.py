"""Hard risk gates. These run AFTER the LLM and can only veto — the language
model can never override or loosen them."""

from dataclasses import dataclass

from alpaca.trading.client import TradingClient

from .config import settings
from .strategy import SpreadCandidate


@dataclass
class AccountRisk:
    equity: float
    day_pnl: float
    open_spreads: int
    committed_risk: float  # sum of max_loss across open spreads (from state)


def account_risk(trading: TradingClient, state: dict) -> AccountRisk:
    acct = trading.get_account()
    equity = float(acct.equity)
    day_pnl = equity - float(acct.last_equity)
    spreads = state.get("open_spreads", [])
    return AccountRisk(
        equity=equity,
        day_pnl=day_pnl,
        open_spreads=len(spreads),
        committed_risk=sum(s["max_loss_total"] for s in spreads),
    )


def size_trade(candidate: SpreadCandidate) -> int:
    """Contracts such that worst case stays within the per-trade risk cap."""
    if candidate.max_loss <= 0:
        return 0
    return max(0, int(settings.max_risk_per_trade // candidate.max_loss))


def entry_gates(risk: AccountRisk, candidate: SpreadCandidate, qty: int,
                portfolio_cap: float | None = None) -> list[str]:
    """Returns a list of violated gates; empty list means the trade may proceed.

    `portfolio_cap` is the current risk-ladder cap; defaults to the hard
    ceiling when no ladder is in play (e.g. in tests)."""
    cap = min(portfolio_cap, settings.max_portfolio_risk) \
        if portfolio_cap is not None else settings.max_portfolio_risk
    violations = []
    if qty < 1:
        violations.append("size_zero: max_loss per lot exceeds per-trade risk cap")
    if risk.day_pnl <= -settings.daily_loss_limit:
        violations.append(f"daily_loss_limit: day P&L {risk.day_pnl:.0f} <= -{settings.daily_loss_limit:.0f}")
    if risk.open_spreads >= settings.max_open_spreads:
        violations.append(f"max_open_spreads: {risk.open_spreads} already open")
    new_risk = candidate.max_loss * qty
    if risk.committed_risk + new_risk > cap:
        violations.append(
            f"portfolio_risk_cap: committed {risk.committed_risk:.0f} + new {new_risk:.0f}"
            f" > {cap:.0f}"
        )
    if candidate.credit < settings.min_credit_frac * candidate.width:
        violations.append("min_credit: credit below floor at submission time")
    return violations
