from __future__ import annotations

import asyncio
from enum import Enum, auto

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from mock_client import MockApiClient
from slots import Slot, build_default_slots


class SlotState(Enum):
    EMPTY = auto()
    FILLING = auto()
    FILLED = auto()
    CHANGING = auto()


class SlotFillingState(BaseModel):
    """Aggregate conversation state (serialisable)."""

    slot_order: list[str] = Field(default_factory=list)
    slot_values: dict[str, str | None] = Field(default_factory=dict)
    slot_states: dict[str, SlotState] = Field(default_factory=dict)
    current_slot_index: int = 0
    awaiting_slot_input: bool = False
    completed: bool = False
    first_message: bool = True

    # ─ runtime-only fields (excluded from persistence) ─
    user_message: str | None = None
    response_message: str | None = None

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}


class GraphManager:
    """Wraps a LangGraph state-machine and handles per-thread persistence."""

    def __init__(self) -> None:
        self.api = MockApiClient()
        self.slot_definitions: list[Slot] = build_default_slots(self.api)

        self.graph = self._build_graph()
        self.executor = self.graph.compile()

        # in-memory persistence (thread-safe with an asyncio.Lock)
        self._threads: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # --------------------------------------------------------------------- #
    #  LangGraph construction
    # --------------------------------------------------------------------- #
    def _build_graph(self) -> StateGraph:
        g = StateGraph(SlotFillingState)

        g.add_node("init", self._init_state)
        g.add_node("detect_intent", self._detect_intent)
        g.add_node("prompt_slot", self._prompt_for_slot)
        g.add_node("process_slot", self._process_slot_input)
        g.add_node("complete", self._complete_appointment)

        g.set_entry_point("init")

        g.add_edge("init", "detect_intent")

        g.add_conditional_edges(
            "detect_intent",
            self._route_after_intent,
            {"process": "process_slot", "prompt": "prompt_slot", "done": "complete", "end": END},
        )

        g.add_conditional_edges(
            "process_slot",
            self._route_after_processing,
            {"next": "prompt_slot", "done": "complete", "retry": "prompt_slot"},
        )

        g.add_edge("prompt_slot", END)
        g.add_edge("complete", END)
        return g

    # ------------------------------------------------------------------ #
    #  LangGraph node implementations
    # ------------------------------------------------------------------ #
    def _init_state(self, state: SlotFillingState) -> SlotFillingState:
        if not state.slot_order:
            state.slot_order = [slot.name for slot in self.slot_definitions]
            state.slot_values = {s: None for s in state.slot_order}
            state.slot_states = {s: SlotState.EMPTY for s in state.slot_order}
        return state

    def _detect_intent(self, state: SlotFillingState) -> SlotFillingState:
        msg = (state.user_message or "").strip()
        if state.first_message or not msg:
            state.first_message = False
            return state

        if state.awaiting_slot_input:
            return state

        msg_low = msg.lower()

        # change request
        for i, slot_name in enumerate(state.slot_order):
            if slot_name in msg_low and "change" in msg_low and state.slot_values[slot_name]:
                state.current_slot_index = i
                state.slot_states[slot_name] = SlotState.CHANGING
                # reset dependents
                for j in range(i + 1, len(state.slot_order)):
                    dep = state.slot_order[j]
                    state.slot_values[dep] = None
                    state.slot_states[dep] = SlotState.EMPTY
                return state

        # new appointment after finishing
        if all(state.slot_values.values()) and any(w in msg_low for w in ("another", "new", "different")):
            state.slot_values = {s: None for s in state.slot_order}
            state.slot_states = {s: SlotState.EMPTY for s in state.slot_order}
            state.current_slot_index = 0
            state.completed = False
        return state

    def _route_after_intent(self, state: SlotFillingState) -> str:
        msg = (state.user_message or "").strip()

        if state.first_message or not msg:
            return "prompt"
        if state.awaiting_slot_input:
            return "process"
        if any(st == SlotState.CHANGING for st in state.slot_states.values()):
            return "prompt"
        if all(state.slot_values.values()):
            return "done"
        return "process"

    def _process_slot_input(self, state: SlotFillingState) -> SlotFillingState:
        current = state.slot_order[state.current_slot_index]
        options = self._options_for_slot(state, current)
        selection = (state.user_message or "").strip()

        matched = next((o for o in options if o.lower() == selection.lower()), None)
        if not matched:
            state.response_message = (
                f"Sorry, '{selection}' isn't valid for {current}. "
                f"Choices: {', '.join(options)}"
            )
            return state  # → retry

        # valid answer
        state.slot_values[current] = matched
        state.slot_states[current] = SlotState.FILLED
        state.awaiting_slot_input = False

        if state.current_slot_index < len(state.slot_order) - 1:
            state.current_slot_index += 1
            nxt = state.slot_order[state.current_slot_index]
            nxt_opts = self._options_for_slot(state, nxt)
            state.awaiting_slot_input = True
            state.response_message = (
                f"Great, {matched} selected for {current}. "
                f"Now choose {nxt}: {', '.join(nxt_opts)}"
            )
        else:
            state.completed = True
            state.response_message = self._format_completion(state)
        return state

    def _route_after_processing(self, state: SlotFillingState) -> str:
        if state.completed:
            return "done"
        return "next"

    def _prompt_for_slot(self, state: SlotFillingState) -> SlotFillingState:
        current = state.slot_order[state.current_slot_index]
        opts = self._options_for_slot(state, current)
        state.awaiting_slot_input = True
        state.response_message = f"Please select a {current}. Options: {', '.join(opts)}"
        return state

    def _complete_appointment(self, state: SlotFillingState) -> SlotFillingState:
        state.response_message = self._format_completion(state)
        return state

    # ------------------------------------------------------------------ #
    #  Helper utilities
    # ------------------------------------------------------------------ #
    def _options_for_slot(self, state: SlotFillingState, slot_name: str) -> list[str]:
        slot = next(s for s in self.slot_definitions if s.name == slot_name)
        return slot.options(state.slot_values)

    @staticmethod
    def _format_completion(state: SlotFillingState) -> str:
        s = state.slot_values
        if not all(s.values()):
            return "We still need more information to finalise your appointment."
        return (
            "✅ Your appointment is booked!\n"
            f"• Hospital: {s['hospital']}\n"
            f"• Specialty: {s['specialty']}\n"
            f"• Doctor: {s['doctor']}\n"
            f"• Date/Time: {s['timeslot']}\n\n"
            "Let me know if you’d like to change anything."
        )

    # ------------------------------------------------------------------ #
    #  Persistence helpers (thread-safe)
    # ------------------------------------------------------------------ #
    async def _load_state(self, thread_id: str) -> SlotFillingState:
        async with self._lock:
            raw = self._threads.get(thread_id)
        return SlotFillingState.model_validate(raw) if raw else SlotFillingState()

    async def _save_state(self, thread_id: str, state) -> None:
        serialisable = state.model_dump() if hasattr(state, "model_dump") else dict(state)
        async with self._lock:
            self._threads[thread_id] = serialisable

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    async def process_message(self, thread_id: str, _token: str, message: str) -> str:
        state = await self._load_state(thread_id)
        state.user_message = message

        # run LangGraph off the main event loop to avoid blocking
        state = await asyncio.to_thread(self.executor.invoke, state)

        await self._save_state(thread_id, state)

        reply = getattr(state, "response_message", None) or state.get("response_message")
        return reply or "Sorry, I didn't get that."