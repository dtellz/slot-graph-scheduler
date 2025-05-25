import pytest
import json
from fastapi.testclient import TestClient

from src.app import app
from src.graph_manager import GraphManager
from src.mock_client import MockApiClient


@pytest.fixture
def client():
    """Create a FastAPI TestClient for testing."""
    return TestClient(app)


@pytest.fixture
def graph_manager():
    """Create a fresh GraphManager instance for testing."""
    return GraphManager()


@pytest.fixture
def mock_client():
    """Create a MockApiClient instance for testing."""
    return MockApiClient()


def test_e2e_complete_flow(client):
    """Test a complete end-to-end flow through the WebSocket API."""
    thread_id = "e2e_complete_flow"
    token = "test_token"
    
    with client.websocket_connect("/ws") as websocket:

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Central Hospital"
        }))
        response = json.loads(websocket.receive_text())
        assert "message" in response
        

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Central Hospital"
        }))
        response = json.loads(websocket.receive_text())
        assert "specialty" in response["message"].lower()
        

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Cardiology"
        }))
        response = json.loads(websocket.receive_text())
        assert "doctor" in response["message"].lower()
        

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Dr. Garcia"
        }))
        response = json.loads(websocket.receive_text())
        assert "time" in response["message"].lower() or "appointment" in response["message"].lower()
        

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "2024-05-01 10:00"
        }))
        response = json.loads(websocket.receive_text())
        assert "appointment" in response["message"].lower() or "booked" in response["message"].lower()


def test_change_previous_slot(client):
    """Test changing a previously filled slot through the WebSocket API."""
    thread_id = "change_slot_test"
    token = "test_token"
    
    with client.websocket_connect("/ws") as websocket:

        for message in ["Central Hospital", "Cardiology"]:
            websocket.send_text(json.dumps({
                "thread_id": thread_id,
                "token": token,
                "message": message
            }))
            websocket.receive_text()  # Consume response
        

        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "I want to change the hospital to North Hospital"
        }))
        response = json.loads(websocket.receive_text())
        

        assert "message" in response


def test_mock_client_integration():
    """Test integration with the MockApiClient."""
    mock = MockApiClient()
    

    hospitals = mock.get_hospitals()
    assert len(hospitals) > 0
    assert isinstance(hospitals, list)
    assert all(isinstance(h, str) for h in hospitals)
    

    specialties = mock.get_specialties("Central Hospital")
    assert len(specialties) > 0
    assert isinstance(specialties, list)
    

    doctors = mock.get_doctors("Central Hospital", "Cardiology")
    assert len(doctors) > 0
    assert isinstance(doctors, list)
    

    slots = mock.get_appointment_slots("Central Hospital", "Cardiology", "Dr. Garcia")
    assert len(slots) > 0
    assert isinstance(slots, list)


def test_session_persistence(client):
    """Test that the session state persists between connections."""
    thread_id = "persistence_session_test"
    token = "test_token"
    

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Central Hospital"
        }))
        first_response = json.loads(websocket.receive_text())
        assert "specialty" in first_response["message"].lower()
    

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "thread_id": thread_id,
            "token": token,
            "message": "Cardiology"
        }))
        second_response = json.loads(websocket.receive_text())

        assert "doctor" in second_response["message"].lower()


def test_multiple_sessions_isolation(client):
    """Test that multiple sessions don't interfere with each other."""
    thread_ids = ["session1", "session2"]
    token = "test_token"
    

    def setup_session(thread_id, hospital):
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "thread_id": thread_id,
                "token": token,
                "message": hospital
            }))
            return json.loads(websocket.receive_text())
    

    setup_session(thread_ids[0], "Central Hospital")
    setup_session(thread_ids[1], "North Hospital")
    

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "thread_id": thread_ids[0],
            "token": token,
            "message": "Cardiology"
        }))
        response = json.loads(websocket.receive_text())
        assert "doctor" in response["message"].lower()  # Should be asking for doctor
    

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "thread_id": thread_ids[1],
            "token": token,
            "message": "Pediatrics"
        }))
        response = json.loads(websocket.receive_text())
        assert "doctor" in response["message"].lower()  # Should be asking for doctor
