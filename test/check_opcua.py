import asyncio
from asyncua import Client

OPC_URL = "opc.tcp://127.0.0.1:49320"

async def main():
    async with Client(url=OPC_URL) as client:

        # 1. Show all namespaces
        print("\n=== Namespace Array ===")

        namespaces = await client.get_namespace_array()

        for i, uri in enumerate(namespaces):
            print(f"ns={i}: {uri}")

        # 2. Browse OPC UA nodes
        print("\n=== OPC UA Nodes ===")

        async def browse(node, level=0):
            if level > 5:
                return

            children = await node.get_children()

            for child in children:
                name = await child.read_browse_name()

                print(
                    "  " * level,
                    name.Name,
                    "| NodeId:",
                    child.nodeid.to_string()
                )

                await browse(child, level + 1)

        await browse(client.nodes.objects)

asyncio.run(main())