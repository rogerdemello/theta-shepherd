"""Tolerant JSON extraction and per-persona model routing."""

from types import SimpleNamespace

import theta_shepherd.committee as committee
from theta_shepherd.committee import persona_backend
from theta_shepherd.llm import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_code_fenced():
    raw = 'Sure! Here is the JSON:\n```json\n{"stance": "neutral", "votes": []}\n```\nHope that helps.'
    assert extract_json(raw) == {"stance": "neutral", "votes": []}


def test_extract_json_with_surrounding_prose():
    raw = 'My analysis follows. {"vote": "reject", "nested": {"x": 2}} — end.'
    assert extract_json(raw) == {"vote": "reject", "nested": {"x": 2}}


def test_extract_json_garbage_flags_error():
    out = extract_json("I refuse to answer in JSON today.")
    assert "_error" in out


def test_persona_backend_defaults_to_azure(monkeypatch):
    monkeypatch.setattr(committee, "settings", SimpleNamespace(
        featherless_api_key="", azure_deployment="gpt-4o"))
    azure = object()
    client, model = persona_backend("vol_trader", azure)
    assert client is azure and model == "gpt-4o"


def test_persona_backend_routes_vol_trader_to_featherless(monkeypatch):
    monkeypatch.setattr(committee, "settings", SimpleNamespace(
        featherless_api_key="fk-test", azure_deployment="gpt-4o",
        featherless_model="Qwen/Qwen2.5-72B-Instruct"))
    import theta_shepherd.llm as llm
    monkeypatch.setattr(llm, "settings", SimpleNamespace(
        featherless_base_url="https://api.featherless.ai/v1",
        featherless_api_key="fk-test"))
    azure = object()
    client, model = persona_backend("vol_trader", azure)
    assert client is not azure
    assert model == "Qwen/Qwen2.5-72B-Instruct"
    # other seats stay on Azure even with the key present
    client2, model2 = persona_backend("macro_analyst", azure)
    assert client2 is azure and model2 == "gpt-4o"
