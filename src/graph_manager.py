from __future__ import annotations

import asyncio
from enum import Enum, auto

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from src.mock_client import MockApiClient
from src.slots import Slot, build_default_slots


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

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for conversation flow."""
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

    def _init_state(self, state: SlotFillingState) -> SlotFillingState:
        """Initialize the conversation state with slot definitions."""
        if not state.slot_order:
            state.slot_order = [slot.name for slot in self.slot_definitions]
            state.slot_values = {s: None for s in state.slot_order}
            state.slot_states = {s: SlotState.EMPTY for s in state.slot_order}
        return state

    def _detect_intent(self, state: SlotFillingState) -> SlotFillingState:
        """Detect user intent from the message.
        
        Analyzes the user message to determine intent and updates state accordingly.
        """
        msg = (state.user_message or "").strip()
        if state.first_message or not msg:
            state.first_message = False
            return state

        if state.awaiting_slot_input:
            return state

        msg_low = msg.lower()
        
        if "change" in msg_low:
            referenced_slot = None
            slot_index = -1
            
            for i, slot_name in enumerate(state.slot_order):
                # Only consider slots that have been filled
                if state.slot_values[slot_name] is None:
                    continue
                    
                # Check if this slot is mentioned in the change request
                if slot_name in msg_low:
                    referenced_slot = slot_name
                    slot_index = i
                    break
                    
            if referenced_slot is None:
                # No valid slot mentioned
                return state
                
            # Try to extract the new value from the message
            new_value = None
            available_options = self._options_for_slot(state, referenced_slot)
            
            # Look for "to <value>" pattern
            if " to " in msg_low:
                value_part = msg_low.split(" to ", 1)[1].strip()
                
                # Try to match against available options
                for option in available_options:
                    if option.lower() in value_part or value_part in option.lower():
                        new_value = option
                        break
            
            # Set the new value and reset downstream slots
            if new_value:
                # Update the slot with the new value
                state.slot_values[referenced_slot] = new_value
                state.slot_states[referenced_slot] = SlotState.CHANGING
                
                # Reset all downstream/dependent slots
                for j in range(slot_index + 1, len(state.slot_order)):
                    downstream_slot = state.slot_order[j]
                    state.slot_values[downstream_slot] = None
                    state.slot_states[downstream_slot] = SlotState.EMPTY
                
                # Move to the next slot for prompting
                if slot_index < len(state.slot_order) - 1:
                    # Move to the next slot
                    state.current_slot_index = slot_index + 1
                    next_slot = state.slot_order[state.current_slot_index]
                    
                    # Prepare for prompting for the next slot
                    state.awaiting_slot_input = True
                    next_options = self._options_for_slot(state, next_slot)
                    
                    # Set response message to confirm the change and prompt for next slot
                    state.response_message = f"Changed {referenced_slot} to {new_value}. Please select a {next_slot}. Options: {', '.join(next_options)}"
                else:
                    # This was the last slot, just confirm the change
                    state.response_message = f"Changed {referenced_slot} to {new_value}."
                    
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
            
        # If a slot is marked as CHANGING, we need to prompt for the next slot
        # This is crucial for handling "change X to Y" intents
        if any(st == SlotState.CHANGING for st in state.slot_states.values()):
            # Mark that we're awaiting input for the current slot
            state.awaiting_slot_input = True
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
        """Load conversation state for a thread from persistence."""
        async with self._lock:
            raw = self._threads.get(thread_id)
        return SlotFillingState.model_validate(raw) if raw else SlotFillingState()

    async def _save_state(self, thread_id: str, state) -> None:
        """Save conversation state for a thread to persistence."""
        serialisable = state.model_dump() if hasattr(state, "model_dump") else dict(state)
        async with self._lock:
            self._threads[thread_id] = serialisable

    async def process_message(self, thread_id: str, _token: str, message: str) -> str:
        """Process an incoming user message.
        
        Loads state, processes the message through the graph, and saves the updated state.
        """
        state = await self._load_state(thread_id)
        message_lower = message.lower()
        
        if "change" in message_lower and " to " in message_lower:
            change_response = self._handle_change_intent(state, message_lower)
            if change_response:
                await self._save_state(thread_id, state)
                return change_response
        

        state.user_message = message
        state = await asyncio.to_thread(self.executor.invoke, state)
        await self._save_state(thread_id, state)
        reply = getattr(state, "response_message", None) or state.get("response_message")
        return reply or "Sorry, I didn't get that."
        
    def _handle_change_intent(self, state: SlotFillingState, message_lower: str) -> str | None:
        """Handle intent to change a previously filled slot."""

        change_parts = message_lower.split(" to ", 1)
        if len(change_parts) != 2:
            return None
            
        before_to = change_parts[0].strip()
        after_to = change_parts[1].strip()
        

        target_slot = None
        slot_index = -1
        
        for i, slot_name in enumerate(state.slot_order):

            if slot_name.lower() in before_to:
                target_slot = slot_name
                slot_index = i
                break
        
        if not target_slot or state.slot_values.get(target_slot) is None:
            return None
            
        # Find the new value in available options
        options = self._options_for_slot(state, target_slot)
        new_value = None
        
        for option in options:
            if option.lower() in after_to or after_to in option.lower():
                new_value = option
                break
        
        if not new_value:
            return None
            
        # Update the slot with the new value
        state.slot_values[target_slot] = new_value
        
        # Reset dependent slots
        for j in range(slot_index + 1, len(state.slot_order)):
            dep_slot = state.slot_order[j]
            state.slot_values[dep_slot] = None
            state.slot_states[dep_slot] = SlotState.EMPTY
        
        # Set up to prompt for the next slot
        next_slot_index = slot_index + 1
        if next_slot_index < len(state.slot_order):
            next_slot = state.slot_order[next_slot_index]
            state.current_slot_index = next_slot_index
            state.awaiting_slot_input = True
            
            # Generate prompt for next slot
            next_options = self._options_for_slot(state, next_slot)
            state.response_message = f"Changed {target_slot} to {new_value}. Please select a {next_slot}. Options: {', '.join(next_options)}"
            return state.response_message
        else:
            state.response_message = f"Changed {target_slot} to {new_value}."
            return state.response_message