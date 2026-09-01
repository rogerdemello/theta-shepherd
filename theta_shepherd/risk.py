"""Hard risk gates. These run AFTER the LLM and can only veto — the language
model can never override or loosen them."""

from dataclasses import dataclass

from alpaca.trading.client import TradingClient

from .config import settings
from .resilience import retry
from .strategy import DebitCandidate, SpreadCandidate


@dataclass
class AccountRisk:
    equity: float
    day_pnl: float
    open_spreads: int
    committed_risk: float  # sum of max_loss across open spreads (from state)
    open_kinds: tuple[str, ...] = ()  # "put_credit"/"call_credit" per open spread


def account_risk(trading: TradingClient, state: dict) -> AccountRisk:
    acct = retry(trading.get_account, what="get_account")
    equity = float(acct.equity)
    day_pnl = equity - float(acct.last_equity)
    spreads = state.get("open_spreads", [])
    return AccountRisk(
        equity=equity,
        day_pnl=day_pnl,
        open_spreads=len(spreads),
        committed_risk=sum(s["max_loss_total"] for s in spreads),
        open_kinds=tuple(s.get("kind", "") for s in spreads),
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
    # Directional balance. A book of nothing but put credit spreads is net long
    # delta — a levered bet that the market stops falling, which is not the
    # market-neutral premium harvest this agent claims to run. Diversifying by
    # underlying (QQQ -> IWM) does nothing here; every leg still loses together
    # on a selloff. Require the other side before stacking more of one.
    same = sum(1 for k in risk.open_kinds if k == candidate.kind)
    opposite = "call_credit" if candidate.kind == "put_credit" else "put_credit"
    if (same >= settings.max_same_direction_spreads
            and opposite not in risk.open_kinds):
        violations.append(
            f"directional_balance: {same} {candidate.kind} open and no "
            f"{opposite} to offset"
        )
    return violations


def size_satellite(candidate: DebitCandidate) -> int:
    """Contracts such that the full debit stays inside the sleeve budget."""
    if candidate.max_loss <= 0:
        return 0
    return max(0, int(settings.satellite_max_risk // candidate.max_loss))


def satellite_gates(risk: AccountRisk, candidate: DebitCandidate, qty: int,
                    has_satellite: bool) -> list[str]:
    """Hard gates for the directional sleeve. Its budget is separate from the
    condor ladder, but the daily loss circuit breaker still applies."""
    violations = []
    if qty < 1:
        violations.append("size_zero: debit per lot exceeds the sleeve budget")
    if has_satellite:
        violations.append("satellite_exists: only one satellite at a time")
    if risk.day_pnl <= -settings.daily_loss_limit:
        violations.append(f"daily_loss_limit: day P&L {risk.day_pnl:.0f}")
    if candidate.max_loss * qty > settings.satellite_max_risk:
        violations.append("satellite_risk_cap: total debit above sleeve budget")
    if candidate.debit > settings.satellite_max_debit_frac * candidate.width:
        violations.append("satellite_debit_frac: paying too much of the width")
    return violations
