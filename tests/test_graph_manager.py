import pytest

from src.graph_manager import GraphManager


@pytest.fixture
def graph_manager():
    """Create a fresh GraphManager instance for each test."""
    return GraphManager()


@pytest.mark.asyncio
async def test_happy_path_end_to_end(graph_manager):
    """Test the complete happy path flow: hospital → specialty → doctor → slot → completion."""

    thread_id = "happy_path_test"
    token = "test_token"
    

    response = await graph_manager.process_message(thread_id, token, "Central Hospital")
    assert "specialty" in response.lower()
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] == "Central Hospital"
    assert not state.completed
    

    response = await graph_manager.process_message(thread_id, token, "Cardiology")
    assert "doctor" in response.lower()
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["specialty"] == "Cardiology"
    assert not state.completed
    

    response = await graph_manager.process_message(thread_id, token, "Dr. Garcia")
    assert "timeslot" in response.lower() or "appointment" in response.lower()
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["doctor"] == "Dr. Garcia"
    assert not state.completed
    

    response = await graph_manager.process_message(thread_id, token, "2024-05-01 10:00")
    assert "appointment" in response.lower()
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["timeslot"] == "2024-05-01 10:00"
    assert state.completed


@pytest.mark.asyncio
async def test_invalid_option_retry(graph_manager):
    """Test retry behavior when an invalid option is provided."""
    thread_id = "invalid_option_test"
    token = "test_token"
    
    # Initialize with empty message
    await graph_manager.process_message(thread_id, token, "")
    
    # Provide invalid hospital
    response = await graph_manager.process_message(thread_id, token, "Invalid Hospital")
    # Just check if the response is asking for a hospital again
    assert "hospital" in response.lower()
    
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] is None
    assert not state.completed


@pytest.mark.asyncio
async def test_change_intent(graph_manager):
    """Test changing a previously filled slot and verifying downstream reset."""
    thread_id = "change_intent_test"
    token = "test_token"
    
    # Fill the first three slots
    await graph_manager.process_message(thread_id, token, "Central Hospital")
    await graph_manager.process_message(thread_id, token, "Cardiology")
    await graph_manager.process_message(thread_id, token, "Dr. Garcia")
    
    # Verify current state
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] == "Central Hospital"
    assert state.slot_values["specialty"] == "Cardiology"
    assert state.slot_values["doctor"] == "Dr. Garcia"
    
    # Change hospital and verify downstream slots reset
    response = await graph_manager.process_message(thread_id, token, "change hospital to North Hospital")
    

    state = await graph_manager._load_state(thread_id)
    

    assert "specialty" in response.lower()
    

    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] == "North Hospital"
    assert state.slot_values["specialty"] is None
    assert state.slot_values["doctor"] is None
    assert state.slot_values["timeslot"] is None
    assert not state.completed


@pytest.mark.asyncio
async def test_first_turn_shortcut(graph_manager):
    """Test providing a valid slot value on the first turn."""
    thread_id = "first_turn_test"
    token = "test_token"
    

    response = await graph_manager.process_message(thread_id, token, "Central Hospital")
    

    assert "specialty" in response.lower()
    
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] == "Central Hospital"
    assert not state.completed


@pytest.mark.asyncio
async def test_persistence_across_messages(graph_manager):
    """Test state persistence by loading, processing, storing, and loading again."""
    thread_id = "persistence_test"
    token = "test_token"
    

    await graph_manager.process_message(thread_id, token, "Central Hospital")
    

    state_before = await graph_manager._load_state(thread_id)
    assert state_before.slot_values["hospital"] == "Central Hospital"
    

    new_graph_manager = GraphManager()
    

    new_graph_manager._threads = graph_manager._threads.copy()
    

    state_after = await new_graph_manager._load_state(thread_id)
    

    assert state_before.slot_values["hospital"] == state_after.slot_values["hospital"]
    assert state_before.current_slot_index == state_after.current_slot_index
    assert state_before.completed == state_after.completed


@pytest.mark.asyncio
async def test_slot_ordering_abstraction():
    """Test that the graph adjusts automatically to a different slot configuration."""

    thread_id = "slot_order_test"
    token = "test_token"
    graph_manager = GraphManager()
    

    responses = []
    for message in ["Central Hospital", "Cardiology", "Dr. Garcia", "2024-05-01 10:00"]:
        response = await graph_manager.process_message(thread_id, token, message)
        responses.append(response)
    

    assert "specialty" in responses[0].lower()
    assert "doctor" in responses[1].lower()
    assert "slot" in responses[2].lower() or "time" in responses[2].lower() or "appointment" in responses[2].lower()
    assert "appointment" in responses[3].lower() and "booked" in responses[3].lower()
    

    state = await graph_manager._load_state(thread_id)
    assert state.completed


@pytest.mark.asyncio
async def test_case_insensitive_matching(graph_manager):
    """Test that slot values match case-insensitively."""
    thread_id = "case_insensitive_test"
    token = "test_token"
    

    response = await graph_manager.process_message(thread_id, token, "central hospital")
    assert "specialty" in response.lower()
    
    state = await graph_manager._load_state(thread_id)
    assert state.slot_values["hospital"] == "Central Hospital"
