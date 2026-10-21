from datetime import UTC, datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.email_limits import (
    MAX_AUTH_RESULTS_LENGTH,
    MAX_BODY_LENGTH,
    MAX_MESSAGE_ID_LENGTH,
    MAX_RECIPIENTS,
    MAX_SENDER_NAME_LENGTH,
    MAX_SUBJECT_LENGTH,
    MAX_THREAD_ID_LENGTH,
)
from app.core.identity import validate_identity_email


def address(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid address")
    return validate_identity_email(value)


def optional_address(value: object) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return address(value)


def identifier(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid identifier")
    value = value.strip()
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid identifier")
    return value


def optional_identifier(value: object) -> str | None:
    return None if value is None else identifier(value)


def text_value(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Invalid text")
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def optional_text(value: object) -> str | None:
    return text_value(value).strip() or None


def recipients(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_RECIPIENTS:
        raise ValueError("Invalid recipient list")
    return list(dict.fromkeys(address(item) for item in value))


Address = Annotated[str, BeforeValidator(address), StringConstraints(max_length=320)]
OptionalAddress = Annotated[
    Annotated[str, StringConstraints(max_length=320)] | None, BeforeValidator(optional_address)
]
MessageID = Annotated[
    str, BeforeValidator(identifier), StringConstraints(max_length=MAX_MESSAGE_ID_LENGTH)
]
RecipientList = Annotated[list[Address], BeforeValidator(recipients)]


def to_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError, ValueError:
        raise ValueError("Invalid received_at") from None


UTCDateTime = Annotated[AwareDatetime, AfterValidator(to_utc)]


class EmailIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    message_id: MessageID
    thread_id: Annotated[
        Annotated[str, StringConstraints(max_length=MAX_THREAD_ID_LENGTH)] | None,
        BeforeValidator(optional_identifier),
    ] = None
    sender_name: Annotated[
        Annotated[str, StringConstraints(max_length=MAX_SENDER_NAME_LENGTH)] | None,
        BeforeValidator(optional_text),
    ] = None
    sender_email: Address
    reply_to: OptionalAddress = None
    return_path: OptionalAddress = None
    to_recipients: RecipientList = Field(default_factory=list)
    cc_recipients: RecipientList = Field(default_factory=list)
    subject: Annotated[
        str, BeforeValidator(text_value), StringConstraints(max_length=MAX_SUBJECT_LENGTH)
    ] = ""
    body_text: Annotated[
        str, BeforeValidator(text_value), StringConstraints(max_length=MAX_BODY_LENGTH)
    ] = ""
    authentication_results: Annotated[
        Annotated[str, StringConstraints(max_length=MAX_AUTH_RESULTS_LENGTH)] | None,
        BeforeValidator(optional_text),
    ] = None
    received_at: UTCDateTime

    @model_validator(mode="after")
    def combined_recipient_limit(self) -> Self:
        if len(self.to_recipients) + len(self.cc_recipients) > MAX_RECIPIENTS:
            raise ValueError("Too many recipients")
        return self

    @field_validator("received_at", mode="before")
    @classmethod
    def require_datetime_input(cls, value: object) -> str | datetime:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Expected an aware datetime")
        return value


class EmailSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: str
    sender_name: str | None
    sender_email: str
    reply_to: str | None
    subject: str
    received_at: AwareDatetime
    ingested_at: AwareDatetime


class EmailDetailResponse(EmailSummaryResponse):
    thread_id: str | None
    return_path: str | None
    to_recipients: list[str]
    cc_recipients: list[str]
    body_text: str
    authentication_results: str | None
