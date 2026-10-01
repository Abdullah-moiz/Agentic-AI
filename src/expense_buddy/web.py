"""A small web UI for Expense Buddy: FastAPI backend + one static HTML page.

It reuses the exact same agent and streaming logic as the terminal chat,
so there is no second copy of the agent behaviour to keep in sync.
"""
import uuid
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel

from expense_buddy import db, tools
from expense_buddy.agent import build_agent
from expense_buddy.cli import _describe_expense, _stream

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    approvals: list[bool]  # one yes/no per pending action


def create_app(agent=None) -> FastAPI:
    """Build the web app. Tests pass in an agent with a fake model."""
    app = FastAPI(title="Expense Buddy")
    state = {"agent": agent}
    # Per conversation: which tool calls we already showed, and what is awaiting approval.
    threads: dict[str, dict] = {}

    def get_agent():
        if state["agent"] is None:  # built lazily so importing this module stays cheap
            state["agent"] = build_agent()
        return state["agent"]

    def run(thread_id: str, payload) -> dict:
        """Run the agent once and package the result for the browser."""
        thread = threads.setdefault(thread_id, {"seen": set(), "pending": 0})
        steps: list[str] = []
        config = {"configurable": {"thread_id": thread_id}}
        try:
            reply, interrupts = _stream(get_agent(), payload, config, steps.append, thread["seen"])
        except Exception as error:  # report the problem in the chat instead of a 500
            return {"steps": steps, "reply": f"Something went wrong: {error}", "pending": []}

        pending = []
        if interrupts:
            requests = interrupts[0].value["action_requests"]
            thread["pending"] = len(requests)
            pending = [{"name": r["name"], "summary": _describe_expense(r)} for r in requests]
        return {"steps": steps, "reply": reply, "pending": pending}

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        return run(request.thread_id, {"messages": [("user", request.message)]})

    @app.post("/api/resume")
    def resume(request: ResumeRequest):
        decisions = [
            {"type": "approve"} if ok
            else {"type": "reject", "message": "The user said no. Do not delete it."}
            for ok in request.approvals
        ]
        return run(request.thread_id, Command(resume={"decisions": decisions}))

    @app.get("/api/expenses")
    def expenses():
        start, end = tools._period_range("this_month")
        return {
            "recent": db.list_expenses(limit=15),
            "month": db.summary_by_category(start.isoformat(), end.isoformat()),
        }

    @app.get("/api/new-thread")
    def new_thread():
        return {"thread_id": uuid.uuid4().hex}

    return app


def main():
    import uvicorn

    load_dotenv(find_dotenv(usecwd=True))
    print("Expense Buddy UI -> http://127.0.0.1:8000")
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
