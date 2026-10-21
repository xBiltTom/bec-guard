from collections.abc import Callable, Iterable
from time import perf_counter

from pydantic import ValidationError

from app.evaluation.contracts import (
    DETECTION_THRESHOLD,
    CasePrediction,
    EvaluationMetadata,
    EvaluationResult,
)
from app.evaluation.metrics import (
    binary_metrics,
    hard_negative_metrics,
    latency_metrics,
    ratio,
    type_metrics,
)
from app.schemas.dataset import DatasetCase
from app.services.alerts import ALERT_THRESHOLD
from app.services.deterministic_analysis import AnalysisContext, assess_deterministically
from app.services.email_analysis import create_semantic_analyzer
from app.services.hybrid_scoring import combine_scores, resolve_bec_type
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError, SemanticAnalyzer


def evaluate(
    cases: Iterable[DatasetCase],
    context: AnalysisContext,
    metadata: EvaluationMetadata,
    *,
    allow_external_llm: bool = False,
    analyzer_factory: Callable[[], SemanticAnalyzer] = create_semantic_analyzer,
    detector: Callable = assess_deterministically,
    clock: Callable[[], float] = perf_counter,
) -> EvaluationResult:
    if metadata.mode == "hybrid" and not allow_external_llm:
        raise ValueError("Hybrid mode requires explicit external LLM consent")
    if metadata.thresholds != {"detection": DETECTION_THRESHOLD, "alert": ALERT_THRESHOLD}:
        raise ValueError("Evaluation thresholds must match the frozen policies")
    predictions = []
    for case in cases:
        if case.split != "holdout":
            continue
        start = clock()
        # Only normalized email and context cross the detector boundary.
        det = detector(case.email, context)
        score, kind, error = det.score, det.bec_type, None
        if metadata.mode == "hybrid":
            try:
                semantic = analyzer_factory().assess(case.email, det, context)
                score = combine_scores(det.score, semantic.risk_score)
                kind = resolve_bec_type(score, det, semantic)
            except ValidationError:
                score = kind = None
                error = LLMErrorCode.NOT_CONFIGURED.value
            except SemanticAnalysisError as failure:
                score = kind = None
                error = failure.code.value
        elapsed = max(0.0, (clock() - start) * 1000)
        # Annotation access occurs only after prediction (never input features).
        predictions.append(
            CasePrediction(
                case_id=case.case_id,
                ground_truth=case.label,
                expected_bec_type=case.expected_bec_type,
                predicted_positive_detection=None
                if score is None
                else score >= DETECTION_THRESHOLD,
                predicted_positive_alert=None if score is None else score >= ALERT_THRESHOLD,
                score=score,
                predicted_bec_type=kind,
                status="ERROR" if error else "COMPLETED",
                error_code=error,
                elapsed_ms=elapsed,
                is_hard_negative=case.is_hard_negative,
            )
        )
    completed = sum(c.status == "COMPLETED" for c in predictions)
    return EvaluationResult(
        **metadata.model_dump(),
        cases_total=len(predictions),
        completed=completed,
        errors=len(predictions) - completed,
        coverage=ratio(completed, len(predictions)),
        detection_metrics=binary_metrics(predictions),
        alert_metrics=binary_metrics(predictions, alert=True),
        hard_negatives=hard_negative_metrics(predictions),
        bec_types=type_metrics(predictions),
        latency=latency_metrics(predictions),
        cases=predictions,
    )
