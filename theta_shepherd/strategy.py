"""Spread construction: delta-targeted vertical credit spreads on liquid ETFs.

The strategy sells out-of-the-money defined-risk verticals (put side, call side,
or both -> synthetic iron condor) and harvests theta over a 1-7 DTE window.
Candidates are ranked by expected value using |short delta| as the probability
of the spread finishing in the money.
"""

from dataclasses import dataclass
from datetime import date

from alpaca.trading.enums import ContractType

from .config import settings
from .market import MarketData, OptionQuote


@dataclass
class SpreadCandidate:
    underlying: str
    kind: str  # "put_credit" | "call_credit"
    expiration: date
    short: OptionQuote
    long: OptionQuote
    credit: float       # executable credit per share (short bid - long ask)
    width: float
    underlying_price: float

    @property
    def mid_credit(self) -> float:
        """Fair-value credit at mid prices (EV uses this; orders use `credit`)."""
        return self.short.mid - self.long.mid

    @property
    def max_loss(self) -> float:
        """Worst case per 1-lot, in dollars."""
        return (self.width - self.credit) * 100

    @property
    def pop(self) -> float:
        """Probability of profit proxy: 1 - |short delta|."""
        return 1 - abs(self.short.delta or 0.5)

    @property
    def expected_value(self) -> float:
        """Per 1-lot at mid prices, in dollars, under the exit policy we
        actually run: take profit at `profit_target_frac` of the credit, stop
        at `stop_loss_mult` x credit.

        This used to model hold-to-expiry with a full-width loss, which the
        agent never takes — it stops out at 2x credit long before that. Every
        candidate scored negative as a result, and ranking was biased toward
        low delta. A stop costs (mult - 1) credits, capped by the true max
        loss in case the stop is wider than the spread itself."""
        c = self.mid_credit
        win = settings.profit_target_frac * c * 100
        loss = min((settings.stop_loss_mult - 1) * c, self.width - c) * 100
        return win * self.pop - loss * (1 - self.pop)

    @property
    def score(self) -> float:
        """EV per dollar of risk — the ranking metric."""
        return self.expected_value / self.max_loss if self.max_loss > 0 else 0.0

    @property
    def otm_pct(self) -> float:
        return abs(self.short.strike - self.underlying_price) / self.underlying_price * 100

    def describe(self) -> dict:
        """Compact dict handed to the LLM gatekeeper and the journal."""
        return {
            "underlying": self.underlying,
            "kind": self.kind,
            "expiration": self.expiration.isoformat(),
            "dte": self.short.dte,
            "short_strike": self.short.strike,
            "long_strike": self.long.strike,
            "short_delta": round(self.short.delta or 0, 3),
            "credit_per_share": round(self.credit, 2),
            "mid_credit_per_share": round(self.mid_credit, 2),
            "width": self.width,
            "max_loss_per_lot": round(self.max_loss, 2),
            "pop": round(self.pop, 3),
            "ev_per_lot": round(self.expected_value, 2),
            "otm_pct": round(self.otm_pct, 2),
            "short_iv": round(self.short.iv or 0, 3),
            "underlying_price": round(self.underlying_price, 2),
        }


def effective_max_dte(today: date | None = None) -> int:
    """Longest DTE we may open: never past the mandatory pre-NFP flatten.
    Goes negative after the contest horizon — callers treat that as 'no
    entries'."""
    today = today or date.today()
    return min(settings.max_dte, (settings.last_entry_expiry - today).days)


@dataclass
class DebitCandidate:
    """Satellite sleeve: a directional vertical debit spread. Bought only on a
    unanimous committee direction; risk is the debit paid, nothing more."""

    underlying: str
    direction: str  # "bullish" | "bearish"
    expiration: date
    buy: OptionQuote    # near-the-money leg we purchase
    sell: OptionQuote   # further-OTM leg we sell to cheapen it
    debit: float        # executable per-share cost (buy ask - sell bid)
    width: float
    underlying_price: float

    @property
    def kind(self) -> str:
        return "satellite_bull" if self.direction == "bullish" else "satellite_bear"

    @property
    def max_loss(self) -> float:
        return self.debit * 100

    @property
    def max_gain(self) -> float:
        return (self.width - self.debit) * 100

    def describe(self) -> dict:
        return {
            "sleeve": "satellite",
            "underlying": self.underlying,
            "kind": self.kind,
            "direction": self.direction,
            "expiration": self.expiration.isoformat(),
            "dte": self.buy.dte,
            "buy_strike": self.buy.strike,
            "sell_strike": self.sell.strike,
            "buy_delta": round(self.buy.delta or 0, 3),
            "debit_per_share": round(self.debit, 2),
            "width": self.width,
            "max_loss_per_lot": round(self.max_loss, 2),
            "max_gain_per_lot": round(self.max_gain, 2),
            "underlying_price": round(self.underlying_price, 2),
        }


def find_satellite_candidate(
    md: MarketData, underlying: str, direction: str
) -> DebitCandidate | None:
    """Best available near-the-money vertical debit spread in the committee's
    direction, or None when nothing passes the cost filter."""
    dte_hi = effective_max_dte()
    if dte_hi < settings.satellite_min_dte:
        return None  # contest horizon too close for a directional hold
    price = md.last_price(underlying)
    width = settings.width_for(underlying)
    if direction == "bullish":
        quotes = md.chain(underlying, ContractType.CALL, price * 0.97, price * 1.08,
                          settings.satellite_min_dte, dte_hi)
    else:
        quotes = md.chain(underlying, ContractType.PUT, price * 0.92, price * 1.03,
                          settings.satellite_min_dte, dte_hi)

    by_key = {(q.expiration, q.strike): q for q in quotes}
    best: DebitCandidate | None = None
    for q in quotes:
        d = q.delta
        if d is None or not (0.40 <= abs(d) <= 0.65):
            continue
        sell_strike = q.strike + width if direction == "bullish" else q.strike - width
        sell = by_key.get((q.expiration, sell_strike))
        if sell is None:
            continue
        debit = q.ask - sell.bid
        if debit <= 0 or debit > settings.satellite_max_debit_frac * width:
            continue
        cand = DebitCandidate(underlying=underlying, direction=direction,
                              expiration=q.expiration, buy=q, sell=sell,
                              debit=debit, width=width, underlying_price=price)
        # Prefer the long leg nearest the delta target; tie-break on cheaper debit.
        key = (abs(abs(d) - settings.satellite_delta_target), debit)
        if best is None or key < (abs(abs(best.buy.delta or 0)
                                      - settings.satellite_delta_target), best.debit):
            best = cand
    return best


def _pair_spreads(
    quotes: list[OptionQuote], kind: str, price: float, width: float | None = None
) -> list[SpreadCandidate]:
    by_key = {(q.expiration, q.strike): q for q in quotes}
    out = []
    for q in quotes:
        w = width if width is not None else settings.width_for(q.underlying)
        d = q.delta
        if d is None or not (settings.short_delta_lo <= abs(d) <= settings.short_delta_hi):
            continue
        long_strike = q.strike - w if kind == "put_credit" else q.strike + w
        lng = by_key.get((q.expiration, long_strike))
        if lng is None:
            continue
        credit = q.bid - lng.ask  # what we can actually collect crossing the spread
        if credit < settings.min_credit_frac * w:
            continue
        out.append(
            SpreadCandidate(
                underlying=q.underlying, kind=kind, expiration=q.expiration,
                short=q, long=lng, credit=credit, width=w,
                underlying_price=price,
            )
        )
    return out


def find_candidates(md: MarketData, top_n: int = 8) -> list[SpreadCandidate]:
    dte_hi = effective_max_dte()
    if dte_hi < settings.min_dte:
        return []  # past the contest horizon — nothing may be opened
    candidates: list[SpreadCandidate] = []
    for sym in settings.underlyings:
        price = md.last_price(sym)
        puts = md.chain(sym, ContractType.PUT, price * 0.85, price, settings.min_dte, dte_hi)
        calls = md.chain(sym, ContractType.CALL, price, price * 1.15, settings.min_dte, dte_hi)
        candidates += _pair_spreads(puts, "put_credit", price)
        candidates += _pair_spreads(calls, "call_credit", price)

    # Never propose a trade that loses money on its own math. The credit floor
    # alone doesn't imply positive EV: break-even needs credit >= |delta| x
    # width, while min_credit_frac only asks for 15% of width.
    candidates = [c for c in candidates if c.expected_value > 0]

    candidates.sort(key=lambda c: c.score, reverse=True)
    # Keep the best candidate per (underlying, kind, expiration) so the LLM
    # sees diverse structures instead of ten neighbouring strikes.
    seen: set[tuple] = set()
    diverse = []
    for c in candidates:
        key = (c.underlying, c.kind, c.expiration)
        if key in seen:
            continue
        seen.add(key)
        diverse.append(c)
    return diverse[:top_n]
