"""Central configuration. Env vars (via .env) override the defaults below."""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    return [s.strip().upper() for s in raw.split(",")] if raw else default


@dataclass(frozen=True)
class Settings:
    # Alpaca
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    paper: bool = os.getenv("ALPACA_PAPER", "true").lower() != "false"

    # Azure OpenAI
    azure_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    azure_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    # Featherless AI (optional): when a key is present, the Vol Trader persona
    # runs on an open-source model — a committee of different minds, not one
    # model role-playing three seats.
    featherless_api_key: str = os.getenv("FEATHERLESS_API_KEY", "")
    featherless_base_url: str = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
    featherless_model: str = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")

    # Universe: liquid ETFs with penny-wide option markets and daily expirations
    underlyings: list[str] = field(default_factory=lambda: _env_list("UNDERLYINGS", ["SPY", "QQQ", "IWM"]))

    # Spread construction
    min_dte: int = 1            # avoid same-day gamma risk at entry
    max_dte: int = 7
    # Contest horizon: never open anything expiring after the mandatory
    # pre-NFP flatten — premium that outlives the contest is premium we pay
    # to give back when we cross the spread to exit early.
    last_entry_expiry: date = date(2026, 9, 3)
    # Measured EV surface (Sep 1, 1-2 DTE, 96 candidates across SPY/QQQ/IWM),
    # in expected dollars per $10k of risk deployed:
    #   0.10:196  0.15:218  0.20:258  0.25:218  0.30:113  0.35:-76  0.40:-353
    # The peak is 0.20 and the edge is gone by 0.35. The old 0.15-0.30 band
    # spanned the peak but leaned on the weak 0.30 shoulder.
    short_delta_lo: float = 0.15   # |delta| band for the short strike
    short_delta_hi: float = 0.25   # centred on the measured 0.20 peak
    spread_width: float = 5.0      # dollars between strikes
    # Cheaper underlyings need narrower spreads to keep credit/width viable
    spread_width_overrides: dict[str, float] = field(default_factory=lambda: {"IWM": 3.0})
    # At the delta-0.20 peak the credit is only ~10.9% of width, so the old
    # 15% floor filtered out the single most profitable bucket before the
    # committee ever saw it — leaving the agent trading the 0.25-0.30 shoulder.
    min_credit_frac: float = 0.08  # credit must be >= 8% of width
    # Liquidity floor per leg: reject quotes wider than max(abs, frac x mid).
    # The stop-loss rule assumes the short leg can be bought back near its
    # mark; on a 0.05 x 0.60 market it cannot, and "defined risk" becomes
    # theoretical. Deliberately permissive — normal SPY/QQQ/IWM 1-2 DTE
    # markets at 0.20 delta quote a few cents wide and pass untouched.
    max_leg_quote_spread: float = _env_float("MAX_LEG_QUOTE_SPREAD", 0.15)
    max_leg_quote_spread_frac: float = _env_float("MAX_LEG_QUOTE_SPREAD_FRAC", 0.50)
    # A book of one direction only is a directional bet, not premium harvest:
    # don't stack more than this many same-kind spreads without the other side.
    max_same_direction_spreads: int = 2

    def width_for(self, underlying: str) -> float:
        return self.spread_width_overrides.get(underlying.upper(), self.spread_width)

    # Risk gates (dollars, per $100k account) — contest posture: every spread
    # is defined-risk and stop-managed every 20 min, so worst realized loss
    # per spread runs well below max_loss; idle capital earns nothing in a
    # one-week P&L contest.
    max_risk_per_trade: float = _env_float("MAX_RISK_PER_TRADE", 4_000.0)
    max_portfolio_risk: float = _env_float("MAX_PORTFOLIO_RISK", 25_000.0)
    # Risk ladder: portfolio cap starts at the base and earns +step per green
    # day, up to max_portfolio_risk. Risk is a privilege the book pays for.
    # The ladder earns headroom over time, but the contest horizon is shorter
    # than the ramp: at +5k/green day from 10k it reaches the 25k ceiling on
    # Sep 4 — a day after the mandatory flatten kills the book. Risk that
    # arrives after the deadline is risk never deployed, so start where the
    # old schedule would have been by mid-week. The circuit breakers that
    # actually prevent catastrophe (daily loss limit, drawdown kill switch,
    # 2x stops, pre-NFP flatten) are deliberately untouched.
    ladder_base_risk: float = _env_float("LADDER_BASE_RISK", 20_000.0)
    ladder_step: float = _env_float("LADDER_STEP", 5_000.0)
    daily_loss_limit: float = _env_float("DAILY_LOSS_LIMIT", 5_000.0)
    max_open_spreads: int = 12
    max_new_trades_per_run: int = 3
    max_drawdown_frac: float = 0.05   # kill switch: flatten at 5% off peak equity

    # Satellite sleeve: at most ONE directional debit spread, opened only when
    # all three committee personas independently share the same non-neutral
    # directional view. Its risk budget is separate from the condor ladder.
    satellite_max_risk: float = _env_float("SATELLITE_MAX_RISK", 4_000.0)
    satellite_profit_mult: float = 1.5    # sell when value >= 1.5x debit paid
    satellite_stop_mult: float = 0.5      # cut when value <= 0.5x debit paid
    satellite_force_close_dte: int = 1    # never carry into the last day
    satellite_min_dte: int = 2
    satellite_delta_target: float = 0.55  # long leg: near-the-money
    satellite_max_debit_frac: float = 0.60  # debit must be <= 60% of width

    # Exits
    profit_target_frac: float = 0.50   # buy back at 50% of credit received
    stop_loss_mult: float = 2.0        # close if spread value reaches 2x credit
    force_close_dte: int = 0           # expiry-day handling below
    # Expiry-day spreads ride the morning's accelerated decay (stops still
    # checked every cycle) but never the final-hours gamma: hard close from
    # this ET hour onward.
    force_close_et_hour: int = 14

    # Journal
    journal_dir: Path = PROJECT_ROOT / "journal"


settings = Settings()
