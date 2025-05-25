# Medical Appointment Scheduler (Slot-Graph-Scheduler)

A lightweight **FastAPI** backend that books medical appointments through an interactive *dialog slot-filling* flow controlled by a **LangGraph** state‑machine.

---

## ✨ Features

| Capability | Detail |
|------------|--------|
| **Real‑time dialogue** | `/ws` WebSocket endpoint accepts JSON messages and streams responses. |
| **State machine** | `LangGraph` persists the conversation state per `thread_id`, enforcing the slot order *(hospital → specialty → doctor → timeslot)*. |
| **Mock HIS client** | `MockApiClient` simulates hospital/specialty/doctor/slot lookups for local testing. |
| **Pluggable slots** | Slots are defined in `slots.py`; swap in a new list to reuse the engine for any domain. |
| **Change intent** | Users can amend previously filled slots (e.g. “change doctor”). |
| **Stateless scaling ready** | Persisted state is serialisable; swap the in‑memory store for Redis/PostgreSQL to scale. |

---

## 🧠 State Machine Architecture

The conversation flow is controlled by a `LangGraph` state machine that enforces the slot-filling process:

```
init → detect_intent → process_slot → prompt_slot → complete
```

| State Node | Purpose |
|------------|--------|
| `init` | Initializes conversation state with slot definitions |
| `detect_intent` | Analyzes user message to determine intent (new appointment, change slot, etc.) |
| `process_slot` | Validates user input against available options for the current slot |
| `prompt_slot` | Generates prompts asking for input for the current slot |
| `complete` | Finalizes the appointment with all slots filled |

### 🔄 State Transitions

- The state machine handles **conditional routing** based on the current conversation state
- When changing a slot, dependent downstream slots are automatically reset
- Each interaction persists the conversation state using the `thread_id` as the key
- The state persistence is handled thread-safely with an asyncio lock

### 🗣️ Change Intent Handling

The state machine recognizes patterns like "change hospital to Central Hospital" and:

1. Updates the specified slot with the new value
2. Resets all dependent downstream slots
3. Prompts the user to fill the next required slot
4. Maintains conversation context across multiple interactions

---

## 🚀 Quick‑start

### 1  Clone & set up Python

Python >= 3.12 and [uv](https://github.com/astral-sh/uv) >= 0.6.10 are recommended.

```bash
git clone https://github.com/you/slot-graph-scheduler.git
cd slot-graph-scheduler
uv venv .venv
```

Unix:
```bash
source .venv/bin/activate
```

Windows:
```bash
.venv\Scripts\activate
```

### 2  Install dependencies
```bash
# Using uv (recommended)
uv pip install -e .
```

### 3  Run the server
```bash
# Using the module path
uv run src/main.py
```
The API is now live at `ws://localhost:8000/ws`.

### 4  Chat from a different terminal *(optional)*
```bash
uv run scripts/test_client.py
```

---

## 🗣️  WebSocket protocol

*Every* message **to** the server:
```json
{
  "thread_id": "<uuid-v4>",
  "token": "<your-auth-token>",
  "message": "<user text>"
}
```

The server keeps track of each `thread_id` independently, so you may multiplex multiple appointments over one WebSocket connection.

---

## 🧪 Running tests
```bash
uv run pytest tests/
```

---

## 🔧  Customisation

| Task | Where |
|------|-------|
| **Add a new slot (e.g. insurance)** | Append a `Slot` instance in `slots.py`. |
| **Connect real hospital API** | Replace `MockApiClient` with a concrete implementation adhering to the same method signatures. |
| **Persist state externally** | Swap `_threads` dict in `GraphManager` for Redis, PostgreSQL, etc. |
| **AuthZ / AuthN** | Inspect the `token` in `app.py` before forwarding to the graph. |
| **Deploy** | Add a `Dockerfile` and point CMD to `uvicorn src.app:app`. |
