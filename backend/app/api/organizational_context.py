from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_session
from app.models import ExecutiveContact, Role, User, Vendor
from app.schemas.organizational_context import (
    ExecutiveContactCreate,
    ExecutiveContactResponse,
    ExecutiveContactUpdate,
    VendorCreate,
    VendorResponse,
    VendorUpdate,
)
from app.services.organizational_context import create_context, update_context

router = APIRouter(prefix="/api", tags=["Organizational context"])
Database = Annotated[Session, Depends(get_session)]
Reader = Annotated[User, Depends(require_roles(*Role))]
Writer = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _peer(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get[T: (ExecutiveContact, Vendor)](session: Session, model: type[T], resource_id: UUID) -> T:
    resource = session.get(model, resource_id)
    if resource is None:
        raise HTTPException(404, "Resource not found")
    return resource


def _list[T: (ExecutiveContact, Vendor)](
    session: Session, model: type[T], limit: int, offset: int, include_inactive: bool
) -> list[T]:
    statement = select(model)
    if not include_inactive:
        statement = statement.where(model.is_active.is_(True))
    return list(
        session.scalars(statement.order_by(model.created_at, model.id).limit(limit).offset(offset))
    )


@router.get("/executives", response_model=list[ExecutiveContactResponse])
def list_executives(
    session: Database,
    _actor: Reader,
    limit: Limit = 50,
    offset: Offset = 0,
    include_inactive: bool = False,
):
    return _list(session, ExecutiveContact, limit, offset, include_inactive)


@router.get("/executives/{resource_id}", response_model=ExecutiveContactResponse)
def get_executive(resource_id: UUID, session: Database, _actor: Reader):
    return _get(session, ExecutiveContact, resource_id)


@router.post("/executives", response_model=ExecutiveContactResponse, status_code=201)
def create_executive(
    body: ExecutiveContactCreate, session: Database, actor: Writer, request: Request
):
    return create_context(
        session, ExecutiveContact(**body.model_dump()), actor=actor, peer=_peer(request)
    )


@router.patch("/executives/{resource_id}", response_model=ExecutiveContactResponse)
def update_executive(
    resource_id: UUID,
    body: ExecutiveContactUpdate,
    session: Database,
    actor: Writer,
    request: Request,
):
    return update_context(
        session,
        _get(session, ExecutiveContact, resource_id),
        body.model_dump(exclude_unset=True),
        actor=actor,
        peer=_peer(request),
    )


@router.get("/vendors", response_model=list[VendorResponse])
def list_vendors(
    session: Database,
    _actor: Reader,
    limit: Limit = 50,
    offset: Offset = 0,
    include_inactive: bool = False,
):
    return _list(session, Vendor, limit, offset, include_inactive)


@router.get("/vendors/{resource_id}", response_model=VendorResponse)
def get_vendor(resource_id: UUID, session: Database, _actor: Reader):
    return _get(session, Vendor, resource_id)


@router.post("/vendors", response_model=VendorResponse, status_code=201)
def create_vendor(body: VendorCreate, session: Database, actor: Writer, request: Request):
    return create_context(session, Vendor(**body.model_dump()), actor=actor, peer=_peer(request))


@router.patch("/vendors/{resource_id}", response_model=VendorResponse)
def update_vendor(
    resource_id: UUID, body: VendorUpdate, session: Database, actor: Writer, request: Request
):
    return update_context(
        session,
        _get(session, Vendor, resource_id),
        body.model_dump(exclude_unset=True),
        actor=actor,
        peer=_peer(request),
    )
