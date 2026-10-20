from collections.abc import Iterator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import get_connection
from app.main import create_app


def make_app():
    # Unit tests override the database boundary; no server or real secret required.
    return create_app(
        Settings(
            _env_file=None,
            postgres_db="unit_test",
            postgres_user="unit_test",
            postgres_password="unit-test-only",
        )
    )


def test_health_checks_database_and_returns_contract():
    app = make_app()
    connection = MagicMock(spec=Connection)
    app.dependency_overrides[get_connection] = lambda: connection

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "bec-guard-api"}
    connection.execute.assert_called_once()
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"


def test_health_returns_503_without_database_error_details():
    app = make_app()
    connection = MagicMock(spec=Connection)
    connection.execute.side_effect = OperationalError("SELECT 1", {}, Exception("private detail"))
    app.dependency_overrides[get_connection] = lambda: connection

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "private detail" not in response.text


def test_health_handles_failure_acquiring_connection():
    app = make_app()

    def unavailable_connection() -> Iterator[Connection]:
        raise OperationalError("connect", {}, Exception("private connection detail"))
        yield  # pragma: no cover

    app.dependency_overrides[get_connection] = unavailable_connection
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
