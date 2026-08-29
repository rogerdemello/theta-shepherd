"""Retro plumbing: journal compaction and lessons recall (no LLM calls)."""

import theta_shepherd.retro as retro
from theta_shepherd.retro import _compact, load_lessons


def test_compact_truncates_long_strings():
    event = {"event": "x", "output": "A" * 1000, "nested": {"blob": "B" * 1000},
             "short": "ok", "num": 3}
    out = _compact(event)
    assert len(out["output"]) == retro.MAX_FIELD_CHARS + 1  # + ellipsis
    assert len(out["nested"]["blob"]) == retro.MAX_FIELD_CHARS + 1
    assert out["short"] == "ok" and out["num"] == 3


def test_load_lessons_returns_recent_sections(tmp_path, monkeypatch):
    f = tmp_path / "lessons.md"
    f.write_text("# Shepherd's lessons\n\nheader\n\n## 2026-08-27\n\nold\n"
                 "\n## 2026-08-28\n\nnewer\n\n## 2026-08-29\n\nnewest\n",
                 encoding="utf-8")
    monkeypatch.setattr(retro, "LESSONS_FILE", f)
    out = load_lessons(max_days=2)
    assert "newest" in out and "newer" in out
    assert "old" not in out


def test_load_lessons_without_file(monkeypatch, tmp_path):
    monkeypatch.setattr(retro, "LESSONS_FILE", tmp_path / "missing.md")
    assert "No lessons" in load_lessons()
