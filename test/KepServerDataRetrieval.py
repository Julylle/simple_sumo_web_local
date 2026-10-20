import asyncio
from asyncua import Client

OPC_URL = "opc.tcp://127.0.0.1:49320"

NODE_ID = "ns=2;s=GEeth.PLC128.Influent_ammonia_sensor"


async def main():

    async with Client(url=OPC_URL, timeout=15) as client:

        node = client.get_node(NODE_ID)

        while True:

            value = await node.read_value()

            print(f"Influent NH4: {value}")

            await asyncio.sleep(5)


asyncio.run(main())