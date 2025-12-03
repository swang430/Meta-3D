#!/usr/bin/env python3
"""Test WebSocket monitoring endpoint"""
import asyncio
import websockets
import json


async def test_monitoring_websocket():
    """Connect to monitoring WebSocket and receive a few messages"""
    uri = "ws://localhost:8001/api/v1/ws/monitoring"

    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected successfully")

            # Receive and print first 5 messages
            for i in range(5):
                message = await websocket.recv()
                data = json.loads(message)

                print(f"\n=== Message {i+1} ===")
                print(f"Type: {data.get('type')}")
                print(f"Timestamp: {data.get('timestamp')}")

                if data.get('type') == 'metrics':
                    metrics = data.get('data', {})
                    print(f"Metrics received: {len(metrics)} items")
                    for name, metric in metrics.items():
                        print(f"  - {name}: {metric['value']} {metric['unit']} (status: {metric['status']})")
                else:
                    print(f"Message: {data.get('message')}")

            # Send a ping
            print("\n=== Testing ping ===")
            await websocket.send(json.dumps({"type": "ping"}))
            pong = await websocket.recv()
            pong_data = json.loads(pong)
            print(f"Received: {pong_data.get('type')} at {pong_data.get('timestamp')}")

            print("\n✓ WebSocket test completed successfully!")

    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    return True


if __name__ == "__main__":
    result = asyncio.run(test_monitoring_websocket())
    exit(0 if result else 1)
