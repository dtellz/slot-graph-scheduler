from enum import Enum, auto
from typing import Dict, List, Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from mock_client import MockApiClient


class SlotState(Enum):
    """Lifecycle of a single slot."""
    EMPTY = auto()
    FILLING = auto()
    FILLED = auto()
    CHANGING = auto()


class SlotFillingState(BaseModel):
    """
    Aggregate conversation state — travels through LangGraph.
    Only Pydantic-serialisable fields!
    """
    slots: List[str] = Field(default_factory=list)
    slot_values: Dict[str, Optional[str]] = Field(default_factory=dict)
    slot_states: Dict[str, SlotState] = Field(default_factory=dict)
    current_slot_index: int = 0
    awaiting_slot_input: bool = False
    completed: bool = False
    first_message: bool = True

    # ─ runtime fields (not persisted to DB) ─
    user_message: Optional[str] = None   # inbound user text
    response_message: Optional[str] = None   # bot’s reply


class GraphManager:
    """
    Wraps a LangGraph state-machine and handles per-thread persistence.
    """

    def __init__(self) -> None:
        self.api = MockApiClient()
        self.default_slots = ["hospital", "specialty", "doctor", "timeslot"]

        self.graph = self._build_graph()
        self.executor = self.graph.compile()

        # ultra-simple in-memory persistence
        self._threads: Dict[str, Dict] = {}

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
            {
                "process": "process_slot",
                "prompt": "prompt_slot",
                "done": "complete",
                "end": END,
            },
        )

        g.add_conditional_edges(
            "process_slot",
            self._route_after_processing,
            {
                "next": "prompt_slot",
                "done": "complete",
                "retry": "prompt_slot",
            },
        )

        g.add_edge("prompt_slot", END)
        g.add_edge("complete", END)

        return g

    def _init_state(self, state: SlotFillingState) -> SlotFillingState:
        if not state.slots:
            state.slots = self.default_slots
            state.slot_values = {s: None for s in state.slots}
            state.slot_states = {s: SlotState.EMPTY for s in state.slots}
        return state

    def _detect_intent(self, state: SlotFillingState) -> SlotFillingState:
        msg = (state.user_message or "").strip()
        if state.first_message or not msg:
            state.first_message = False
            return state

        if state.awaiting_slot_input:
            return state

        msg_low = msg.lower()

        # user asked to change an earlier slot
        for i, slot in enumerate(state.slots):
            if slot in msg_low and "change" in msg_low and state.slot_values[slot]:
                state.current_slot_index = i
                state.slot_states[slot] = SlotState.CHANGING
                # reset dependents
                for j in range(i + 1, len(state.slots)):
                    dep = state.slots[j]
                    state.slot_values[dep] = None
                    state.slot_states[dep] = SlotState.EMPTY
                return state

        # new appointment after finishing
        if all(state.slot_values.values()):
            if any(w in msg_low for w in ("another", "new", "different")):
                state.slot_values = {s: None for s in state.slots}
                state.slot_states = {s: SlotState.EMPTY for s in state.slots}
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
        current = state.slots[state.current_slot_index]
        options = self._options_for_slot(state, current)
        selection = (state.user_message or "").strip()

        matched = next((o for o in options if o.lower() == selection.lower()), None)
        if not matched:
            state.response_message = (
                f"Sorry, '{selection}' isn't valid for {current}. "
                f"Choices: {', '.join(options)}"
            )
            return state  # will route to retry

        # valid answer
        state.slot_values[current] = matched
        state.slot_states[current] = SlotState.FILLED
        state.awaiting_slot_input = False

        if state.current_slot_index < len(state.slots) - 1:
            state.current_slot_index += 1
            nxt = state.slots[state.current_slot_index]
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
        if state.awaiting_slot_input:
            return "next"
        return "next"

    def _prompt_for_slot(self, state: SlotFillingState) -> SlotFillingState:
        current = state.slots[state.current_slot_index]
        opts = self._options_for_slot(state, current)
        state.awaiting_slot_input = True
        state.response_message = (
            f"Please select a {current}. Options: {', '.join(opts)}"
        )
        return state

    def _complete_appointment(self, state: SlotFillingState) -> SlotFillingState:
        state.response_message = self._format_completion(state)
        return state

    # ───────────────────── helpers ───────────────────────────
    def _options_for_slot(self, state: SlotFillingState, slot: str) -> List[str]:
        if slot == "hospital":
            return self.api.get_hospitals()
        if slot == "specialty":
            hosp = state.slot_values.get("hospital")
            return self.api.get_specialties(hosp) if hosp else []
        if slot == "doctor":
            hosp = state.slot_values.get("hospital")
            spec = state.slot_values.get("specialty")
            return self.api.get_doctors(hosp, spec) if hosp and spec else []
        if slot == "timeslot":
            hosp = state.slot_values.get("hospital")
            spec = state.slot_values.get("specialty")
            doc = state.slot_values.get("doctor")
            return (
                self.api.get_appointment_slots(hosp, spec, doc)
                if hosp and spec and doc
                else []
            )
        return []

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

    # ───────────────────── persistence helpers ───────────────
    def _load_state(self, thread_id: str) -> SlotFillingState:
        raw = self._threads.get(thread_id)
        return SlotFillingState.model_validate(raw) if raw else SlotFillingState()

    def _save_state(self, thread_id: str, state) -> None:
        """Persist the state dict (handles both Pydantic and LangGraph dict)."""
        if hasattr(state, "model_dump"):            # Pydantic model
            self._threads[thread_id] = state.model_dump()
        else:                                       # AddableValuesDict / plain dict
            self._threads[thread_id] = dict(state)

    # ───────────────────── public API ────────────────────────
    def process_message(self, thread_id: str, token: str, message: str) -> str:
        state = self._load_state(thread_id)
        state.user_message = message

        # run LangGraph
        state = self.executor.invoke(state)

        # ensure we persist a serialisable dict
        self._save_state(thread_id, state)

        # pull the reply safely
        reply = (
            state.response_message
            if hasattr(state, "response_message")
            else state.get("response_message")
        )
        return reply or "Sorry, I didn't get that."