"""Agent tested with a scripted fake model: no API key, no network."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command

from expense_buddy import db
from expense_buddy.agent import build_agent


class FakeModel(GenericFakeChatModel):
    # create_agent calls bind_tools; the fake has no real tools to bind.
    def bind_tools(self, tools, **kwargs):
        return self


def tool_call(name, args, call_id):
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def make_agent(*messages):
    return build_agent(FakeModel(messages=iter(messages)))


def config(thread="t1"):
    return {"configurable": {"thread_id": thread}}


def ask(agent, text, thread="t1"):
    return agent.invoke({"messages": [("user", text)]}, config(thread))


def test_two_tool_calls_in_one_message_save_two_rows():
    agent = make_agent(
        AIMessage(content="", tool_calls=[
            tool_call("add_expense", {"amount": 1200, "category": "food", "note": "lunch"}, "c1"),
            tool_call("add_expense", {"amount": 300, "category": "transport", "note": "uber"}, "c2"),
        ]),
        AIMessage(content="Saved both."),
    )
    result = ask(agent, "spent 1200 on lunch and 300 on uber")
    assert len(db.list_expenses()) == 2
    assert result["messages"][-1].content == "Saved both."


def _agent_waiting_to_delete():
    saved = db.add_expense(300, "transport", "uber", "2026-10-01")
    agent = make_agent(
        AIMessage(content="", tool_calls=[tool_call("delete_expense", {"expense_id": saved["id"]}, "d1")]),
        AIMessage(content="Done."),
    )
    return agent, saved["id"]


def test_delete_pauses_until_approved():
    agent, expense_id = _agent_waiting_to_delete()
    result = ask(agent, "delete the uber one")

    assert "__interrupt__" in result
    assert db.get_expense(expense_id) is not None  # still there while paused

    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config())
    assert db.get_expense(expense_id) is None


def test_reject_keeps_the_row():
    agent, expense_id = _agent_waiting_to_delete()
    ask(agent, "delete the uber one")

    agent.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "The user said no. Do not delete it."}]}),
        config(),
    )
    assert db.get_expense(expense_id) is not None
