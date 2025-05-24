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
        async with websockets.connect(uri) as websocket:
            welcome = await websocket.recv()
            welcome_data = json.loads(welcome)

            print(f"Server: {welcome_data['response']}")
            thread_id = welcome_data.get('thread_id', thread_id)
            
            while True:
                user_input = input("You: ")
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Ending conversation. Goodbye!")
                    break
                
                await send_message(websocket, thread_id, user_input)
                
                response = await websocket.recv()
                response_data = json.loads(response)
                print(f"Server: {response_data['response']}")
    
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
