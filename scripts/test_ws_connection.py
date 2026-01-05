import asyncio
import websockets

async def test_ws():
    uri = "ws://localhost:8000/api/v1/ws/monitoring"
    print(f"Connecting to {uri} with Origin: http://localhost:5173...")
    try:
        # Simulate browser origin
        async with websockets.connect(uri, origin="http://localhost:5173") as websocket:
            print("Connected!")
            msg = await websocket.recv()
            print(f"Received: {msg}")
            # Keep alive for a bit
            await asyncio.sleep(1)
            print("Closing...")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
