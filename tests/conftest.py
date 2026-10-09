"""Test không ghi vào Google Sheets thật: kho cấu hình là bộ nhớ, làm sạch trước mỗi test."""

import pytest


@pytest.fixture(autouse=True)
def memory_config_store(monkeypatch):
    monkeypatch.setenv("CONFIG_STORE", "memory")
    from macro_app.ui import editor_gate, profile_store

    editor_gate.reset_counters()
    profile_store.store.clear()
    profile_store._rows.clear()
    yield
    profile_store.store.clear()
    profile_store._rows.clear()
