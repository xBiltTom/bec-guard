from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )


def get_connection(request: Request) -> Iterator[Connection]:
    with request.app.state.engine.connect() as connection:
        yield connection
