from enum import StrEnum
from ipaddress import ip_address as parse_ip
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog, User


class AuditAction(StrEnum):
    ADMIN_BOOTSTRAPPED = "ADMIN_BOOTSTRAPPED"
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_INACTIVE = "LOGIN_INACTIVE"
    RBAC_DENIED = "RBAC_DENIED"
    EXECUTIVE_CREATED = "EXECUTIVE_CREATED"
    EXECUTIVE_UPDATED = "EXECUTIVE_UPDATED"
    EXECUTIVE_DEACTIVATED = "EXECUTIVE_DEACTIVATED"
    EXECUTIVE_REACTIVATED = "EXECUTIVE_REACTIVATED"
    VENDOR_CREATED = "VENDOR_CREATED"
    VENDOR_UPDATED = "VENDOR_UPDATED"
    VENDOR_DEACTIVATED = "VENDOR_DEACTIVATED"
    VENDOR_REACTIVATED = "VENDOR_REACTIVATED"


class AuditReason(StrEnum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"
    ROLE_NOT_ALLOWED = "ROLE_NOT_ALLOWED"


def record_security_event(
    session: Session,
    action: AuditAction,
    *,
    actor: User | None = None,
    peer: str | None = None,
    reason: AuditReason | None = None,
) -> AuditLog:
    # Accept only fixed internal metadata, never request bodies or arbitrary details.
    if not isinstance(action, AuditAction) or (
        reason is not None and not isinstance(reason, AuditReason)
    ):
        raise ValueError("Security audit metadata must use predefined events and reasons")
    try:
        address = str(parse_ip(peer)) if peer else None
    except ValueError:
        address = None
    event = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action.value,
        resource_type="user" if actor else None,
        resource_id=actor.id if actor else None,
        ip_address=address,
        details={"reason": reason.value} if reason else None,
    )
    session.add(event)
    return event


CONTEXT_FIELDS = {
    "executive": {"name", "position", "department", "email", "is_active"},
    "vendor": {"name", "domain", "contact_email", "bank_account_reference", "is_active"},
}


def record_context_event(
    session: Session,
    action: AuditAction,
    *,
    actor: User,
    resource_type: str,
    resource_id: UUID,
    changed_fields: set[str] | None = None,
    peer: str | None = None,
) -> AuditLog:
    # Only allow field NAMES. No values or arbitrary request details reach JSONB.
    if (
        resource_type not in CONTEXT_FIELDS
        or not isinstance(action, AuditAction)
        or action.value
        not in {
            f"{resource_type.upper()}_{suffix}"
            for suffix in ("CREATED", "UPDATED", "DEACTIVATED", "REACTIVATED")
        }
        or (changed_fields is not None and not changed_fields <= CONTEXT_FIELDS[resource_type])
    ):
        raise ValueError("Invalid context audit metadata")
    try:
        address = str(parse_ip(peer)) if peer else None
    except ValueError:
        address = None
    event = AuditLog(
        actor_user_id=actor.id,
        actor_role=actor.role,
        action=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=address,
        details={"changed_fields": ",".join(sorted(changed_fields))} if changed_fields else None,
    )
    session.add(event)
    return event
