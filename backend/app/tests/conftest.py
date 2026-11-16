"""Route tests use real SQLite SQL through a test-only async session facade.
This does NOT exercise async drivers, PostgreSQL semantics, or row locking.
PostgreSQL concurrency tests use real AsyncSession separately.
"""

import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import get_db
from app.models.entities import Base, User, WorkerProfile


class TestSession:
    __test__ = False

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def commit(self):
        self.session.commit()

    def add(self, value):
        self.session.add(value)

    def add_all(self, values):
        self.session.add_all(values)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def get(self, model, identifier):
        return self.session.get(model, identifier)

    async def flush(self):
        self.session.flush()

    async def delete(self, value):
        self.session.delete(value)


@pytest.fixture
async def api_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MAIL_DIR", str(tmp_path / "mail"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PAYMENT_PROVIDER", "mock")
    get_settings.cache_clear()
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        with factory() as session:
            try:
                yield TestSession(session)
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    clients = []
    test_ip = str(uuid4())

    def client():
        result = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(test_ip, 123)),
            base_url="http://test",
            headers={"Origin": "http://localhost:3000"},
        )
        clients.append(result)
        return result

    async def account(email, role="client", admin=False):
        c = client()
        response = await c.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "test-password-long-123",
                "display_name": "Test Person",
                "role": role,
                "adult_confirmed": True,
            },
        )
        assert response.status_code == 201, response.text
        mails = [json.loads(path.read_text()) for path in (tmp_path / "mail").glob("*.json")]
        mail = next(m for m in mails if m["to"] == email)
        token = parse_qs(urlparse(mail["url"]).query)["token"][0]
        assert (await c.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 200
        assert (
            await c.post("/api/v1/auth/login", json={"email": email, "password": "test-password-long-123"})
        ).status_code == 200
        user = (await c.get("/api/v1/auth/me")).json()
        if admin:
            with factory() as db:
                db.get(User, user["id"]).roles = ["admin", "client"]
                db.commit()
        if role == "worker":
            response = await c.put(
                "/api/v1/profile",
                json={
                    "display_name": "Test Worker",
                    "headline": "Useful public research",
                    "bio": "An experienced fictional worker for automated tests.",
                    "city": "Toronto",
                    "category": "Retail checks",
                    "skills": ["research"],
                    "hourly_rate": 2500,
                    "available": True,
                    "published": True,
                },
            )
            assert response.status_code == 200, response.text
            with factory() as db:
                db.scalar(
                    select(WorkerProfile).where(WorkerProfile.user_id == user["id"])
                ).review_status = "APPROVED"
                db.commit()
        return c, user

    yield {
        "app": app,
        "client": client,
        "account": account,
        "factory": factory,
        "mail_dir": tmp_path / "mail",
    }
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()
