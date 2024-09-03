import asyncio
import socket
import struct
import json

class IBClient:
    def __init__(self, host='127.0.0.1', port=7496):
        self.host = host
        self.port = port
        self.loop = asyncio.get_event_loop()
        self.socket = None

    async def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        await self.loop.run_in_executor(None, self.socket.connect, (self.host, self.port))
        print("Connected to TWS API")

    async def receive_messages(self):
        while True:
            data = await self.loop.run_in_executor(None, self.socket.recv, 4096)
            if not data:
                break
            self.process_message(data)

    def process_message(self, data):
        # Here you would parse the data according to TWS API message format
        # For example, let's assume the message is in JSON format
        try:
            message = json.loads(data.decode('utf-8'))
            if 'type' in message and message['type'] == 'orderFilled':
                stock_symbol = message.get('symbol')
                quantity = message.get('quantity')
                fill_price = message.get('fillPrice')
                fill_time = message.get('time')
                print(f"Order filled: {stock_symbol}, Quantity: {quantity}, Fill Price: {fill_price}, Time: {fill_time}")
                # You can store or process these values as needed
        except json.JSONDecodeError:
            print("Failed to decode message")

    async def run(self):
        await self.connect()
        await self.receive_messages()

if __name__ == "__main__":
    client = IBClient()
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("Client stopped.")
    finally:
        if client.socket:
            client.socket.close()
