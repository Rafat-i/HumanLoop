"""Must run against a disposable PostgreSQL database ending in _test."""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import Base, Task, TaskApplication, TaskAssignment, User, WorkerProfile
from app.services.tasks import accept_application


@pytest.mark.postgres
async def test_concurrent_assignment_has_one_winner():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL row-lock testing")
    parsed = make_url(url)
    assert parsed.drivername == "postgresql+asyncpg" and parsed.database.endswith("_test"), (
        "Refusing non-test database"
    )
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    suffix = uuid4().hex
    async with factory() as db:
        owner = User(
            email=f"owner-{suffix}@example.com",
            display_name="Owner",
            password_hash="not-a-login-hash",
            roles=["client"],
            adult_confirmed=True,
            email_verified=True,
        )
        workers = [
            User(
                email=f"worker-{n}-{suffix}@example.com",
                display_name="Worker",
                password_hash="not-a-login-hash",
                roles=["worker"],
                adult_confirmed=True,
                email_verified=True,
            )
            for n in range(2)
        ]
        db.add_all([owner, *workers])
        await db.flush()
        for w in workers:
            db.add(
                WorkerProfile(
                    user_id=w.id,
                    display_name="Worker",
                    headline="Research",
                    bio="Test profile",
                    city="Toronto",
                    category="Retail checks",
                    skills=["research"],
                    hourly_rate=2500,
                    review_status="APPROVED",
                    available=True,
                )
            )
        task = Task(
            owner_id=owner.id,
            title="Concurrency test",
            description="Only one worker may be assigned",
            category="Retail checks",
            city="Toronto",
            budget=3000,
            status="OPEN",
        )
        db.add(task)
        await db.flush()
        applications = [
            TaskApplication(
                task_id=task.id,
                worker_id=w.id,
                proposal="Test proposal",
                compensation=3000,
                estimated_minutes=60,
            )
            for w in workers
        ]
        db.add_all(applications)
        await db.commit()
        owner_id, task_id, ids = owner.id, task.id, [a.id for a in applications]

    async def attempt(application_id):
        async with factory() as db:
            user = await db.get(User, owner_id)
            try:
                await accept_application(db, user, task_id, application_id)
                await db.commit()
                return 200
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code

    results = await asyncio.gather(*(attempt(identifier) for identifier in ids))
    assert sorted(results) == [200, 409]
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(TaskAssignment).where(TaskAssignment.task_id == task_id)
            )
            == 1
        )
    await engine.dispose()
