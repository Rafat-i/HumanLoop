"""Official MCP SDK, local stdio transport only. Never log credentials or stdout noise."""
import os
from uuid import UUID
from urllib.parse import urlparse
import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("HUMANLOOP_API_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
KEY = os.environ.get("HUMANLOOP_API_KEY", "")
parsed = urlparse(BASE_URL)
if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
    raise RuntimeError("API URL must use HTTPS or local loopback HTTP")
if not KEY.startswith("hl_"):
    raise RuntimeError("Set HUMANLOOP_API_KEY to a scoped account-owned key")
mcp = FastMCP("HumanLoop", instructions="Create drafts only. An account owner must approve tasks; workers must accept assignments. Never imply tools authorize payments or physical work.")


async def request(method, path, data=None, params=None, idempotency_key=None):
    headers = {"Authorization": f"Bearer {KEY}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.request(method, BASE_URL + path, headers=headers, json=data, params=params)
    if not response.is_success:
        raise ValueError(f"HumanLoop rejected the request ({response.status_code}): {response.json().get('error', {}).get('message', 'Request failed')}")
    return response.json()


@mcp.tool()
async def search_workers(query: str = "", city: str = "", page: int = 1):
    """Search explicitly published worker profiles; approximate city only."""
    return await request("GET", "/agent/workers", params={"q": query, "city": city, "page": page})


@mcp.tool()
async def get_worker_profile(worker_id: UUID):
    """Read permitted public worker information."""
    return await request("GET", f"/agent/workers/{worker_id}")


@mcp.tool()
async def list_services(page: int = 1):
    """List publicly published worker services."""
    return await request("GET", "/agent/services", params={"page": page})


@mcp.tool()
async def create_task_draft(title: str, description: str, category: str, city: str, budget: int, idempotency_key: str, currency: str = "CAD", required_skills: list[str] | None = None, expected_minutes: int = 60):
    """Create a draft, not a booking. Budget is integer minor currency units. Reuse the same idempotency key only for retries of the same request."""
    return await request("POST", "/agent/tasks/drafts", {"title": title, "description": description, "category": category, "city": city, "budget": budget, "currency": currency, "required_skills": required_skills or [], "expected_minutes": expected_minutes}, idempotency_key=idempotency_key)


@mcp.tool()
async def submit_task_for_approval(task_id: UUID, idempotency_key: str):
    """Submit an owned draft for human review. Does not publish or commit funds."""
    return await request("POST", f"/agent/tasks/{task_id}/submit", idempotency_key=idempotency_key)


@mcp.tool()
async def get_task_status(task_id: UUID):
    """Read a task owned by this key's human account."""
    return await request("GET", f"/agent/tasks/{task_id}")


@mcp.tool()
async def list_my_tasks(page: int = 1):
    """List this account owner's tasks."""
    return await request("GET", "/agent/tasks", params={"page": page})


@mcp.tool()
async def get_task_results(task_id: UUID):
    """Retrieve authorized private results for an owned task."""
    return await request("GET", f"/agent/tasks/{task_id}/results")


@mcp.tool()
async def send_task_message(task_id: UUID, content: str, idempotency_key: str):
    """Send plain text only inside an owned, assigned task."""
    return await request("POST", "/agent/messages", {"task_id": str(task_id), "content": content}, idempotency_key=idempotency_key)


@mcp.tool()
async def get_notifications(page: int = 1):
    """Read notifications belonging to this account owner."""
    return await request("GET", "/agent/notifications", params={"page": page})


if __name__ == "__main__":
    mcp.run(transport="stdio")
