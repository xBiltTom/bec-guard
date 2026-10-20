"""Register domain models in the shared metadata used by Alembic."""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.enums import Role
from app.models.executive_contact import ExecutiveContact
from app.models.user import User
from app.models.vendor import Vendor

__all__ = ["AuditLog", "Base", "ExecutiveContact", "Role", "User", "Vendor"]
