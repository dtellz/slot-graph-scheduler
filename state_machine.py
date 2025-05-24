from typing import Dict, List, Optional
from enum import Enum, auto

from mock_client import MockApiClient


class SlotState(Enum):
    """Enum representing the state of a slot in the appointment process."""
    EMPTY = auto()
    FILLING = auto()
    FILLED = auto()
    CHANGING = auto()


class AppointmentStateMachine:
    """State machine for managing medical appointment scheduling conversations."""
    
    def __init__(self):
        self.api_client = MockApiClient()
        self.slots = ["hospital", "specialty", "doctor", "slot"]
        self.slot_values: Dict[str, Optional[str]] = {slot: None for slot in self.slots}
        self.slot_states: Dict[str, SlotState] = {slot: SlotState.EMPTY for slot in self.slots}
        self.current_slot_index = 0
        self.completed = False
        self.awaiting_slot_input = False
        self.first_message = True
    
    def detect_intent(self, message: str) -> str:
        """Detect if the user wants to change a slot or continue with the flow."""
        if self.first_message or not message.strip():
            self.first_message = False
            return self.prompt_for_current_slot()
    
        if self.awaiting_slot_input:
            return self.process_slot_input(message)
        
        message_lower = message.lower()
        
        for i, slot in enumerate(self.slots):
            if slot.lower() in message_lower and "change" in message_lower and self.slot_values[slot] is not None:
                self.current_slot_index = i
                self.slot_states[slot] = SlotState.CHANGING
                
                for j in range(i + 1, len(self.slots)):
                    dependent_slot = self.slots[j]
                    self.slot_values[dependent_slot] = None
                    self.slot_states[dependent_slot] = SlotState.EMPTY
                
                return self.prompt_for_current_slot()
        
        if all(value is not None for value in self.slot_values.values()):
            if "another" in message_lower or "new" in message_lower or "different" in message_lower:
                for slot in self.slots:
                    self.slot_values[slot] = None
                    self.slot_states[slot] = SlotState.EMPTY
                self.current_slot_index = 0
                self.completed = False
                return self.prompt_for_current_slot()
            else:
                return "Your appointment is already scheduled. If you'd like to make another appointment, please let me know."
        
        return self.process_slot_input(message)
    
    def prompt_for_current_slot(self) -> str:
        """Provide options for the current slot."""
        current_slot = self.slots[self.current_slot_index]
        self.slot_states[current_slot] = SlotState.FILLING
        self.awaiting_slot_input = True
        
        options = self.get_options_for_slot(current_slot)
        
        return f"Please select a {current_slot}. Available options: {', '.join(options)}"
    
    def process_slot_input(self, message: str) -> str:
        """Process user input for the current slot."""
        current_slot = self.slots[self.current_slot_index]
        selection = message.strip()
        options = self.get_options_for_slot(current_slot)
        
        matching_option = next((option for option in options if option.lower() == selection.lower()), None)
        
        if matching_option:
            self.slot_values[current_slot] = matching_option
            self.slot_states[current_slot] = SlotState.FILLED
            self.awaiting_slot_input = False
            
            if self.current_slot_index < len(self.slots) - 1:
                self.current_slot_index += 1
                next_slot = self.slots[self.current_slot_index]
                options = self.get_options_for_slot(next_slot)
                
                if options:
                    self.awaiting_slot_input = True
                    return f"Great! You've selected {matching_option} for {current_slot}. Now please select a {next_slot}. Available options: {', '.join(options)}"
                else:
                    return f"Great! You've selected {matching_option} for {current_slot}. However, there are no available options for {next_slot} with your current selections."
            else:
                self.completed = True
                return self.complete_appointment()
        else:
            return f"Sorry, '{selection}' is not a valid option for {current_slot}. Please choose from: {', '.join(options)}"
    
    def complete_appointment(self) -> str:
        """Complete the appointment process."""
        if all(value is not None for value in self.slot_values.values()):
            return (
                f"Your appointment has been scheduled!\n"
                f"Hospital: {self.slot_values['hospital']}\n"
                f"Specialty: {self.slot_values['specialty']}\n"
                f"Doctor: {self.slot_values['doctor']}\n"
                f"Appointment time: {self.slot_values['slot']}\n\n"
                f"Is there anything else you would like to change?"
            )
        else:
            return "We still need some information to complete your appointment."
    
    def get_options_for_slot(self, slot: str) -> List[str]:
        """Get available options for the current slot based on previous selections."""
        if slot == "hospital":
            return self.api_client.get_hospitals()
        elif slot == "specialty":
            hospital = self.slot_values["hospital"]
            if hospital:
                return self.api_client.get_specialties(hospital)
            return []
        elif slot == "doctor":
            hospital = self.slot_values["hospital"]
            specialty = self.slot_values["specialty"]
            if hospital and specialty:
                return self.api_client.get_doctors(hospital, specialty)
            return []
        elif slot == "slot":
            hospital = self.slot_values["hospital"]
            specialty = self.slot_values["specialty"]
            doctor = self.slot_values["doctor"]
            if hospital and specialty and doctor:
                return self.api_client.get_appointment_slots(hospital, specialty, doctor)
            return []
        return []
    
    def process_message(self, message: str) -> str:
        """Process an incoming message and return a response."""
        return self.detect_intent(message)
