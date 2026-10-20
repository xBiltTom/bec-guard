from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    MANAGER = "MANAGER"
    AUDITOR = "AUDITOR"
