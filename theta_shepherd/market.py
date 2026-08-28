"""Market data access: underlying prices, option chains with Greeks, news."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from alpaca.data.historical.news import NewsClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import (
    NewsRequest,
    OptionChainRequest,
    OptionLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.trading.enums import ContractType

from .config import settings

_OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


@dataclass
class OptionQuote:
    """A single option contract snapshot, flattened for strategy use."""

    symbol: str
    underlying: str
    expiration: date
    contract_type: str  # "call" | "put"
    strike: float
    bid: float
    ask: float
    delta: float | None
    theta: float | None
    iv: float | None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def dte(self) -> int:
        return (self.expiration - date.today()).days


def parse_occ(symbol: str) -> tuple[str, date, str, float]:
    """SPY250903P00640000 -> ('SPY', 2025-09-03, 'put', 640.0)"""
    m = _OCC_RE.match(symbol)
    if not m:
        raise ValueError(f"Not an OCC option symbol: {symbol}")
    root, ymd, cp, strike = m.groups()
    exp = datetime.strptime(ymd, "%y%m%d").date()
    return root, exp, ("call" if cp == "C" else "put"), int(strike) / 1000


class MarketData:
    def __init__(self) -> None:
        key, secret = settings.alpaca_api_key, settings.alpaca_secret_key
        self.stocks = StockHistoricalDataClient(key, secret)
        self.options = OptionHistoricalDataClient(key, secret)
        self.news = NewsClient(key, secret)

    def last_price(self, symbol: str) -> float:
        trades = self.stocks.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
        return float(trades[symbol].price)

    def chain(
        self,
        underlying: str,
        contract_type: ContractType,
        strike_lo: float,
        strike_hi: float,
        dte_lo: int,
        dte_hi: int,
    ) -> list[OptionQuote]:
        today = date.today()
        req = OptionChainRequest(
            underlying_symbol=underlying,
            type=contract_type,
            strike_price_gte=strike_lo,
            strike_price_lte=strike_hi,
            expiration_date_gte=today + timedelta(days=dte_lo),
            expiration_date_lte=today + timedelta(days=dte_hi),
        )
        snapshots = self.options.get_option_chain(req)

        quotes: list[OptionQuote] = []
        for sym, snap in snapshots.items():
            if snap.latest_quote is None:
                continue
            bid = float(snap.latest_quote.bid_price)
            ask = float(snap.latest_quote.ask_price)
            if bid <= 0 or ask <= 0:
                continue  # illiquid or one-sided market
            root, exp, cp, strike = parse_occ(sym)
            quotes.append(
                OptionQuote(
                    symbol=sym,
                    underlying=root,
                    expiration=exp,
                    contract_type=cp,
                    strike=strike,
                    bid=bid,
                    ask=ask,
                    delta=snap.greeks.delta if snap.greeks else None,
                    theta=snap.greeks.theta if snap.greeks else None,
                    iv=snap.implied_volatility,
                )
            )
        return quotes

    def option_mids(self, symbols: list[str]) -> dict[str, float]:
        """Latest mid price per option symbol (skips one-sided markets)."""
        quotes = self.options.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=symbols))
        mids = {}
        for sym, q in quotes.items():
            bid, ask = float(q.bid_price), float(q.ask_price)
            if ask > 0:
                mids[sym] = (bid + ask) / 2
        return mids

    def recent_headlines(self, symbols: list[str], hours: int = 24, limit: int = 12) -> list[str]:
        req = NewsRequest(
            symbols=",".join(symbols),
            start=datetime.now(timezone.utc) - timedelta(hours=hours),
            limit=limit,
            exclude_contentless=True,
        )
        news = self.news.get_news(req)
        return [f"[{a.created_at:%m-%d %H:%M}] {a.headline}" for a in news.data.get("news", [])]
