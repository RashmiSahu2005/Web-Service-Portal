import asyncio
import websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8000/ws/installation/job_1234") as ws:
        print("Connected!")
        await asyncio.sleep(1)

asyncio.run(test())
