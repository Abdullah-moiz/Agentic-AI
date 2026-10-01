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


ALL_TOOLS = [add_expense]
