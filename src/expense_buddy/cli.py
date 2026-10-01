"""Terminal chat loop. Prints every agent step so you can watch it think."""
import uuid

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from expense_buddy import db
from expense_buddy.agent import build_agent

MAX_PREVIEW = 200  # keep tool output readable in the terminal


def _short(text) -> str:
    text = str(text)
    return text if len(text) <= MAX_PREVIEW else text[:MAX_PREVIEW] + "..."


def _stream(agent, payload, config, show):
    """Run the agent, printing each step. Returns (final_reply, interrupts)."""
    reply, interrupts = "", []
    for update in agent.stream(payload, config, stream_mode="updates"):
        if "__interrupt__" in update:
            interrupts.extend(update["__interrupt__"])
            continue
        for node_output in update.values():
            for message in (node_output or {}).get("messages", []):
                if isinstance(message, AIMessage):
                    for call in message.tool_calls:
                        show(f"  → calling {call['name']}({call['args']})")
                    if message.content and not message.tool_calls:
                        reply = message.content
                elif isinstance(message, ToolMessage):
                    show(f"  ← tool returned: {_short(message.content)}")
    return reply, interrupts


def _describe_expense(request: dict) -> str:
    """Turn a pending delete into a human-readable line for the confirmation."""
    expense = db.get_expense(request["args"].get("expense_id"))
    if expense is None:
        return f"expense #{request['args'].get('expense_id')} (not found)"
    return f"PKR {expense['amount']:,.0f} · {expense['category']} · {expense['note']} · {expense['date']}"


def _ask_approval(interrupt, confirm) -> dict:
    """Ask the human about every pending action; return the resume payload."""
    decisions = []
    for request in interrupt.value["action_requests"]:
        answer = confirm(f"Delete this expense? {_describe_expense(request)} [y/N] ")
        if answer.strip().lower() in ("y", "yes"):
            decisions.append({"type": "approve"})
        else:
            decisions.append({"type": "reject", "message": "The user said no. Do not delete it."})
    return {"decisions": decisions}


def run_turn(agent, user_text, thread_id, show=print, confirm=input) -> str:
    """One user message -> final reply, handling approval pauses along the way."""
    config = {"configurable": {"thread_id": thread_id}}
    payload = {"messages": [("user", user_text)]}
    while True:
        reply, interrupts = _stream(agent, payload, config, show)
        if not interrupts:
            return reply
        # Paused for approval: ask the human, then resume the same thread.
        payload = Command(resume=_ask_approval(interrupts[0], confirm))


def main():
    load_dotenv()
    agent = build_agent()
    thread_id = uuid.uuid4().hex  # one id per session = one conversation memory
    print("Expense Buddy ready. Type 'quit' to leave.\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue
        try:
            print(f"\nbuddy> {run_turn(agent, text, thread_id)}\n")
        except Exception as error:  # never let one bad turn kill the chat
            print(f"\nSomething went wrong: {error}\n")
    print("Bye!")
