from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text

from app.core.database import get_connection
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(connection: Annotated[Connection, Depends(get_connection)]) -> HealthResponse:
    connection.execute(text("SELECT 1"))
    return HealthResponse()
