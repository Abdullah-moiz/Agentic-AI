"""Web API tested with the fake model through FastAPI's test client."""
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from expense_buddy import db
from expense_buddy.web import create_app
from test_agent import make_agent, tool_call


def test_chat_saves_expense_and_panel_shows_it():
    agent = make_agent(
        AIMessage(content="", tool_calls=[tool_call("add_expense", {"amount": 1200, "category": "food", "note": "lunch"}, "c1")]),
        AIMessage(content="Added PKR 1,200 for lunch."),
    )
    client = TestClient(create_app(agent))

    data = client.post("/api/chat", json={"thread_id": "w1", "message": "spent 1200 on lunch"}).json()
    assert data["reply"] == "Added PKR 1,200 for lunch."
    assert any("calling add_expense" in step for step in data["steps"])
    assert data["pending"] == []

    panel = client.get("/api/expenses").json()
    assert panel["recent"][0]["note"] == "lunch"
    assert panel["month"]["total"] == 1200


def test_delete_waits_for_approval_then_deletes():
    saved = db.add_expense(300, "transport", "uber", "2026-10-01")
    agent = make_agent(
        AIMessage(content="", tool_calls=[tool_call("delete_expense", {"expense_id": saved["id"]}, "d1")]),
        AIMessage(content="Deleted."),
    )
    client = TestClient(create_app(agent))

    data = client.post("/api/chat", json={"thread_id": "w2", "message": "delete uber"}).json()
    assert data["pending"][0]["summary"] == "PKR 300 · transport · uber · 2026-10-01"
    assert db.get_expense(saved["id"]) is not None

    data = client.post("/api/resume", json={"thread_id": "w2", "approvals": [True]}).json()
    assert data["reply"] == "Deleted."
    assert db.get_expense(saved["id"]) is None


def test_index_page_is_served():
    client = TestClient(create_app(make_agent()))
    assert "Expense Buddy" in client.get("/").text
