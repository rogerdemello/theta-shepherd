"""Decision sanitation and unanimity — the pure logic around the LLM calls."""

from theta_shepherd.committee import _is_unanimous
from theta_shepherd.config import settings
from theta_shepherd.llm import sanitize_approvals


def test_sanitize_drops_invalid_indices():
    decision = {"approved": [{"index": 0}, {"index": 7}, {"index": "x"}, {}]}
    out = sanitize_approvals(decision, n_candidates=2)
    assert [a["index"] for a in out["approved"]] == [0]


def test_sanitize_clamps_size_factor():
    decision = {"approved": [{"index": 0, "size_factor": 3.0},
                             {"index": 1, "size_factor": 0.01}]}
    out = sanitize_approvals(decision, n_candidates=2)
    factors = [a["size_factor"] for a in out["approved"]]
    assert factors == [1.0, 0.25]


def test_sanitize_enforces_max_new_trades():
    decision = {"approved": [{"index": i} for i in range(10)]}
    out = sanitize_approvals(decision, n_candidates=10)
    assert len(out["approved"]) <= settings.max_new_trades_per_run


def vote(index, verdict):
    return {"index": index, "vote": verdict, "reason": "-"}


def test_unanimous_requires_all_three_approvals():
    opinions = {
        "macro_analyst": {"votes": [vote(0, "approve"), vote(1, "reject")]},
        "vol_trader": {"votes": [vote(0, "approve"), vote(1, "approve")]},
        "risk_officer": {"votes": [vote(0, "approve"), vote(1, "approve")]},
    }
    assert _is_unanimous(opinions, 0)
    assert not _is_unanimous(opinions, 1)


def test_missing_vote_is_not_unanimous():
    opinions = {
        "macro_analyst": {"votes": [vote(0, "approve")]},
        "vol_trader": {"votes": []},  # never voted on 0
        "risk_officer": {"votes": [vote(0, "approve")]},
    }
    assert not _is_unanimous(opinions, 0)


def test_malformed_persona_output_is_not_unanimous():
    opinions = {
        "macro_analyst": {"votes": [vote(0, "approve")]},
        "vol_trader": {"_error": "unparseable"},
        "risk_officer": {"votes": [vote(0, "approve")]},
    }
    assert not _is_unanimous(opinions, 0)
