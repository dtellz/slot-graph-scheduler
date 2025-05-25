"""FastAPI WebSocket server for medical appointment scheduling."""

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from graph_manager import GraphManager

app = FastAPI(title="Medical Appointment Scheduler")

graph_manager = GraphManager()

# active WebSocket connections, keyed by thread_id
active_connections: dict[str, WebSocket] = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Extract required fields from message data with type hints
            thread_id: str | None = message_data.get("thread_id")
            token: str | None = message_data.get("token")
            message: str | None = message_data.get("message")

            if not thread_id or not token or not message:
                await websocket.send_text(
                    json.dumps({"error": "Missing thread_id, token or message"})
                )
                continue

            active_connections[thread_id] = websocket

            # async call into the graph manager
            response = await graph_manager.process_message(thread_id, token, message)

            await websocket.send_text(json.dumps({"thread_id": thread_id, "message": response}))

    except WebSocketDisconnect:
        active_connections.pop(
            next((tid for tid, conn in active_connections.items() if conn == websocket), None),
            None,
        )
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": f"Internal error: {e}"}))
        except Exception:
            pass


@app.get("/")
async def root():
    return {
        "message": "Medical Appointment Scheduler API — connect to /ws via WebSocket."
    }