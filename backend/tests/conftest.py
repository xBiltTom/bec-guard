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

from app.core.config import AuthSettings, LLMSettings, Settings
from app.core.database import create_session_factory, get_session
from app.core.passwords import hash_password
from app.main import create_app
from app.models import Role, User
from app.schemas.analysis import SemanticAssessment
from app.services.semantic_analysis import SemanticAnalysisError


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
                connection.execute(
                    text(
                        "TRUNCATE public.audit_log, public.users, "
                        "public.executive_contacts, public.vendors, public.emails, "
                        "public.email_analysis, public.bec_alerts"
                    )
                )


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


@pytest.fixture
def email_payload():
    return {
        "message_id": "<MiXeD-unit@fixtures.becguard.example>",
        "thread_id": "conversation-1",
        "sender_name": "  Nora Prisma  ",
        "sender_email": " NORA@LUMINARIA.EXAMPLE ",
        "reply_to": " REPLY@LUMINARIA.EXAMPLE ",
        "return_path": " BOUNCE@LUMINARIA.EXAMPLE ",
        "to_recipients": [
            " FINANZAS@LUMINARIA.EXAMPLE ",
            "finanzas@luminaria.example",
            "team@luminaria.example",
        ],
        "cc_recipients": [" CC@LUMINARIA.EXAMPLE ", "cc@luminaria.example"],
        "subject": "Asunto PRIVADO sin análisis",
        "body_text": "Contenido PRIVADO\r\nSegunda línea\x00\rTercera línea",
        "authentication_results": "mx.luminaria.example; spf=pass",
        "received_at": "2026-10-20T09:30:00-05:00",
    }


@pytest.fixture
def analysis_stub():
    class Analyzer:
        settings = LLMSettings(_env_file=None, llm_provider="openai", llm_model="unit-test-model")
        score = 90
        calls = 0
        failure = None
        entered = None
        release = None

        def assess(self, email, deterministic, context):
            self.calls += 1
            if self.entered:
                self.entered.set()
                assert self.release.wait(10)
            if self.failure:
                raise SemanticAnalysisError(self.failure)
            return SemanticAssessment(
                risk_score=self.score,
                bec_type="OTHER",
                signals=[],
                summary="Resultado controlado de pruebas.",
                recommended_action="Verificar identidad.",
            )

    return Analyzer()


@pytest.fixture
def alert_setup(db_session, account, email_payload, auth_settings, api_app, analysis_stub):
    from datetime import UTC, datetime

    from app.api.email_analysis import get_analyzer_factory
    from app.core.tokens import create_access_token
    from app.models import EmailAnalysis
    from app.schemas.email import EmailIngestRequest
    from app.services.email_ingestion import ingest_email
    from app.services.hybrid_scoring import risk_level

    email = ingest_email(db_session, EmailIngestRequest(**email_payload), actor=account)
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: analysis_stub
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}

    def assessment(score=70, status="COMPLETED"):
        row = EmailAnalysis(
            email_id=email.id,
            status=status,
            deterministic_score=100,
            semantic_score=score if status == "COMPLETED" else None,
            risk_score=score if status == "COMPLETED" else None,
            risk_level=risk_level(score) if status == "COMPLETED" else None,
            bec_type=None,
            signals=[],
            summary="Test" if status == "COMPLETED" else None,
            recommended_action="Verify" if status == "COMPLETED" else None,
            provider="openai",
            model="unit-test-model",
            policy_version="det-v1/semantic-v1/hybrid-v1",
            error_code="LLM_TIMEOUT" if status == "ERROR" else None,
            analyzed_at=datetime.now(UTC),
        )
        db_session.add(row)
        db_session.commit()
        return row

    return email, assessment, headers
