"""SQLite storage for expenses. Plain Python, no AI in here.

Keeping the database separate from the agent means we can test it on its own,
and the agent's tools stay thin wrappers around these functions.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    amount     REAL NOT NULL CHECK (amount > 0),
    category   TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    date       TEXT NOT NULL,  -- YYYY-MM-DD, so text sorting == date sorting
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _db_path() -> str:
    # Read at call time (not import time) so tests can point to a temp file.
    return os.environ.get("EXPENSE_DB_PATH", "expenses.db")


@contextmanager
def connect():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row  # lets us turn rows into dicts by column name
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_expense(amount: float, category: str, note: str = "", expense_date: str | None = None) -> dict:
    """Insert one expense and return it as a dict (date defaults to today)."""
    expense_date = expense_date or date.today().isoformat()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
            (amount, category, note, expense_date),
        )
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_expenses(
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return expenses (newest first), optionally filtered."""
    # Build the WHERE clause from fixed fragments; user values only ever go
    # into the params list, never into the SQL string itself.
    clauses, params = [], []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    if search:
        clauses.append("note LIKE ?")
        params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM expenses {where} ORDER BY date DESC, id DESC LIMIT ?"
    with connect() as conn:
        rows = conn.execute(sql, (*params, limit)).fetchall()
    return [dict(r) for r in rows]


def summary_by_category(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Total spending plus a per-category breakdown for a date range."""
    clauses, params = [], []
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT category, SUM(amount) AS total FROM expenses {where} GROUP BY category ORDER BY total DESC"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    by_category = {r["category"]: r["total"] for r in rows}
    return {"total": sum(by_category.values()), "by_category": by_category}


def get_expense(expense_id: int) -> dict | None:
    """Return one expense, or None if the id doesn't exist."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return dict(row) if row else None


def delete_expense(expense_id: int) -> bool:
    """Delete one expense. Returns False if there was nothing to delete."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return cur.rowcount > 0
