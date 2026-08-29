from theta_shepherd.config import settings
from theta_shepherd.risk import AccountRisk, entry_gates, size_trade

from conftest import make_candidate


def healthy_risk(**overrides) -> AccountRisk:
    base = dict(equity=100_000.0, day_pnl=0.0, open_spreads=0, committed_risk=0.0)
    return AccountRisk(**{**base, **overrides})


def test_size_trade_respects_per_trade_cap():
    c = make_candidate(credit=1.0, width=5.0)  # max_loss 400/lot
    assert size_trade(c) == int(settings.max_risk_per_trade // 400)


def test_size_trade_zero_for_degenerate_spread():
    c = make_candidate(credit=6.0, width=5.0)  # negative max loss = bad data
    assert size_trade(c) == 0


def test_entry_gates_pass_for_healthy_book():
    assert entry_gates(healthy_risk(), make_candidate(), qty=2) == []


def test_entry_gates_veto_zero_qty():
    assert any("size_zero" in v for v in entry_gates(healthy_risk(), make_candidate(), 0))


def test_entry_gates_veto_daily_loss():
    risk = healthy_risk(day_pnl=-settings.daily_loss_limit)
    assert any("daily_loss_limit" in v for v in entry_gates(risk, make_candidate(), 2))


def test_entry_gates_veto_max_spreads():
    risk = healthy_risk(open_spreads=settings.max_open_spreads)
    assert any("max_open_spreads" in v for v in entry_gates(risk, make_candidate(), 2))


def test_entry_gates_veto_ladder_cap():
    # 800 committed + 2 lots x 400 = 1600 > 1000 ladder cap
    risk = healthy_risk(committed_risk=800.0)
    vio = entry_gates(risk, make_candidate(), 2, portfolio_cap=1000.0)
    assert any("portfolio_risk_cap" in v for v in vio)


def test_entry_gates_ladder_cap_never_exceeds_hard_ceiling():
    risk = healthy_risk(committed_risk=settings.max_portfolio_risk)
    vio = entry_gates(risk, make_candidate(), 1, portfolio_cap=10 * settings.max_portfolio_risk)
    assert any("portfolio_risk_cap" in v for v in vio)


def test_entry_gates_veto_thin_credit():
    thin = make_candidate(credit=settings.min_credit_frac * 5.0 - 0.01, width=5.0)
    assert any("min_credit" in v for v in entry_gates(healthy_risk(), thin, 2))
