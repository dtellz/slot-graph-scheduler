import asyncio
import json
import websockets
import uuid

async def connect_and_chat():
    """Connect to the WebSocket server and interact with it."""
    uri = "ws://localhost:8000/ws"
    thread_id = str(uuid.uuid4())
    
    try:
        print("Connecting to the appointment scheduler...")
        print(f"Using thread ID: {thread_id}")
        async with websockets.connect(uri) as websocket:
            # Send an initial message to start the conversation
            await send_message(websocket, thread_id, "Hello")
            
            # Get the initial response
            response = await websocket.recv()
            response_data = json.loads(response)
            
            # Check if this is an error message or a regular response
            if 'error' in response_data:
                print(f"Server Error: {response_data['error']}")
            elif 'message' in response_data:
                print(f"Server: {response_data['message']}")
            else:
                print(f"Server sent: {response_data}")
            
            while True:
                user_input = input("You: ")
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Ending conversation. Goodbye!")
                    break
                
                await send_message(websocket, thread_id, user_input)
                
                response = await websocket.recv()
                response_data = json.loads(response)
                
                # Check if this is an error message or a regular response
                if 'error' in response_data:
                    print(f"Server Error: {response_data['error']}")
                elif 'message' in response_data:
                    print(f"Server: {response_data['message']}")
                else:
                    print(f"Server sent: {response_data}")
    
    except websockets.exceptions.ConnectionClosedError:
        print("\nConnection closed by the server. Make sure the server is running.")
        print("To start the server, run: python main.py")
    except ConnectionRefusedError:
        print("\nCould not connect to the server. Make sure the server is running.")
        print("To start the server, run: python main.py")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        print("\nTest client closed.")
        return

async def send_message(websocket, thread_id, message):
    """Send a message to the WebSocket server."""
    message_data = {
        "thread_id": thread_id,
        "token": "test-token",  # Not used in the implementation / included for completeness
        "message": message
    }
    await websocket.send(json.dumps(message_data))

if __name__ == "__main__":
    asyncio.run(connect_and_chat())
