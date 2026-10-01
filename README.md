# Expense Buddy

A small AI agent that keeps track of your spending. You just talk to it:

```
you> spent 1200 on lunch and 300 on uber today
  → calling add_expense({'amount': 1200, 'category': 'food', ...})
  → calling add_expense({'amount': 300, 'category': 'transport', ...})
buddy> Added PKR 1,200 for lunch and PKR 300 for uber.
```

It figures out the amounts, categories and dates, saves them in a local SQLite
file, and can answer questions like "how much did I spend on food this week?"
or "what's my total this month in USD?". My home currency is PKR.

I built this to learn how **tool-calling agents** work, so the code is small
and every step is printed while you chat.

## Quick start

You need Python 3.11+ and a free [Groq API key](https://console.groq.com).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # then paste your GROQ_API_KEY into .env
expense-buddy             # or: python -m expense_buddy
```

Run the tests (no API key or internet needed):

```bash
pytest
```

To switch models, change one line in `.env`, for example
`MODEL=openai:gpt-4o-mini` or `MODEL=anthropic:claude-sonnet-5-5`
(and add that provider's key).

## How it works

An LLM can't touch your database. It can only *ask* for things. The agent
loop is what lets it:

```
 you ──► MODEL ──► "I want to call add_expense(1200, food)"
           ▲                      │
           │                      ▼
           │               our Python runs the tool
           │                      │
           └──── result ◄─────────┘
           
  (repeat until the model has no more tools to call)
           │
           ▼
      final answer ──► you
```

The pieces:

| File | What it does |
| --- | --- |
| `db.py` | Plain SQLite code. No AI. |
| `tools.py` | Five tools the model can call: `add_expense`, `list_expenses`, `get_summary`, `delete_expense`, `convert_currency`. |
| `agent.py` | Glues model + tools + system prompt together with LangChain's `create_agent`. |
| `cli.py` | The terminal chat. Prints each tool call and result. |

A few ideas worth knowing:

- **The model never sees the code**, only each tool's name, description and
  argument schema. So the descriptions are really instructions to the model.
- **Tools never raise.** They return `{"error": "..."}` so the model can read
  the problem and explain it in plain words.
- **Date math lives in Python.** Models are bad at calendars, so
  `get_summary("this_week")` is computed by code, not by the model.
- **Deleting needs your OK.** `HumanInTheLoopMiddleware` pauses the agent
  before `delete_expense` runs and the CLI asks `Delete this expense? [y/N]`.
  A rule in the prompt is only a suggestion the model might ignore. The
  middleware is code, so it's a guarantee.
- **Memory** comes from a checkpointer keyed by a per-session `thread_id`.

## The 7 prompts I tested with a real model

Run against Groq `openai/gpt-oss-120b`, in one session:

1. `spent 1200 on lunch and 300 on uber today` → two `add_expense` calls
2. `how much did I spend on food this week?` → `get_summary(this_week)`
3. `what's my total this month in USD?` → `get_summary` then `convert_currency`
4. `delete the uber one` → `list_expenses`, then `delete_expense` after I said yes
5. `add 500 for groceries yesterday` → saved with yesterday's date
6. `spent abc on lunch` → no tool call, it asked me for a real amount
7. `what's the capital of France?` → answered directly, no tools

## What I learned

- An agent is just a loop: model asks for a tool, code runs it, the result goes back.
- Good tool descriptions matter more than clever code.
- Do the math (dates, totals) in code and let the model do the language.
- Test the agent with a scripted fake model so tests are free and deterministic.
- Safety for risky actions belongs in code (middleware), not in the prompt.
- Models get retired. Groq dropped `llama-3.3-70b-versatile` while I was building
  this, and switching was a one-line env change.

## Next step: RAG as a tool

Add a `search_receipts` tool that looks up notes, receipts or bank statements
in a vector store. The agent would then answer things like "what was that
expensive dinner in March?" by retrieving the right document first. Retrieval
is just another tool in the same loop.
