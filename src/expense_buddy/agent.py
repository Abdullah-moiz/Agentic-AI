"""Builds the Expense Buddy agent: a model + tools + a system prompt."""
import os

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver

from expense_buddy import tools

SYSTEM_PROMPT = """You are Expense Buddy, a friendly assistant that tracks the user's expenses.
Today is {weekday}, {today}. The home currency is PKR.

Rules:
- To save spending, call add_expense once per expense. "1200 on lunch and 300 on uber" means two calls.
- Convert relative dates ("yesterday", "last Friday") to YYYY-MM-DD using today's date above.
- If an amount is missing or unclear, ask the user instead of guessing.
- Use get_summary for totals and "how much did I spend" questions.
- Use list_expenses to look up individual entries.
- Before deleting, find the expense id with list_expenses. Never guess an id.
- If a tool returns an error, explain it to the user in simple words.
- If the question has nothing to do with expenses, just answer it without using tools.
- Keep replies short. Show money like "PKR 1,200".
"""


def build_agent(model=None):
    """Create the agent.

    `model` can be a ready-made chat model object (tests pass a fake one) or a
    "provider:model" string. If omitted we read the MODEL env variable, so
    switching models never needs a code change.
    """
    if model is None:
        model = os.environ.get("MODEL", "groq:openai/gpt-oss-120b")
    if isinstance(model, str):
        # temperature=0 keeps the model predictable when picking tools.
        model = init_chat_model(model, temperature=0)

    today = tools._today()
    return create_agent(
        model,
        tools=tools.ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT.format(weekday=today.strftime("%A"), today=today.isoformat()),
        middleware=[
            # Deleting is destructive, so the code (not the prompt) pauses the run
            # and waits for a human to approve or reject.
            HumanInTheLoopMiddleware(
                interrupt_on={"delete_expense": {"allowed_decisions": ["approve", "reject"]}}
            )
        ],
        # A checkpointer saves state per thread_id; it's required for pausing
        # and also gives the chat its memory.
        checkpointer=InMemorySaver(),
    )
