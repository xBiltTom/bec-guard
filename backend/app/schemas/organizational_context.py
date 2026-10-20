from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

from app.core.context_validation import normalize_domain
from app.core.identity import validate_identity_email


def email_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid email")
    return validate_identity_email(value)


def domain_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid domain")
    return normalize_domain(value)


def optional_text(value: object) -> object:
    return (value.strip() or None) if isinstance(value, str) else value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Email = Annotated[str, BeforeValidator(email_value), StringConstraints(max_length=320)]
Domain = Annotated[str, BeforeValidator(domain_value), StringConstraints(max_length=253)]
Department = Annotated[
    str | None, StringConstraints(max_length=200), BeforeValidator(optional_text)
]
BankReference = Annotated[
    str | None, StringConstraints(max_length=256), BeforeValidator(optional_text)
]
OptionalEmail = Annotated[Email | None, BeforeValidator(optional_text)]


class ContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutiveContactCreate(ContextInput):
    name: Name
    position: Name
    department: Department = None
    email: Email
    is_active: bool = True


class VendorCreate(ContextInput):
    name: Name
    domain: Domain
    contact_email: OptionalEmail = None
    bank_account_reference: BankReference = None
    is_active: bool = True


class ContextUpdate(ContextInput):
    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        required = {"name", "position", "email", "domain", "is_active"}
        if any(getattr(self, field) is None for field in self.model_fields_set & required):
            raise ValueError("Required fields cannot be null")
        return self


class ExecutiveContactUpdate(ContextUpdate):
    name: Name | None = None
    position: Name | None = None
    department: Department = None
    email: Email | None = None
    is_active: bool | None = None


class VendorUpdate(ContextUpdate):
    name: Name | None = None
    domain: Domain | None = None
    contact_email: OptionalEmail = None
    bank_account_reference: BankReference = None
    is_active: bool | None = None


class ContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExecutiveContactResponse(ContextResponse):
    position: str
    department: str | None
    email: str


class VendorResponse(ContextResponse):
    domain: str
    contact_email: str | None
    bank_account_reference: str | None
