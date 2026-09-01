import pytest

from theta_shepherd.config import settings
from theta_shepherd.strategy import SpreadCandidate, _pair_spreads

from conftest import make_candidate, make_quote


def test_candidate_math():
    c = make_candidate(credit=1.0, width=5.0, delta=-0.20)
    assert c.max_loss == 400.0                       # (5 - 1) * 100
    assert c.pop == 0.8                              # 1 - |delta|
    assert c.mid_credit == pytest.approx(1.0)        # 1.15 mid - 0.15 mid
    # EV models the exit policy actually run, not hold-to-expiry: win 50% of
    # the credit, stop at 2x credit (costing one credit, < the 400 max loss).
    #   50*0.8 - 100*0.2 = 20
    assert c.expected_value == pytest.approx(20.0)
    assert c.score == pytest.approx(20.0 / 400.0)


def test_expected_value_turns_negative_past_the_breakeven_pop():
    """Stop at 2x credit means one credit lost per loser: break-even needs
    pop > 2/3, i.e. a short delta under ~0.333."""
    assert make_candidate(credit=1.0, width=5.0, delta=-0.30).expected_value > 0
    assert make_candidate(credit=1.0, width=5.0, delta=-0.34).expected_value < 0


def test_expected_value_caps_the_stop_at_true_max_loss():
    """When one credit exceeds the spread's remaining width, the real loss is
    the width — the stop can't cost more than the position can. EV works off
    mid prices, so this needs quotes with a genuinely rich mid, not
    make_candidate's executable-credit argument."""
    short = make_quote(strike=630.0, bid=3.10, ask=3.30, delta=-0.20)
    long = make_quote(strike=625.0, bid=0.15, ask=0.25, delta=-0.10)
    c = SpreadCandidate(underlying="SPY", kind="put_credit",
                        expiration=short.expiration, short=short, long=long,
                        credit=2.85, width=5.0, underlying_price=643.0)
    assert c.mid_credit == pytest.approx(3.0)
    # loss per lot = min(1x3.0, 5-3.0) = 2.0 -> 150*0.8 - 200*0.2 = 80
    assert c.expected_value == pytest.approx(80.0)


def test_pair_spreads_builds_executable_credit():
    short = make_quote(strike=630.0, bid=1.00, ask=1.10, delta=-0.18)
    long = make_quote(strike=625.0, bid=0.15, ask=0.20, delta=-0.09)
    out = _pair_spreads([short, long], "put_credit", 643.0)
    assert len(out) == 1
    assert out[0].credit == 0.80                     # short bid - long ask
    assert out[0].short.strike == 630.0 and out[0].long.strike == 625.0


def test_pair_spreads_filters_delta_band():
    short = make_quote(strike=630.0, bid=2.00, ask=2.10, delta=-0.40)  # too close
    long = make_quote(strike=625.0, bid=0.15, ask=0.20, delta=-0.20)
    assert _pair_spreads([short, long], "put_credit", 643.0) == []


def test_pair_spreads_filters_thin_credit():
    floor = settings.min_credit_frac * settings.spread_width
    short = make_quote(strike=630.0, bid=floor - 0.05, ask=floor, delta=-0.18)
    long = make_quote(strike=625.0, bid=0.10, ask=0.15, delta=-0.09)
    assert _pair_spreads([short, long], "put_credit", 643.0) == []


def test_pair_spreads_uses_narrower_width_for_iwm():
    assert settings.width_for("IWM") == 3.0 and settings.width_for("SPY") == 5.0
    short = make_quote(underlying="IWM", strike=220.0, bid=0.55, ask=0.60, delta=-0.18)
    long = make_quote(underlying="IWM", strike=217.0, bid=0.08, ask=0.10, delta=-0.09)
    out = _pair_spreads([short, long], "put_credit", 226.0)
    assert len(out) == 1
    assert out[0].width == 3.0
    assert out[0].credit == pytest.approx(0.45)   # exactly the 15%-of-width floor
    assert out[0].max_loss == pytest.approx((3.0 - 0.45) * 100)


def test_pair_spreads_requires_matching_long_strike():
    short = make_quote(strike=630.0, bid=1.00, ask=1.10, delta=-0.18)
    stray = make_quote(strike=620.0, bid=0.10, ask=0.15, delta=-0.05)  # not width away
    assert _pair_spreads([short, stray], "put_credit", 643.0) == []
