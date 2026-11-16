"""Real MCP stdio/backend verification; creates an unpublished fictional draft."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connection(key):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("server.py"))],
        env={**os.environ, "HUMANLOOP_API_KEY": key},
    )
    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def payload(result):
    assert not result.isError, "Expected successful tool response"
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    for block in result.content:
        if block.type == "text":
            return json.loads(block.text)
    raise AssertionError("Missing JSON tool response")


async def main():
    if os.environ.get("HUMANLOOP_VERIFY_DEVELOPMENT") != "true":
        raise RuntimeError(
            "Set HUMANLOOP_VERIFY_DEVELOPMENT=true for fictional draft creation"
        )
    key = os.environ["HUMANLOOP_API_KEY"]
    other = os.environ["HUMANLOOP_OTHER_API_KEY"]
    base = os.environ.get("HUMANLOOP_API_URL", "http://127.0.0.1:8000/api/v1").rstrip(
        "/"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        identities = []
        for token in (key, other):
            response = await client.get(
                base + "/agent/account", headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            identities.append(response.json()["owner_id"])
        assert identities[0] != identities[1], "Keys must belong to distinct owners"
    async with connection(key) as owner:
        names = {tool.name for tool in (await owner.list_tools()).tools}
        assert {"search_workers", "create_task_draft", "get_task_status"} <= names
        assert "items" in payload(
            await owner.call_tool("search_workers", {"query": "research"})
        )
        request = {
            "title": "Fictional MCP integration draft",
            "description": "Fictional test of public opening-hours research. No real work requested.",
            "category": "Retail checks",
            "city": "Toronto",
            "budget": 3000,
            "idempotency_key": str(uuid4()),
        }
        draft = payload(await owner.call_tool("create_task_draft", request))
        assert draft["status"] == "DRAFT" and draft["owner_id"] == identities[0]
        assert (
            payload(await owner.call_tool("create_task_draft", request))["id"]
            == draft["id"]
        )
        assert (
            payload(await owner.call_tool("get_task_status", {"task_id": draft["id"]}))[
                "status"
            ]
            == "DRAFT"
        )
        assert (
            await owner.call_tool("get_task_status", {"task_id": "invalid-uuid"})
        ).isError
        assert (
            await owner.call_tool(
                "create_task_draft",
                {**request, "budget": -1, "idempotency_key": str(uuid4())},
            )
        ).isError
        async with connection(other) as outsider:
            assert (
                await outsider.call_tool("get_task_status", {"task_id": draft["id"]})
            ).isError
        async with connection("hl_invalid_integration_test_key") as invalid:
            assert (await invalid.call_tool("search_workers", {})).isError
    print(
        "MCP integration passed: discovery, draft/status, replay, ownership, invalid input and invalid key."
    )


if __name__ == "__main__":
    asyncio.run(main())
