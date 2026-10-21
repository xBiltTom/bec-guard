"""Evaluation metadata only. Never imported by production ingestion or SQL models."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.email import EmailIngestRequest


class DatasetLabel(StrEnum):
    LEGITIMATE = "LEGITIMATE"
    BEC = "BEC"


class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    HOLDOUT = "holdout"


class ExpectedBECType(StrEnum):
    EXECUTIVE_IMPERSONATION = "EXECUTIVE_IMPERSONATION"
    VENDOR_FRAUD = "VENDOR_FRAUD"
    BANK_ACCOUNT_CHANGE = "BANK_ACCOUNT_CHANGE"
    SENSITIVE_DATA_REQUEST = "SENSITIVE_DATA_REQUEST"
    OTHER = "OTHER"


class DatasetCase(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    case_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    split: DatasetSplit
    label: DatasetLabel
    expected_bec_type: ExpectedBECType | None
    is_hard_negative: bool = False
    email: EmailIngestRequest

    @model_validator(mode="after")
    def metadata_consistency(self) -> Self:
        if (self.label == DatasetLabel.LEGITIMATE) != (self.expected_bec_type is None):
            raise ValueError("Label and expected type are inconsistent")
        if self.is_hard_negative and self.label != DatasetLabel.LEGITIMATE:
            raise ValueError("Only legitimate cases can be hard negatives")
        return self
