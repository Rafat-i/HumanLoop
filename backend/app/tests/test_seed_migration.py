import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select

from app.models.entities import Payment, Review, Task, User, WorkerProfile


async def test_demo_seed_is_repeatable_and_has_consistent_history(api_env, monkeypatch):
    from conftest import TestSession

    from app import cli

    monkeypatch.setattr(cli, "SessionFactory", lambda: TestSession(api_env["factory"]()))
    await cli.seed("test-only-demo-password")
    await cli.seed("different-test-password")
    with api_env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 5
        assert db.scalar(select(func.count()).select_from(WorkerProfile)) == 3
        assert db.scalar(select(func.count()).select_from(Task)) == 4
        assert db.scalar(select(func.count()).select_from(Review)) == 1
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert all(not p.identity_verified for p in db.scalars(select(WorkerProfile)))
        assert all(u.demo for u in db.scalars(select(User)))


def test_frozen_initial_migration_applies_and_reverts_on_sqlite():
    # app/tests -> backend/app -> backend
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location("migration_0001_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            assert "tasks" in inspect(connection).get_table_names()
            assert "api_keys" in inspect(connection).get_table_names()
            module.downgrade()
            assert not inspect(connection).get_table_names()
    engine.dispose()


async def test_showcase_uses_curated_demo_profiles_only(api_env, monkeypatch):
    from conftest import TestSession

    from app import cli

    monkeypatch.setattr(cli, "SessionFactory", lambda: TestSession(api_env["factory"]()))
    await cli.seed("fictional-showcase-password")
    client = api_env["client"]()
    rows = (await client.get("/api/v1/workers/showcase")).json()
    assert len(rows) == 3
    assert len({row["display_name"] for row in rows}) == 3
    assert len({row["city"] for row in rows}) == 3
    assert {row["available"] for row in rows} == {True, False}
    assert all(row["demo"] for row in rows)
