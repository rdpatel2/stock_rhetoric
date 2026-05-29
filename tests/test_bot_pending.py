"""Tests for the bot's pending-updates persistence (crash-safety)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from stock_rhetoric import bot


@pytest.fixture(autouse=True)
def _isolate_pending_dir(tmp_path, monkeypatch):
    pending = tmp_path / "pending_updates"
    monkeypatch.setattr(bot, "_PENDING_DIR", pending)
    return pending


class _FakeUpdate:
    """Minimal duck for what `_persist_update` reads off of an Update."""

    def __init__(self, update_id: int, payload: dict | None = None):
        self.update_id = update_id
        self._payload = payload or {"update_id": update_id, "message": {"text": "AAPL"}}

    def to_json(self) -> str:
        return json.dumps(self._payload)


def test_persist_writes_file(_isolate_pending_dir):
    bot._persist_update(_FakeUpdate(42))
    files = list(_isolate_pending_dir.glob("*.json"))
    assert [p.name for p in files] == ["42.json"]
    assert json.loads(files[0].read_text())["update_id"] == 42


def test_clear_removes_file(_isolate_pending_dir):
    bot._persist_update(_FakeUpdate(7))
    bot._clear_update(7)
    assert list(_isolate_pending_dir.glob("*.json")) == []


def test_clear_missing_file_is_silent(_isolate_pending_dir):
    bot._clear_update(999)  # should not raise


def test_persist_overwrites_same_update_id(_isolate_pending_dir):
    bot._persist_update(_FakeUpdate(1, {"update_id": 1, "v": "a"}))
    bot._persist_update(_FakeUpdate(1, {"update_id": 1, "v": "b"}))
    files = list(_isolate_pending_dir.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["v"] == "b"
