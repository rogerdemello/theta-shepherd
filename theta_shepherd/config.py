"""Central configuration. Env vars (via .env) override the defaults below."""

import os
from dataclasses import dataclass, field
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
    min_dte: int = 1            # avoid same-day gamma risk
    max_dte: int = 7
    short_delta_lo: float = 0.12   # |delta| band for the short strike
    short_delta_hi: float = 0.25
    spread_width: float = 5.0      # dollars between strikes
    # Cheaper underlyings need narrower spreads to keep credit/width viable
    spread_width_overrides: dict[str, float] = field(default_factory=lambda: {"IWM": 3.0})
    min_credit_frac: float = 0.15  # credit must be >= 15% of width

    def width_for(self, underlying: str) -> float:
        return self.spread_width_overrides.get(underlying.upper(), self.spread_width)

    # Risk gates (dollars, per $100k account)
    max_risk_per_trade: float = _env_float("MAX_RISK_PER_TRADE", 2_000.0)
    max_portfolio_risk: float = _env_float("MAX_PORTFOLIO_RISK", 10_000.0)
    # Risk ladder: portfolio cap starts at the base and earns +step per green
    # day, up to max_portfolio_risk. Risk is a privilege the book pays for.
    ladder_base_risk: float = _env_float("LADDER_BASE_RISK", 4_000.0)
    ladder_step: float = _env_float("LADDER_STEP", 2_000.0)
    daily_loss_limit: float = _env_float("DAILY_LOSS_LIMIT", 3_000.0)
    max_open_spreads: int = 6
    max_new_trades_per_run: int = 2
    max_drawdown_frac: float = 0.05   # kill switch: flatten at 5% off peak equity

    # Satellite sleeve: at most ONE directional debit spread, opened only when
    # all three committee personas independently share the same non-neutral
    # directional view. Its risk budget is separate from the condor ladder.
    satellite_max_risk: float = _env_float("SATELLITE_MAX_RISK", 2_000.0)
    satellite_profit_mult: float = 1.5    # sell when value >= 1.5x debit paid
    satellite_stop_mult: float = 0.5      # cut when value <= 0.5x debit paid
    satellite_force_close_dte: int = 1    # never carry into the last day
    satellite_min_dte: int = 2
    satellite_delta_target: float = 0.55  # long leg: near-the-money
    satellite_max_debit_frac: float = 0.60  # debit must be <= 60% of width

    # Exits
    profit_target_frac: float = 0.50   # buy back at 50% of credit received
    stop_loss_mult: float = 2.0        # close if spread value reaches 2x credit
    force_close_dte: int = 0           # close anything expiring today

    # Journal
    journal_dir: Path = PROJECT_ROOT / "journal"


settings = Settings()
