"""CLI turn tested with the fake model, capturing what gets printed."""
from langchain_core.messages import AIMessage

from expense_buddy import db
from expense_buddy.cli import run_turn
from test_agent import FakeModel, make_agent, tool_call


def delete_scenario():
    saved = db.add_expense(300, "transport", "uber", "2026-10-01")
    agent = make_agent(
        AIMessage(content="", tool_calls=[tool_call("delete_expense", {"expense_id": saved["id"]}, "d1")]),
        AIMessage(content="Deleted the uber expense."),
    )
    return agent, saved["id"]


def test_delete_with_approval_prints_steps():
    agent, expense_id = delete_scenario()
    lines, prompts = [], []

    def confirm(prompt):
        prompts.append(prompt)
        return "y"

    reply = run_turn(agent, "delete the uber one", "cli1", show=lines.append, confirm=confirm)

    assert prompts == ["Delete this expense? PKR 300 · transport · uber · 2026-10-01 [y/N] "]
    assert any("→ calling delete_expense" in line for line in lines)
    assert any("← tool returned" in line for line in lines)
    assert reply == "Deleted the uber expense."
    assert db.get_expense(expense_id) is None


def test_saying_no_keeps_the_expense():
    agent, expense_id = delete_scenario()
    run_turn(agent, "delete the uber one", "cli2", show=lambda _: None, confirm=lambda _: "n")
    assert db.get_expense(expense_id) is not None
