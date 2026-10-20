"""Register domain models in the shared metadata used by Alembic."""

from app.models.base import Base
from app.models.enums import Role
from app.models.user import User

__all__ = ["Base", "Role", "User"]
