import pytest

from app.models.enums import BECType, RiskLevel
from app.schemas.analysis import DeterministicAssessment, SemanticAssessment
from app.services.hybrid_scoring import combine_scores, resolve_bec_type, risk_level


@pytest.mark.parametrize(
    "det,sem,expected",
    [
        (0, 0, 0),
        (0, 100, 50),
        (100, 0, 70),
        (70, 0, 70),
        (69, 0, 35),
        (60, 80, 70),
        (90, 90, 90),
        (100, 100, 100),
        (8, 9, 9),
    ],
)
def test_combine_scores(det, sem, expected):
    assert combine_scores(det, sem) == expected


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, RiskLevel.LOW),
        (39, RiskLevel.LOW),
        (40, RiskLevel.MEDIUM),
        (69, RiskLevel.MEDIUM),
        (70, RiskLevel.HIGH),
        (84, RiskLevel.HIGH),
        (85, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_thresholds(score, expected):
    assert risk_level(score) == expected


@pytest.mark.parametrize("score", [-1, 101, True, 2.5, "50", None])
def test_invalid_scores(score):
    with pytest.raises(ValueError):
        risk_level(score)
    with pytest.raises(ValueError):
        combine_scores(score, 10)
    with pytest.raises(ValueError):
        combine_scores(10, score)


def test_type_resolution():
    det = DeterministicAssessment(score=50, bec_type=BECType.VENDOR_FRAUD, signals=[])
    sem = SemanticAssessment(
        risk_score=80,
        bec_type=BECType.OTHER,
        signals=[],
        summary="Evidence",
        recommended_action="Verify",
    )
    assert resolve_bec_type(39, det, sem) is None
    assert resolve_bec_type(40, det, sem) == BECType.VENDOR_FRAUD
    det.bec_type = None
    assert resolve_bec_type(70, det, sem) == BECType.OTHER
    sem.bec_type = None
    assert resolve_bec_type(70, det, sem) is None
