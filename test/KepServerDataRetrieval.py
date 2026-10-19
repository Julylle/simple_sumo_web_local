import asyncio
from asyncua import Client

# Or use: OPC_URL = "opc.tcp://localhost:49320"
OPC_URL = "opc.tcp://192.168.1.100:49320"

async def main():
    async with Client(url=OPC_URL) as client:

        node = client.get_node(
            "ns=2;s=GEeth.PLC128.Influent_ammonia_sensor"
        )

        while True:

            value = await node.read_value()

            print("Influent NH4:", value)

            # Send to model input interface
            # await model_service.update_input(value)

            await asyncio.sleep(5)

asyncio.run(main())