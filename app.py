"""FastAPI WebSocket server for medical appointment scheduling.

This module implements a WebSocket-based API for a dialog-based slot-filling flow
to schedule medical appointments. It manages conversation state by thread_id and
uses a state machine to control the appointment scheduling process.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict
import json
import uuid

from state_machine import AppointmentStateMachine

app = FastAPI(title="Medical Appointment Scheduler")

type ThreadId = str

active_connections: Dict[ThreadId, WebSocket] = {}
conversation_states: Dict[ThreadId, AppointmentStateMachine] = {}

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
    
    thread_id = str(uuid.uuid4())
    await websocket.send_text(json.dumps({
        "thread_id": thread_id,
        "response": "Welcome to the Medical Appointment Scheduler. How can I help you schedule your appointment today?"
    }))
    
    try:
        active_connections[thread_id] = websocket
        state_machine = AppointmentStateMachine()
        conversation_states[thread_id] = state_machine
        
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            client_thread_id = message_data.get("thread_id")
            message = message_data.get("message")
            
            if client_thread_id:
                thread_id = client_thread_id
            
            response = state_machine.process_message(message)
            
            await websocket.send_text(json.dumps({
                "thread_id": thread_id,
                "response": response
            }))
            
    except WebSocketDisconnect:
        for thread_id, conn in list(active_connections.items()):
            if conn == websocket:
                del active_connections[thread_id]

@app.get("/")
async def root():
    """Root endpoint providing basic API information.
    
    Returns:
        dict: A message directing users to the WebSocket endpoint
    """
    return {"message": "Medical Appointment Scheduler API. Connect to /ws for WebSocket communication."}
