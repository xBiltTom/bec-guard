from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import BECType

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
