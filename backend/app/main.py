from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router as health_router
from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_database_engine(settings or Settings())
        app.state.session_factory = create_session_factory(app.state.engine)
        try:
            yield
        finally:
            app.state.engine.dispose()

    application = FastAPI(title="BEC Guard API", version="0.1.0", lifespan=lifespan)

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        # Do not return or log database connection details or credentials.
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    application.include_router(health_router)
    return application


app = create_app()
