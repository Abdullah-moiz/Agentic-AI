"""Tools tested directly, with no LLM involved."""
import json
from datetime import date

import httpx

from expense_buddy import tools


def call(tool, **kwargs) -> dict:
    return json.loads(tool.invoke(kwargs))


def test_add_and_list():
    call(tools.add_expense, amount=1200, category="food", note="lunch")
    result = call(tools.list_expenses)
    assert result["count"] == 1
    assert result["expenses"][0]["amount"] == 1200
    assert result["expenses"][0]["date"] == "2026-10-01"  # defaulted to fixed today


def test_bad_input_returns_error_instead_of_raising():
    assert "error" in call(tools.add_expense, amount=-5, category="food")
    assert "error" in call(tools.add_expense, amount=5, category="food", date="tomorrow")
    assert "error" in call(tools.list_expenses, start_date="not-a-date")


def test_this_week_summary():
    # Fake today is Thu 2026-10-01, so this week = Mon Sep 28 .. Sun Oct 4.
    call(tools.add_expense, amount=100, category="food", date="2026-09-28")
    call(tools.add_expense, amount=200, category="transport", date="2026-10-01")
    call(tools.add_expense, amount=999, category="food", date="2026-09-27")  # last week
    summary = call(tools.get_summary, period="this_week")
    assert summary["total"] == 300
    assert summary["by_category"] == {"transport": 200, "food": 100}


def test_period_date_math():
    ranges = {p: tools._period_range(p) for p in
              ["today", "yesterday", "this_week", "last_week", "this_month", "last_month"]}
    assert ranges["today"] == (date(2026, 10, 1),) * 2
    assert ranges["yesterday"] == (date(2026, 9, 30),) * 2
    assert ranges["this_week"] == (date(2026, 9, 28), date(2026, 10, 4))
    assert ranges["last_week"] == (date(2026, 9, 21), date(2026, 9, 27))
    assert ranges["this_month"] == (date(2026, 10, 1), date(2026, 10, 31))
    assert ranges["last_month"] == (date(2026, 9, 1), date(2026, 9, 30))


def test_delete_twice():
    saved = call(tools.add_expense, amount=300, category="transport", note="uber")
    expense_id = saved["saved"]["id"]
    assert call(tools.delete_expense, expense_id=expense_id) == {"deleted_id": expense_id}
    assert "error" in call(tools.delete_expense, expense_id=expense_id)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_currency_conversion(monkeypatch):
    fake = FakeResponse({"result": "success", "rates": {"USD": 0.0036}})
    monkeypatch.setattr(httpx, "get", lambda *a, **k: fake)
    result = call(tools.convert_currency, amount=1000, from_currency="pkr", to_currency="usd")
    assert result["converted"] == 3.6


def test_unknown_currency(monkeypatch):
    fake = FakeResponse({"result": "success", "rates": {"USD": 0.0036}})
    monkeypatch.setattr(httpx, "get", lambda *a, **k: fake)
    assert "error" in call(tools.convert_currency, amount=1, from_currency="PKR", to_currency="XXX")


def test_network_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("no internet")

    monkeypatch.setattr(httpx, "get", boom)
    assert "error" in call(tools.convert_currency, amount=1, from_currency="PKR", to_currency="USD")
