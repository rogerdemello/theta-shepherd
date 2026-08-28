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
        """Per 1-lot at mid prices, in dollars."""
        mid_loss = (self.width - self.mid_credit) * 100
        return self.mid_credit * 100 * self.pop - mid_loss * (1 - self.pop)

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


def _pair_spreads(
    quotes: list[OptionQuote], kind: str, price: float
) -> list[SpreadCandidate]:
    by_key = {(q.expiration, q.strike): q for q in quotes}
    out = []
    for q in quotes:
        d = q.delta
        if d is None or not (settings.short_delta_lo <= abs(d) <= settings.short_delta_hi):
            continue
        long_strike = q.strike - settings.spread_width if kind == "put_credit" else q.strike + settings.spread_width
        lng = by_key.get((q.expiration, long_strike))
        if lng is None:
            continue
        credit = q.bid - lng.ask  # what we can actually collect crossing the spread
        if credit < settings.min_credit_frac * settings.spread_width:
            continue
        out.append(
            SpreadCandidate(
                underlying=q.underlying, kind=kind, expiration=q.expiration,
                short=q, long=lng, credit=credit, width=settings.spread_width,
                underlying_price=price,
            )
        )
    return out


def find_candidates(md: MarketData, top_n: int = 8) -> list[SpreadCandidate]:
    candidates: list[SpreadCandidate] = []
    for sym in settings.underlyings:
        price = md.last_price(sym)
        puts = md.chain(sym, ContractType.PUT, price * 0.85, price, settings.min_dte, settings.max_dte)
        calls = md.chain(sym, ContractType.CALL, price, price * 1.15, settings.min_dte, settings.max_dte)
        candidates += _pair_spreads(puts, "put_credit", price)
        candidates += _pair_spreads(calls, "call_credit", price)

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
