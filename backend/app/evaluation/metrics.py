"""Direct, defined-denominator metrics; ERROR predictions never become negatives."""

from math import ceil
from statistics import mean, median

from app.evaluation.contracts import (
    BinaryMetrics,
    CasePrediction,
    HardNegativeMetrics,
    LatencyMetrics,
    TypeMetrics,
)
from app.models.enums import BECType


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def binary_metrics(cases: list[CasePrediction], *, alert: bool = False) -> BinaryMetrics:
    tp = tn = fp = fn = 0
    for case in cases:
        if case.status != "COMPLETED":
            continue
        positive = case.predicted_positive_alert if alert else case.predicted_positive_detection
        actual = case.ground_truth == "BEC"
        tp += int(actual and positive is True)
        tn += int(not actual and positive is False)
        fp += int(not actual and positive is True)
        fn += int(actual and positive is False)
    return BinaryMetrics(
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        precision=ratio(tp, tp + fp),
        recall=ratio(tp, tp + fn),
        f1=ratio(2 * tp, 2 * tp + fp + fn),
        accuracy=ratio(tp + tn, tp + tn + fp + fn),
        specificity=ratio(tn, tn + fp),
        false_positive_rate=ratio(fp, fp + tn),
        effective_recall=ratio(tp, sum(c.ground_truth == "BEC" for c in cases)),
    )


def hard_negative_metrics(cases: list[CasePrediction]) -> HardNegativeMetrics:
    hard = [c for c in cases if c.is_hard_negative]
    completed = [c for c in hard if c.status == "COMPLETED"]
    detection = sum(c.predicted_positive_detection is True for c in completed)
    alert = sum(c.predicted_positive_alert is True for c in completed)
    return HardNegativeMetrics(
        total=len(hard),
        completed=len(completed),
        errors=len(hard) - len(completed),
        false_positives_detection=detection,
        false_positives_alert=alert,
        fpr_detection=ratio(detection, len(completed)),
        fpr_alert=ratio(alert, len(completed)),
    )


def type_metrics(cases: list[CasePrediction]) -> TypeMetrics:
    attacks = [c for c in cases if c.ground_truth == "BEC"]
    breakdown = {}
    for kind in BECType:
        group = [c for c in attacks if c.expected_bec_type == kind]
        correct = sum(c.predicted_bec_type == kind for c in group)
        missing = sum(c.predicted_bec_type is None for c in group)
        breakdown[kind.value] = {
            "total": len(group),
            "correct": correct,
            "incorrect": len(group) - correct - missing,
            "unclassified": missing,
            "errors": sum(c.status == "ERROR" for c in group),
        }
    correct = sum(v["correct"] for v in breakdown.values())
    return TypeMetrics(
        total_bec=len(attacks),
        correct=correct,
        accuracy=ratio(correct, len(attacks)),
        breakdown=breakdown,
    )


def latency_metrics(cases: list[CasePrediction]) -> LatencyMetrics:
    values = sorted(c.elapsed_ms for c in cases)
    return LatencyMetrics(
        mean_ms=mean(values) if values else None,
        median_ms=median(values) if values else None,
        p95_ms=values[ceil(0.95 * len(values)) - 1] if values else None,
    )
