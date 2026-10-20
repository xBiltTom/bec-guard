import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import AuthSettings, Settings
from app.core.database import create_session_factory, get_session
from app.core.passwords import hash_password
from app.main import create_app
from app.models import Role, User


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
                # Guarded, disposable test DB only. Do not disable the audit trigger.
                connection.execute(text("TRUNCATE public.audit_log, public.users"))


@pytest.fixture(scope="session")
def auth_settings():
    return AuthSettings(_env_file=None, jwt_secret_key=secrets.token_urlsafe(48))


@pytest.fixture
def api_app(db_session, migrated_engine, auth_settings):
    application = create_app(
        Settings(
            _env_file=None,
            postgres_db="unit_test",
            postgres_user="unit_test",
            postgres_password="test-only",
        ),
        auth_settings,
    )

    def session_override():
        with create_session_factory(migrated_engine)() as session:
            yield session

    application.dependency_overrides[get_session] = session_override
    return application


@pytest.fixture
def api_client(api_app):
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def account(db_session):
    user = User(
        name="Test Analyst",
        email="analyst@example.com",
        password_hash=hash_password("a long test password"),
        role=Role.ANALYST,
    )
    db_session.add(user)
    db_session.commit()
    return user
