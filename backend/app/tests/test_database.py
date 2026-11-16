"""SQLite verifies portable constraints only; PostgreSQL concurrency is tested separately."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Base, Payment, Review, Task, User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def seed(db):
    user = User(
        id=str(uuid4()),
        email="client@example.com",
        display_name="Client",
        password_hash="test-only-not-login",
        roles=["client"],
    )
    worker = User(
        id=str(uuid4()),
        email="worker@example.com",
        display_name="Worker",
        password_hash="test-only-not-login",
        roles=["worker"],
    )
    db.add_all([user, worker])
    db.flush()
    task = Task(
        owner_id=user.id,
        assigned_worker_id=worker.id,
        title="Public task",
        description="A description",
        category="Retail checks",
        city="Toronto",
        budget=3000,
    )
    db.add(task)
    db.commit()
    return user, worker, task


def test_one_payment_per_task(db):
    user, _, task = seed(db)
    for _ in range(2):
        db.add(Payment(task_id=task.id, owner_id=user.id, amount=3000, currency="CAD", provider="mock"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_review_constraints(db):
    user, worker, task = seed(db)
    db.add(
        Review(task_id=task.id, reviewer_id=user.id, worker_id=worker.id, rating=6, comment="Invalid rating")
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_budget_check_constraint(db):
    user, _, task = seed(db)
    task.budget = -1
    with pytest.raises(IntegrityError):
        db.commit()


def test_all_foreign_keys_resolve():
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.column is not None
