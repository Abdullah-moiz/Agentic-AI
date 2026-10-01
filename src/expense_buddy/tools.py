"""The tools the AI agent can call.

The model never sees this code. It only sees each tool's name, description
(the docstring) and argument schema. So those are written for the model.

Every tool returns a JSON string and never raises: if something goes wrong
we return {"error": "..."} so the model can read it and explain it to the user.
"""
import json
from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from expense_buddy import db

Category = Literal[
    "food", "transport", "groceries", "shopping", "bills",
    "entertainment", "health", "education", "other",
]


def _today() -> date:
    # One place to get "today" so tests can patch it with a fixed date.
    return date.today()


def _error(message: str) -> str:
    return json.dumps({"error": message})


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------- add_expense

class AddExpenseInput(BaseModel):
    amount: float = Field(description="Amount spent, in PKR unless the user says otherwise. Must be greater than 0.")
    category: Category = Field(description="Best-fitting category for this expense.")
    note: str = Field(default="", description="Short description, e.g. 'lunch' or 'uber to office'.")
    date: str | None = Field(
        default=None,
        description="Date of the expense as YYYY-MM-DD. Leave empty for today.",
    )


@tool("add_expense", args_schema=AddExpenseInput)
def add_expense(amount: float, category: str, note: str = "", date: str | None = None) -> str:
    """Save ONE expense to the database.
    If the user mentions several expenses, call this tool once for each one.
    """
    if amount <= 0:
        return _error("Amount must be greater than 0.")
    if date is not None and _parse_date(date) is None:
        return _error(f"Invalid date '{date}'. Use the format YYYY-MM-DD, e.g. 2026-10-01.")

    saved = db.add_expense(amount, category, note, date or _today().isoformat())
    return json.dumps({"saved": saved})


# ------------------------------------------------------------- list_expenses

class ListExpensesInput(BaseModel):
    category: Category | None = Field(default=None, description="Only show this category.")
    start_date: str | None = Field(default=None, description="Earliest date, YYYY-MM-DD, inclusive.")
    end_date: str | None = Field(default=None, description="Latest date, YYYY-MM-DD, inclusive.")
    search: str | None = Field(default=None, description="Text to look for inside the note, e.g. 'uber'.")
    limit: int = Field(default=20, description="Maximum number of entries to return.")


@tool("list_expenses", args_schema=ListExpensesInput)
def list_expenses(
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    limit: int = 20,
) -> str:
    """List individual expense entries, each with its id, newest first.
    Use this to look up specific entries, and to find the id before deleting.
    Do NOT use it to calculate totals; use get_summary for that.
    """
    for label, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and _parse_date(value) is None:
            return _error(f"Invalid {label} '{value}'. Use the format YYYY-MM-DD.")

    rows = db.list_expenses(category, start_date, end_date, search, limit)
    return json.dumps({"count": len(rows), "expenses": rows})


# --------------------------------------------------------------- get_summary

Period = Literal["today", "yesterday", "this_week", "last_week", "this_month", "last_month"]


def _period_range(period: str) -> tuple[date, date]:
    """Turn a period name into (start, end) dates. Done in Python because
    models are unreliable at calendar math."""
    today = _today()
    monday = today - timedelta(days=today.weekday())  # weeks start on Monday
    first_of_month = today.replace(day=1)

    if period == "today":
        return today, today
    if period == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    if period == "this_week":
        return monday, monday + timedelta(days=6)
    if period == "last_week":
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if period == "this_month":
        next_month = (first_of_month + timedelta(days=32)).replace(day=1)
        return first_of_month, next_month - timedelta(days=1)
    if period == "last_month":
        last_day = first_of_month - timedelta(days=1)
        return last_day.replace(day=1), last_day
    raise ValueError(period)


class GetSummaryInput(BaseModel):
    period: Period = Field(description="Which time period to total up.")


@tool("get_summary", args_schema=GetSummaryInput)
def get_summary(period: str) -> str:
    """Get the total spent in a period, plus a per-category breakdown (in PKR).
    Use this for any question about totals or 'how much did I spend'.
    """
    try:
        start, end = _period_range(period)
    except ValueError:
        return _error(f"Unknown period '{period}'.")

    summary = db.summary_by_category(start.isoformat(), end.isoformat())
    return json.dumps({"period": period, "start": start.isoformat(), "end": end.isoformat(), **summary})


# ----------------------------------------------------------- delete_expense

class DeleteExpenseInput(BaseModel):
    expense_id: int = Field(description="The id of the expense to delete, taken from list_expenses.")


@tool("delete_expense", args_schema=DeleteExpenseInput)
def delete_expense(expense_id: int) -> str:
    """Permanently delete one expense by id.
    Always call list_expenses first to find the correct id; never guess it.
    """
    if not db.delete_expense(expense_id):
        return _error(f"No expense with id {expense_id}. Use list_expenses to find the right id.")
    return json.dumps({"deleted_id": expense_id})


# --------------------------------------------------------- convert_currency

class ConvertCurrencyInput(BaseModel):
    amount: float = Field(description="Amount to convert.")
    from_currency: str = Field(description="3-letter source currency code, e.g. PKR.")
    to_currency: str = Field(description="3-letter target currency code, e.g. USD.")


@tool("convert_currency", args_schema=ConvertCurrencyInput)
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies using live exchange rates.
    Use it when the user asks for amounts or totals in a currency other than PKR.
    """
    source, target = from_currency.upper(), to_currency.upper()
    try:
        # open.er-api.com is free, needs no key and supports PKR.
        response = httpx.get(f"https://open.er-api.com/v6/latest/{source}", timeout=10)
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return _error("Could not reach the exchange-rate service. Please try again in a moment.")

    if data.get("result") != "success":
        return _error(f"Unknown currency '{source}'.")
    rate = data.get("rates", {}).get(target)
    if rate is None:
        return _error(f"Unknown currency '{target}'.")

    return json.dumps({
        "amount": amount, "from": source, "to": target,
        "rate": rate, "converted": round(amount * rate, 2),
    })


ALL_TOOLS = [add_expense, list_expenses, get_summary, delete_expense, convert_currency]
