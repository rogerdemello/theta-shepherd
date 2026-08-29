"""Order execution: multi-leg (MLEG) credit spread entry and exit via the
Trading API, plus mark-to-market of open spreads for exit management.

MLEG limit price convention (Alpaca): negative = credit received,
positive = debit paid.
"""

import uuid

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

from .config import settings
from .journal import log_event
from .market import MarketData
from .strategy import DebitCandidate, SpreadCandidate


def make_trading_client() -> TradingClient:
    return TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.paper)


def open_spread(trading: TradingClient, candidate: SpreadCandidate, qty: int) -> dict:
    """Submit a credit spread as one atomic MLEG limit order at mid credit."""
    mid_credit = round(candidate.short.mid - candidate.long.mid, 2)
    limit_credit = max(round(candidate.credit, 2), round(mid_credit - 0.02, 2))
    client_order_id = f"shepherd-{uuid.uuid4().hex[:12]}"

    order = LimitOrderRequest(
        qty=qty,
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=-limit_credit,
        client_order_id=client_order_id,
        legs=[
            OptionLegRequest(symbol=candidate.short.symbol, ratio_qty=1, side=OrderSide.SELL),
            OptionLegRequest(symbol=candidate.long.symbol, ratio_qty=1, side=OrderSide.BUY),
        ],
    )
    submitted = trading.submit_order(order)
    record = {
        "client_order_id": client_order_id,
        "order_id": str(submitted.id),
        "qty": qty,
        "limit_credit": limit_credit,
        **candidate.describe(),
        "short_symbol": candidate.short.symbol,
        "long_symbol": candidate.long.symbol,
        "max_loss_total": candidate.max_loss * qty,
    }
    log_event("order_submitted", record)
    return record


def resubmit_spread(trading: TradingClient, spread: dict, new_credit: float) -> dict:
    """Re-place an unfilled entry one step cheaper. Caller must have cancelled
    (and verified dead) the previous order first."""
    client_order_id = f"shepherd-{uuid.uuid4().hex[:12]}"
    order = LimitOrderRequest(
        qty=spread["qty"],
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=-round(new_credit, 2),
        client_order_id=client_order_id,
        legs=[
            OptionLegRequest(symbol=spread["short_symbol"], ratio_qty=1, side=OrderSide.SELL),
            OptionLegRequest(symbol=spread["long_symbol"], ratio_qty=1, side=OrderSide.BUY),
        ],
    )
    submitted = trading.submit_order(order)
    spread.update(order_id=str(submitted.id), client_order_id=client_order_id,
                  limit_credit=round(new_credit, 2))
    log_event("entry_repriced", {"client_order_id": client_order_id,
                                 "new_credit": round(new_credit, 2),
                                 "short_symbol": spread["short_symbol"]})
    return spread


def close_spread(trading: TradingClient, spread: dict, reason: str, debit: float,
                 pad: float = 0.03) -> str:
    """Buy back a spread with a reversed MLEG limit order. `debit` is the
    per-share cost to close (short mid - long mid), padded for fillability."""
    limit_debit = round(max(debit, 0.01) + pad, 2)
    client_order_id = f"shepherd-x-{uuid.uuid4().hex[:10]}"
    order = LimitOrderRequest(
        qty=spread["qty"],
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_debit,
        client_order_id=client_order_id,
        legs=[
            OptionLegRequest(symbol=spread["short_symbol"], ratio_qty=1, side=OrderSide.BUY),
            OptionLegRequest(symbol=spread["long_symbol"], ratio_qty=1, side=OrderSide.SELL),
        ],
    )
    submitted = trading.submit_order(order)
    log_event("close_submitted", {
        "reason": reason,
        "close_order_id": str(submitted.id),
        "limit_debit": limit_debit,
        **{k: spread[k] for k in ("client_order_id", "short_symbol", "long_symbol", "qty")},
    })
    return str(submitted.id)


def open_satellite(trading: TradingClient, candidate: DebitCandidate, qty: int) -> dict:
    """Buy a directional debit spread as one atomic MLEG limit order.
    Positive MLEG limit = debit paid."""
    mid_debit = round(candidate.buy.mid - candidate.sell.mid, 2)
    limit_debit = min(round(candidate.debit, 2), round(mid_debit + 0.02, 2))
    client_order_id = f"shepherd-sat-{uuid.uuid4().hex[:10]}"

    order = LimitOrderRequest(
        qty=qty,
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_debit,
        client_order_id=client_order_id,
        legs=[
            OptionLegRequest(symbol=candidate.buy.symbol, ratio_qty=1, side=OrderSide.BUY),
            OptionLegRequest(symbol=candidate.sell.symbol, ratio_qty=1, side=OrderSide.SELL),
        ],
    )
    submitted = trading.submit_order(order)
    record = {
        "client_order_id": client_order_id,
        "order_id": str(submitted.id),
        "qty": qty,
        "limit_debit": limit_debit,
        **candidate.describe(),
        "long_symbol": candidate.buy.symbol,   # the leg we own
        "short_symbol": candidate.sell.symbol,  # the leg we sold
        "max_loss_total": candidate.max_loss * qty,
    }
    log_event("satellite_submitted", record)
    return record


def close_satellite(trading: TradingClient, spread: dict, reason: str, value: float,
                    pad: float = 0.03) -> str:
    """Sell a debit spread back: reversed legs, negative limit = credit we
    accept. `value` is the current per-share worth (long mid - short mid)."""
    limit_credit = round(max(value - pad, 0.01), 2)
    client_order_id = f"shepherd-satx-{uuid.uuid4().hex[:8]}"
    order = LimitOrderRequest(
        qty=spread["qty"],
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=-limit_credit,
        client_order_id=client_order_id,
        legs=[
            OptionLegRequest(symbol=spread["long_symbol"], ratio_qty=1, side=OrderSide.SELL),
            OptionLegRequest(symbol=spread["short_symbol"], ratio_qty=1, side=OrderSide.BUY),
        ],
    )
    submitted = trading.submit_order(order)
    log_event("satellite_close_submitted", {
        "reason": reason,
        "close_order_id": str(submitted.id),
        "limit_credit": limit_credit,
        **{k: spread[k] for k in ("client_order_id", "long_symbol", "short_symbol", "qty")},
    })
    return str(submitted.id)


def satellite_value(md: MarketData, spread: dict) -> float | None:
    """Current per-share worth of a debit spread (positive), or None."""
    mids = md.option_mids([spread["long_symbol"], spread["short_symbol"]])
    if spread["long_symbol"] not in mids or spread["short_symbol"] not in mids:
        return None
    return mids[spread["long_symbol"]] - mids[spread["short_symbol"]]


def spread_close_cost(md: MarketData, spread: dict) -> float | None:
    """Current per-share cost to close (positive number), or None if unquotable."""
    mids = md.option_mids([spread["short_symbol"], spread["long_symbol"]])
    if spread["short_symbol"] not in mids or spread["long_symbol"] not in mids:
        return None
    return mids[spread["short_symbol"]] - mids[spread["long_symbol"]]
