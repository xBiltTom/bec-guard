import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.database import create_session_factory
from app.models import User


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Integration tests require TEST_DATABASE_URL; see docs/persistence.md")
    url = make_url(raw_url)
    if url.drivername != "postgresql+psycopg" or not (
        url.database == "bec_guard_test" or (url.database or "").startswith("bec_guard_test_")
    ):
        pytest.fail("TEST_DATABASE_URL must point to a PostgreSQL bec_guard_test[_...] database")

    engine = create_engine(
        url,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c search_path=public"},
    )
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if "n8n" in inspector.get_schema_names():
                pytest.fail("Test database must not contain the n8n schema")
            tables = set(inspector.get_table_names(schema="public"))
            if tables - {"alembic_version"}:
                pytest.fail("Test database public schema must be empty before the suite")
            if "alembic_version" in tables:
                if connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).first():
                    pytest.fail("Test database must be at Alembic base before the suite")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def migration_runner(test_engine):
    def run(operation, revision=None):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            if revision is None:
                operation(config)
            else:
                operation(config, revision)

    return run


@pytest.fixture(scope="session")
def migrated_engine(test_engine, migration_runner) -> Iterator[Engine]:
    migration_runner(command.upgrade, "head")
    try:
        yield test_engine
    finally:
        # Only the guarded, initially empty test database is reverted.
        migration_runner(command.downgrade, "base")


@pytest.fixture
def db_session(migrated_engine) -> Iterator[Session]:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        try:
            yield session
        finally:
            session.rollback()
            with migrated_engine.begin() as connection:
                connection.execute(delete(User))
