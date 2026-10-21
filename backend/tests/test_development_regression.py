from types import SimpleNamespace

from app.schemas.analysis import SemanticAssessment
from app.scripts.check_development import check_development, load_synthetic_context
from app.services.dataset import load_dataset
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError


def test_development_regression_and_hard_negatives():
    result = check_development(load_dataset(), load_synthetic_context())
    assert result["total"] == 98 and result["mode"] == "deterministic"
    assert result["scores_by_label"]["LEGITIMATE"]["count"] == 70
    assert result["scores_by_label"]["BEC"]["count"] == 28
    assert result["hard_negative_levels"] == {"LOW": 21}
    assert result["errors"] == {}


def test_holdout_never_reaches_engines_or_label_access():
    class ReservedCase:
        split = "holdout"

        def __getattr__(self, _name):
            raise AssertionError("Reserved holdout data was accessed")

    def forbidden_factory():
        raise AssertionError("Holdout must not invoke a model")

    result = check_development([ReservedCase()], load_synthetic_context(), forbidden_factory)
    assert result["total"] == 0 and result["scores_by_label"] == {}
    assert result["risk_levels"] == {} and result["errors"] == {}


def test_optional_llm_failure_has_no_fallback_low():
    development = [case for case in load_dataset() if case.split == "development"]

    def fail(*_args):
        raise SemanticAnalysisError(LLMErrorCode.TIMEOUT)

    result = check_development(
        development, load_synthetic_context(), lambda: SimpleNamespace(assess=fail)
    )
    assert result["total"] == 98
    assert result["errors"] == {"LLM_TIMEOUT": 98}
    assert result["risk_levels"] == {} and result["scores_by_label"] == {}


def test_optional_hybrid_uses_only_email_input():
    inputs = []

    def assess(email, _det, _context):
        assert not hasattr(email, "label") and not hasattr(email, "split")
        inputs.append(email.message_id)
        return SemanticAssessment(
            risk_score=20,
            bec_type=None,
            signals=[],
            summary="Evaluación fake",
            recommended_action="Revisar",
        )

    result = check_development(
        load_dataset(), load_synthetic_context(), lambda: SimpleNamespace(assess=assess)
    )
    assert len(inputs) == result["total"] == 98
    assert result["mode"] == "hybrid" and result["errors"] == {}
