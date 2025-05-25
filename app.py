"""FastAPI WebSocket server for medical appointment scheduling.

This module implements a WebSocket-based API for a dialog-based slot-filling flow
to schedule medical appointments. It manages conversation state by thread_id and
uses a state machine to control the appointment scheduling process.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
from typing import Dict

from graph_manager import GraphManager

app = FastAPI(title="Medical Appointment Scheduler")

# Create an instance of the GraphManager
graph_manager = GraphManager()

# Define thread ID type alias
ThreadId = str

# Store active connections
active_connections: Dict[ThreadId, WebSocket] = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time appointment scheduling conversations.
    
    This endpoint handles the WebSocket connection lifecycle, including:
    - Connection acceptance and welcome message
    - Message processing through the appointment state machine
    - Response delivery back to the client
    - Connection cleanup on disconnect
    
    Each conversation is identified by a unique thread_id, allowing multiple
    concurrent conversations to be managed independently.
    
    Args:
        websocket: The WebSocket connection from the client
    """
    await websocket.accept()
    
    try:
        while True:
            # Receive a message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Extract required fields
            thread_id = message_data.get("thread_id")
            token = message_data.get("token")
            message = message_data.get("message")
            
            if not thread_id or not token or not message:
                await websocket.send_text(json.dumps({
                    "error": "Missing required fields: thread_id, token, and message are required"
                }))
                continue
            
            # Store the connection
            active_connections[thread_id] = websocket
            
            # Process the message using the graph manager
            response = graph_manager.process_message(thread_id, token, message)
            
            # Send the response
            await websocket.send_text(json.dumps({
                "thread_id": thread_id,
                "message": response
            }))
    
    except WebSocketDisconnect:
        # Remove connection when disconnected
        for thread_id, conn in list(active_connections.items()):
            if conn == websocket:
                active_connections.pop(thread_id)
                break
    except Exception as e:
        # Handle any exceptions
        try:
            await websocket.send_text(json.dumps({
                "error": f"An error occurred: {str(e)}"
            }))
        except Exception:
            pass

@app.get("/")
async def root():
    """Root endpoint providing basic API information.
    
    Returns:
        dict: A message directing users to the WebSocket endpoint
    """
    return {"message": "Medical Appointment Scheduler API. Connect to /ws for WebSocket communication."}
