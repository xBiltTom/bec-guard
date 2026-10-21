from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import AnalysisStatus, BECType, RiskLevel

Score = Annotated[int, Field(strict=True, ge=0, le=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    description: Description
    source: Literal["RULE", "CONTEXT", "SEMANTIC"]
    contribution: Score = 0


class DeterministicAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: Score
    signals: list[Signal]
    bec_type: BECType | None
    policy_version: str = "det-v1"


class SemanticSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    description: Description
    source: Literal["SEMANTIC"]

    @field_validator("description")
    @classmethod
    def reject_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Invalid description")
        return value


class SemanticAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    risk_score: Score
    bec_type: BECType | None
    signals: list[SemanticSignal] = Field(max_length=8)
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    recommended_action: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
    ]

    @field_validator("summary", "recommended_action")
    @classmethod
    def reject_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Invalid semantic text")
        return value


class EmailAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_id: UUID
    status: AnalysisStatus
    deterministic_score: Score
    semantic_score: Score | None
    risk_score: Score | None
    risk_level: RiskLevel | None
    bec_type: BECType | None
    signals: list[Signal]
    summary: str | None
    recommended_action: str | None
    provider: str | None
    model: str | None
    policy_version: str
    error_code: str | None
    analyzed_at: AwareDatetime
