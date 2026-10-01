from datetime import date

import pytest

from expense_buddy import tools

FAKE_TODAY = date(2026, 10, 1)  # a Thursday


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own empty database, so tests never affect each other."""
    monkeypatch.setenv("EXPENSE_DB_PATH", str(tmp_path / "test.db"))


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """Freeze 'today' so date math is predictable."""
    monkeypatch.setattr(tools, "_today", lambda: FAKE_TODAY)
