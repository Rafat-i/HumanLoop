"""Full HTTP lifecycle through real AsyncSession; apply migrations before running."""

import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import digest
from app.models.entities import Session, User, WorkerProfile, now


@pytest.mark.postgres
async def test_postgres_http_lifecycle(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for PostgreSQL HTTP lifecycle")
    parsed = make_url(url)
    assert parsed.drivername == "postgresql+asyncpg" and (parsed.database or "").endswith("_test")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "mock")
    get_settings.cache_clear()
    from app.main import app

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tokens = [uuid4().hex for _ in range(3)]

    async def database():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    previous = app.dependency_overrides.get(get_db)
    try:
        async with engine.connect() as connection:
            assert "PostgreSQL" in await connection.scalar(text("select version()"))
            assert await connection.scalar(text("select version_num from alembic_version"))
        async with factory() as db:
            people = []
            for index, role in enumerate(("client", "worker", "client")):
                user = User(
                    email=f"pg-{uuid4().hex}@example.com",
                    display_name="Fictional PG tester",
                    password_hash="no-password-login",
                    roles=[role],
                    adult_confirmed=True,
                    email_verified=True,
                    demo=True,
                )
                db.add(user)
                await db.flush()
                db.add(
                    Session(
                        user_id=user.id,
                        token_hash=digest(tokens[index]),
                        expires_at=now() + timedelta(hours=1),
                    )
                )
                people.append(user)
            db.add(
                WorkerProfile(
                    user_id=people[1].id,
                    display_name="PG test worker",
                    headline="Public research",
                    bio="Fictional integration-test worker profile.",
                    city="Toronto",
                    category="Retail checks",
                    skills=["research"],
                    hourly_rate=2500,
                    review_status="APPROVED",
                    published=False,
                    available=True,
                    demo=True,
                )
            )
            await db.commit()
        app.dependency_overrides[get_db] = database
        transport = httpx.ASGITransport(app=app, client=(uuid4().hex, 123))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"Origin": "http://localhost:3000"}
        ) as client:

            def account(index):
                client.cookies.clear()
                client.cookies.set("hl_session", tokens[index])

            account(0)
            created = await client.post(
                "/api/v1/tasks",
                json={
                    "title": "Fictional PostgreSQL lifecycle",
                    "description": "Document public information in this fictional integration test.",
                    "category": "Retail checks",
                    "city": "Toronto",
                    "budget": 3000,
                },
            )
            assert created.status_code == 201, created.text
            path = "/api/v1/tasks/" + created.json()["id"]
            assert (await client.post(path + "/submit-for-approval")).status_code == 200
            assert (await client.post(path + "/publish")).status_code == 200
            account(1)
            application = await client.post(
                path + "/applications",
                json={
                    "proposal": "I will provide a clear public report.",
                    "compensation": 3000,
                    "estimated_minutes": 60,
                },
            )
            assert application.status_code == 201
            account(0)
            assert (
                await client.post(path + "/applications/" + application.json()["id"] + "/accept")
            ).status_code == 200
            account(2)
            assert (await client.get(path + "/messages")).status_code == 403
            account(1)
            assert (await client.post(path + "/start")).status_code == 200
            assert (
                await client.post(path + "/messages", json={"content": "Accepted fictional scope."})
            ).status_code == 201
            assert (
                await client.post(
                    path + "/results",
                    json={"report": "Fictional report: publicly displayed information documented."},
                )
            ).status_code == 200
            account(0)
            assert (await client.get(path + "/messages")).json()[0]["content"] == "Accepted fictional scope."
            assert (await client.post(path + "/complete")).status_code == 200
            checkout = await client.post(path + "/checkout")
            assert checkout.status_code < 300, checkout.text
            payment = checkout.json()["payment"]
            assert (await client.post("/api/v1/payments/" + payment["id"] + "/simulate")).json()[
                "status"
            ] == "SUCCEEDED"
            account(1)
            assert (await client.get("/api/v1/analytics")).json()["tasks_completed"] == 1
            # Exercise PostgreSQL UUID/aggregate serialization with populated worker data.
            account(0)
            assert (
                await client.post(
                    path + "/reviews", json={"rating": 5, "comment": "Fictional integration review."}
                )
            ).status_code < 300
            async with factory() as db:
                profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == people[1].id))
                profile.published = True
                profile_id = profile.id
                await db.commit()
            try:
                listing = await client.get(
                    "/api/v1/workers", params={"q": "PG test worker", "sort": "recent"}
                )
                assert listing.status_code == 200, listing.text
                detail = await client.get("/api/v1/workers/" + profile_id)
                assert detail.status_code == 200, detail.text
                assert detail.json()["rating"] == 5
                assert detail.json()["completed_tasks"] == 1
                assert (await client.get("/api/v1/workers/showcase")).status_code == 200
            finally:
                async with factory() as db:
                    profile = await db.get(WorkerProfile, profile_id)
                    profile.published = False
                    await db.commit()

    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        await engine.dispose()
        get_settings.cache_clear()
