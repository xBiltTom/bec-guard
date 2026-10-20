from enum import StrEnum
from ipaddress import ip_address as parse_ip

from sqlalchemy.orm import Session

from app.models import AuditLog, User


class AuditAction(StrEnum):
    ADMIN_BOOTSTRAPPED = "ADMIN_BOOTSTRAPPED"
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_INACTIVE = "LOGIN_INACTIVE"
    RBAC_DENIED = "RBAC_DENIED"


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
