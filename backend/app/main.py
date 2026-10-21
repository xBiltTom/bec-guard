from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.email_analysis import router as analysis_router
from app.api.emails import router as emails_router
from app.api.health import router as health_router
from app.api.organizational_context import router as context_router
from app.core.config import AuthSettings, Settings
from app.core.database import create_database_engine, create_session_factory


def create_app(
    settings: Settings | None = None, auth_settings: AuthSettings | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.auth_settings = auth_settings or AuthSettings()
        app.state.engine = create_database_engine(settings or Settings())
        app.state.session_factory = create_session_factory(app.state.engine)
        try:
            yield
        finally:
            app.state.engine.dispose()

    application = FastAPI(title="BEC Guard API", version="0.1.0", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Pydantic errors can contain the original password/body; never reflect them.
        return JSONResponse(status_code=400, content={"detail": "Invalid request"})

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        # Do not return or log database connection details or credentials.
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(context_router)
    application.include_router(emails_router)
    application.include_router(analysis_router)
    return application


app = create_app()
