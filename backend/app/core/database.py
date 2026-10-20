from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=3000 -c timezone=UTC -c search_path=public",
        },
        hide_parameters=True,
    )


def get_connection(request: Request) -> Iterator[Connection]:
    with request.app.state.engine.connect() as connection:
        yield connection


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    # The caller owns commit; closing rolls back any unfinished transaction.
    with request.app.state.session_factory() as session:
        yield session
