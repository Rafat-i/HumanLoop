import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("server.py"))], env={**os.environ})
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Available tools:", ", ".join(tool.name for tool in tools.tools))
            result = await session.call_tool("search_workers", {"query": "research", "city": "Montréal"})
            if result.isError:
                raise RuntimeError(str(result.content))
            print("Worker search:", result.content)
            if "--create-draft" in sys.argv:
                result = await session.call_tool("create_task_draft", {"title": "Check public store hours", "description": "Observe the opening hours posted at a public store entrance. No purchase or private access.", "category": "Retail checks", "city": "Montréal", "budget": 3000, "idempotency_key": str(uuid4())})
                if result.isError:
                    raise RuntimeError(str(result.content))
                print("Created draft only:", result.content)


if __name__ == "__main__":
    asyncio.run(main())
