"""Exact context lookups and atomic writes; no BEC decisions."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.context_validation import normalize_domain
from app.core.identity import validate_identity_email
from app.models import ExecutiveContact, User, Vendor
from app.services.audit import AuditAction, record_context_event


def find_executive_by_email(
    session: Session, email: str, *, include_inactive: bool = False
) -> ExecutiveContact | None:
    statement = select(ExecutiveContact).where(
        func.lower(ExecutiveContact.email) == validate_identity_email(email)
    )
    if not include_inactive:
        statement = statement.where(ExecutiveContact.is_active.is_(True))
    return session.scalar(statement)


def find_vendor_by_domain(
    session: Session, domain: str, *, include_inactive: bool = False
) -> Vendor | None:
    statement = select(Vendor).where(func.lower(Vendor.domain) == normalize_domain(domain))
    if not include_inactive:
        statement = statement.where(Vendor.is_active.is_(True))
    return session.scalar(statement)


def create_context[T: (ExecutiveContact, Vendor)](
    session: Session, resource: T, *, actor: User, peer: str | None = None
) -> T:
    session.add(resource)
    _persist(session, resource, actor=actor, peer=peer, suffix="CREATED")
    return resource


def update_context[T: (ExecutiveContact, Vendor)](
    session: Session,
    resource: T,
    changes: dict[str, object],
    *,
    actor: User,
    peer: str | None = None,
) -> T:
    changed = {field for field, value in changes.items() if getattr(resource, field) != value}
    if not changed:
        return resource
    for field in changed:
        setattr(resource, field, changes[field])
    suffix = "UPDATED"
    if "is_active" in changed:
        suffix = "REACTIVATED" if resource.is_active else "DEACTIVATED"
    _persist(session, resource, actor=actor, peer=peer, suffix=suffix, changed_fields=changed)
    return resource


def _persist(
    session: Session,
    resource: ExecutiveContact | Vendor,
    *,
    actor: User,
    peer: str | None,
    suffix: str,
    changed_fields: set[str] | None = None,
) -> None:
    kind = "executive" if isinstance(resource, ExecutiveContact) else "vendor"
    identity_index = (
        "uq_executive_contacts_email_lower" if kind == "executive" else "uq_vendors_domain_lower"
    )
    try:
        session.flush()
        record_context_event(
            session,
            AuditAction(f"{kind.upper()}_{suffix}"),
            actor=actor,
            resource_type=kind,
            resource_id=resource.id,
            changed_fields=changed_fields,
            peer=peer,
        )
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        if (
            isinstance(error, IntegrityError)
            and getattr(error.orig, "sqlstate", None) == "23505"
            and getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == identity_index
        ):
            raise HTTPException(409, "Organizational identity already exists") from None
        raise
