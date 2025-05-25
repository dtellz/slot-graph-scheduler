import pytest
import json
from fastapi.testclient import TestClient

from src.app import app


@pytest.fixture
def client():
    """Create a FastAPI TestClient for testing the API."""
    return TestClient(app)


@pytest.fixture
def websocket_client():
    """Create a FastAPI TestClient for websocket testing."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_websocket_contract(websocket_client):
    """Test the WebSocket contract with proper JSON message shape."""
    thread_id = "test_websocket_contract"
    token = "test_token"
    
    with websocket_client.websocket_connect("/ws") as websocket:

        message_data = {
            "thread_id": thread_id,
            "token": token,
            "message": "Central Hospital"
        }
        websocket.send_text(json.dumps(message_data))
        
        # Receive response
        response = websocket.receive_text()
        response_data = json.loads(response)
        

        assert "thread_id" in response_data
        assert "message" in response_data
        assert "specialty" in response_data["message"].lower()


def test_concurrent_threads(websocket_client):
    """Test handling multiple concurrent threads without state bleeding."""
    def run_conversation(thread_id, messages):
        results = []
        with websocket_client.websocket_connect("/ws") as websocket:
            for msg in messages:
                message_data = {
                    "thread_id": thread_id,
                    "token": "test_token",
                    "message": msg
                }
                websocket.send_text(json.dumps(message_data))
                response = websocket.receive_text()
                results.append(json.loads(response))
        return results
    
    # Run sequential conversations with different thread IDs
    thread1_results = run_conversation("thread1", ["Central Hospital", "Cardiology"])
    thread2_results = run_conversation("thread2", ["North Hospital", "Pediatrics"])
    
    # Check the responses contain the expected values
    assert "specialty" in thread1_results[0]["message"].lower()
    assert "doctor" in thread1_results[1]["message"].lower()
    
    assert "specialty" in thread2_results[0]["message"].lower()
    assert "doctor" in thread2_results[1]["message"].lower()


def test_error_handling(websocket_client):
    """Test error handling for malformed messages."""
    with websocket_client.websocket_connect("/ws") as websocket:

        message_data = {
            "message": "Hello"
            # Missing required fields
        }
        websocket.send_text(json.dumps(message_data))
        
        # Receive response
        response = websocket.receive_text()
        response_data = json.loads(response)
        

        assert "error" in response_data
        assert "thread_id" in response_data["error"].lower() or "missing" in response_data["error"].lower()
