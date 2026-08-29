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

    # Universe: liquid ETFs with penny-wide option markets and daily expirations
    underlyings: list[str] = field(default_factory=lambda: _env_list("UNDERLYINGS", ["SPY", "QQQ"]))

    # Spread construction
    min_dte: int = 1            # avoid same-day gamma risk
    max_dte: int = 7
    short_delta_lo: float = 0.12   # |delta| band for the short strike
    short_delta_hi: float = 0.25
    spread_width: float = 5.0      # dollars between strikes
    min_credit_frac: float = 0.15  # credit must be >= 15% of width

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

    # Exits
    profit_target_frac: float = 0.50   # buy back at 50% of credit received
    stop_loss_mult: float = 2.0        # close if spread value reaches 2x credit
    force_close_dte: int = 0           # close anything expiring today

    # Journal
    journal_dir: Path = PROJECT_ROOT / "journal"


settings = Settings()
