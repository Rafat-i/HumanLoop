import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sqlalchemy import func, select

from app.models.entities import PaymentTransaction, Session

PAYLOAD = {
    "title": "Check public opening hours",
    "description": "Confirm publicly displayed hours without entering any private property.",
    "category": "Retail checks",
    "city": "Toronto",
    "budget": 3000,
    "currency": "CAD",
    "required_skills": ["research"],
}


async def open_task(client):
    response = await client.post("/api/v1/tasks", json=PAYLOAD)
    assert response.status_code == 201, response.text
    task = response.json()
    assert (await client.post(f"/api/v1/tasks/{task['id']}/submit-for-approval")).status_code == 200
    assert (await client.post(f"/api/v1/tasks/{task['id']}/publish")).status_code == 200
    return task


async def application(worker, task):
    response = await worker.post(
        f"/api/v1/tasks/{task['id']}/applications",
        json={
            "proposal": "I can provide a clear written report.",
            "compensation": 3000,
            "estimated_minutes": 60,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_complete_workflow_and_negative_authorization(api_env):
    owner, owner_user = await api_env["account"]("owner@example.com")
    worker, worker_user = await api_env["account"]("worker@example.com", "worker")
    outsider, _ = await api_env["account"]("outsider@example.com")
    task = await open_task(owner)
    task_id = task["id"]
    listing = await owner.get("/api/v1/workers?q=research")
    assert listing.json()["total"] == 1
    app = await application(worker, task)
    assert (
        await outsider.post(f"/api/v1/tasks/{task_id}/applications/{app['id']}/accept")
    ).status_code == 403
    assert (await owner.post(f"/api/v1/tasks/{task_id}/applications/{app['id']}/accept")).status_code == 200
    assert (await owner.post(f"/api/v1/tasks/{task_id}/applications/{app['id']}/accept")).status_code == 409
    assert (await owner.post(f"/api/v1/tasks/{task_id}/start")).status_code == 403
    assert (await worker.post(f"/api/v1/tasks/{task_id}/start")).status_code == 200
    assert (
        await worker.post(
            f"/api/v1/tasks/{task_id}/messages", json={"content": "I have accepted the agreed scope."}
        )
    ).status_code == 201
    assert (await outsider.get(f"/api/v1/tasks/{task_id}/messages")).status_code == 403
    assert len((await owner.get(f"/api/v1/tasks/{task_id}/messages")).json()) == 1
    attachment = await worker.post(
        f"/api/v1/tasks/{task_id}/attachments",
        content=b"Public information evidence.",
        headers={"Content-Type": "text/plain", "X-Filename": "report.txt"},
    )
    assert attachment.status_code == 201, attachment.text
    attachment_id = attachment.json()["id"]
    assert (await outsider.get(f"/api/v1/attachments/{attachment_id}")).status_code == 403
    assert (
        await owner.get(f"/api/v1/attachments/{attachment_id}")
    ).content == b"Public information evidence."
    assert (
        await outsider.post(
            f"/api/v1/tasks/{task_id}/results",
            json={"report": "A fabricated result from an unauthorized party."},
        )
    ).status_code == 403
    assert (
        await worker.post(
            f"/api/v1/tasks/{task_id}/results",
            json={"report": "The publicly displayed opening hours were documented in the attached report."},
        )
    ).status_code == 200
    assert (await worker.post(f"/api/v1/tasks/{task_id}/complete")).status_code == 403
    assert (await owner.post(f"/api/v1/tasks/{task_id}/complete")).status_code == 200
    payment = (await owner.post(f"/api/v1/tasks/{task_id}/checkout")).json()["payment"]
    assert (await outsider.post(f"/api/v1/payments/{payment['id']}/simulate")).status_code == 403
    for _ in range(2):
        assert (await owner.post(f"/api/v1/payments/{payment['id']}/simulate")).json()[
            "status"
        ] == "SUCCEEDED"
    assert (await owner.post(f"/api/v1/tasks/{task_id}/checkout")).status_code == 409
    with api_env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 1
    assert (
        await worker.post(
            f"/api/v1/tasks/{task_id}/reviews", json={"rating": 5, "comment": "Self review should fail"}
        )
    ).status_code == 403
    assert (
        await owner.post(
            f"/api/v1/tasks/{task_id}/reviews", json={"rating": 5, "comment": "A clear and useful report."}
        )
    ).status_code == 201
    assert (
        await owner.post(
            f"/api/v1/tasks/{task_id}/reviews", json={"rating": 5, "comment": "Duplicate review"}
        )
    ).status_code == 409
    analytics = (await worker.get("/api/v1/analytics")).json()
    assert analytics["tasks_completed"] == 1
    assert (await owner.get("/api/v1/analytics")).json()["client_tasks_completed"] == 1
    assert analytics["test_earnings"] == [{"currency": "CAD", "amount": 3000}]


async def test_authentication_recovery_csrf_and_sessions(api_env):
    c, user = await api_env["account"]("auth@example.com")
    assert (
        "HttpOnly"
        in (
            await c.post(
                "/api/v1/auth/login", json={"email": "auth@example.com", "password": "test-password-long-123"}
            )
        ).headers["set-cookie"]
    )
    assert (
        await c.post("/api/v1/auth/logout", headers={"Origin": "https://attacker.example"})
    ).status_code == 403
    assert (
        await c.post("/api/v1/auth/login", json={"email": "auth@example.com", "password": "wrong-password"})
    ).status_code == 401
    assert (
        await c.post("/api/v1/auth/forgot-password", json={"email": "auth@example.com"})
    ).status_code == 200
    mails = [json.loads(p.read_text()) for p in api_env["mail_dir"].glob("*.json")]
    token = parse_qs(urlparse(next(m for m in mails if m["purpose"] == "reset")["url"]).query)["token"][0]
    assert (
        await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "new-long-test-password"}
        )
    ).status_code == 200
    assert (
        await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "another-test-password"}
        )
    ).status_code == 400
    assert (await c.get("/api/v1/auth/me")).status_code == 401
    with api_env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Session).where(Session.user_id == user["id"])) == 0


async def test_agent_scopes_idempotency_revocation_and_human_boundary(api_env):
    owner, _ = await api_env["account"]("agent-owner@example.com")
    key = (
        await owner.post(
            "/api/v1/keys",
            json={"name": "Test agent", "scopes": ["tasks:write", "tasks:read", "workers:read"]},
        )
    ).json()
    agent = api_env["client"]()
    agent.headers["Authorization"] = "Bearer " + key["key"]
    headers = {"Idempotency-Key": str(uuid4())}
    response = await agent.post("/api/v1/agent/tasks/drafts", json=PAYLOAD, headers=headers)
    assert response.status_code == 201, response.text
    task = response.json()
    duplicate = await agent.post("/api/v1/agent/tasks/drafts", json=PAYLOAD, headers=headers)
    assert duplicate.json()["id"] == task["id"]
    conflict = await agent.post(
        "/api/v1/agent/tasks/drafts", json={**PAYLOAD, "budget": 4000}, headers=headers
    )
    assert conflict.status_code == 409
    assert (
        await agent.post(
            f"/api/v1/agent/tasks/{task['id']}/submit", headers={"Idempotency-Key": str(uuid4())}
        )
    ).json()["status"] == "PENDING_APPROVAL"
    assert (await agent.post(f"/api/v1/tasks/{task['id']}/publish")).status_code == 401
    assert (await agent.get("/api/v1/agent/notifications")).status_code == 403
    assert "key" not in (await owner.get("/api/v1/keys")).json()[0]
    assert "key_hash" not in (await owner.get("/api/v1/keys")).json()[0]
    assert (await owner.delete(f"/api/v1/keys/{key['id']}")).status_code == 200
    assert (await agent.get("/api/v1/agent/tasks")).status_code == 403


async def test_admin_authorization_and_suspension(api_env):
    normal, user = await api_env["account"]("normal@example.com")
    admin, _ = await api_env["account"]("admin@example.com", admin=True)
    assert (await normal.get("/api/v1/admin/users")).status_code == 403
    assert (await normal.post("/api/v1/auth/roles/admin")).status_code == 422
    assert (
        await admin.post(f"/api/v1/admin/users/{user['id']}", json={"action": "suspend"})
    ).status_code == 200
    assert (await normal.get("/api/v1/auth/me")).status_code in (401, 403)


async def test_unassigned_worker_and_cancelled_task(api_env):
    owner, _ = await api_env["account"]("cancel-owner@example.com")
    worker, _ = await api_env["account"]("other-worker@example.com", "worker")
    task = await open_task(owner)
    assert (
        await worker.post(
            f"/api/v1/tasks/{task['id']}/results", json={"report": "I am not assigned but want to submit."}
        )
    ).status_code == 403
    assert (await owner.post(f"/api/v1/tasks/{task['id']}/cancel")).status_code == 200
    assert (await owner.post(f"/api/v1/tasks/{task['id']}/complete")).status_code == 409
    assert (
        await worker.post(
            f"/api/v1/tasks/{task['id']}/applications",
            json={"proposal": "Too late to apply now", "compensation": 3000, "estimated_minutes": 60},
        )
    ).status_code == 409


async def test_draft_edit_preserves_ownership_and_enforces_review_boundary(api_env):
    owner, user = await api_env["account"]("draft-owner@example.com")
    outsider, _ = await api_env["account"]("draft-outsider@example.com")
    task = (await owner.post("/api/v1/tasks", json=PAYLOAD)).json()
    path = f"/api/v1/tasks/{task['id']}"
    revised = {**PAYLOAD, "title": "Updated public information brief", "budget": 4500}
    assert (await outsider.put(path, json=revised)).status_code == 403
    assert (await api_env["client"]().put(path, json=revised)).status_code == 401
    assert (await owner.put(path, json={**revised, "owner_id": user["id"]})).status_code == 422
    assert (
        await owner.put(
            path, json={**revised, "description": "Please obtain a private address for this person."}
        )
    ).status_code == 422
    unchanged = (await owner.get(path)).json()
    assert unchanged["title"] == PAYLOAD["title"]
    updated = await owner.put(path, json=revised)
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == revised["title"]
    assert updated.json()["budget"] == 4500
    assert updated.json()["status"] == "DRAFT"
    assert updated.json()["owner_id"] == user["id"]
    assert (await owner.post(path + "/submit-for-approval")).status_code == 200
    assert (await owner.put(path, json=PAYLOAD)).status_code == 409
    assert (await owner.get(path)).json()["title"] == revised["title"]


async def test_reports_require_access_to_unpublished_tasks(api_env):
    owner, _ = await api_env["account"]("report-owner@example.com")
    outsider, _ = await api_env["account"]("report-outsider@example.com")
    task = (await owner.post("/api/v1/tasks", json=PAYLOAD)).json()
    path = f"/api/v1/tasks/{task['id']}"
    reason = {"reason": "This request needs a policy review."}
    assert (await outsider.post(path + "/report", json=reason)).status_code == 403
    assert (await owner.post(path + "/report", json=reason)).status_code == 201
    await owner.post(path + "/submit-for-approval")
    await owner.post(path + "/publish")
    assert (await outsider.post(path + "/report", json=reason)).status_code == 201


async def test_draft_deletion_hides_private_content_and_preserves_audit(api_env):
    from app.models.entities import AuditLog, Task

    owner, user = await api_env["account"]("delete-owner@example.com")
    outsider, _ = await api_env["account"]("delete-outsider@example.com")
    task = (await owner.post("/api/v1/tasks", json=PAYLOAD)).json()
    path = f"/api/v1/tasks/{task['id']}"
    attachment = await owner.post(
        path + "/attachments", content=b"Private draft evidence", headers={"Content-Type": "text/plain"}
    )
    assert attachment.status_code == 201
    assert (await outsider.delete(path)).status_code == 403
    assert (await api_env["client"]().delete(path)).status_code == 401
    assert (await owner.delete(path)).status_code == 204
    assert (await owner.get(path)).status_code == 404
    assert (await owner.put(path, json=PAYLOAD)).status_code == 404
    assert (await owner.post(path + "/submit-for-approval")).status_code == 404
    assert (await owner.get("/api/v1/attachments/" + attachment.json()["id"])).status_code == 404
    assert not (await owner.get("/api/v1/my/tasks")).json()
    assert (await owner.get("/api/v1/analytics")).json()["tasks_created"] == 0
    with api_env["factory"]() as db:
        assert db.get(Task, task["id"]).status == "DELETED"
        assert any(
            row.details.get("target") == "DELETED"
            for row in db.scalars(select(AuditLog).where(AuditLog.resource_id == task["id"]))
        )
    active = await open_task(owner)
    assert (await owner.delete("/api/v1/tasks/" + active["id"])).status_code == 409


async def test_marketplace_rejects_malformed_worker_ids(api_env):
    client, _ = await api_env["account"]("identifier-test@example.com")
    for path in (
        "/api/v1/workers/not-a-uuid",
        "/api/v1/workers/not-a-uuid/reviews",
        "/api/v1/services?worker_id=not-a-uuid",
    ):
        response = await client.get(path)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["message"] == "Invalid worker identifier"
