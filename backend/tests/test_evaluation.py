from datetime import UTC, datetime

import pytest

from app.evaluation.contracts import CasePrediction, EvaluationMetadata, EvaluationResult
from app.evaluation.metrics import (
    binary_metrics,
    hard_negative_metrics,
    latency_metrics,
    type_metrics,
)
from app.evaluation.runner import evaluate
from app.schemas.analysis import DeterministicAssessment, SemanticAssessment
from app.schemas.dataset import DatasetCase
from app.schemas.email import EmailIngestRequest
from app.services.deterministic_analysis import AnalysisContext
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError


def prediction(actual="BEC", score=70, *, hard=False, kind="OTHER", error=False, elapsed=1):
    return CasePrediction(
        case_id="ARTIFICIAL",
        ground_truth=actual,
        expected_bec_type="OTHER" if actual == "BEC" else None,
        predicted_positive_detection=None if error else score >= 40,
        predicted_positive_alert=None if error else score >= 70,
        score=None if error else score,
        predicted_bec_type=None if error else kind,
        status="ERROR" if error else "COMPLETED",
        error_code="LLM_TIMEOUT" if error else None,
        elapsed_ms=elapsed,
        is_hard_negative=hard,
    )


def metadata(mode="deterministic"):
    return EvaluationMetadata(
        mode=mode,
        generated_at=datetime.now(UTC),
        git_commit="a" * 40,
        dataset_sha256="b" * 64,
        context_sha256="c" * 64,
        policies={
            "deterministic": "det-v1",
            "semantic": "semantic-v1",
            "hybrid": "hybrid-v1",
            "alert": "alert-v1",
        },
        thresholds={"detection": 40, "alert": 70},
        detector_sha256={},
    )


def case(label="BEC", split="holdout"):
    return DatasetCase(
        case_id="ARTIFICIAL",
        split=split,
        label=label,
        expected_bec_type="OTHER" if label == "BEC" else None,
        email=EmailIngestRequest(
            message_id="<artificial@fixture.example>",
            sender_email="sender@fixture.example",
            subject="PRIVATE SUBJECT",
            body_text="PRIVATE BODY",
            received_at=datetime.now(UTC),
        ),
    )


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([prediction(), prediction("LEGITIMATE", 0)], (1, 1, 0, 0)),
        ([prediction("LEGITIMATE", 0)], (0, 1, 0, 0)),
        ([prediction(), prediction()], (2, 0, 0, 0)),
        ([prediction("LEGITIMATE", 80)], (0, 0, 1, 0)),
        ([prediction(score=0)], (0, 0, 0, 1)),
        ([], (0, 0, 0, 0)),
    ],
)
def test_binary_counts(rows, expected):
    result = binary_metrics(rows)
    assert (result.tp, result.tn, result.fp, result.fn) == expected
    assert "NaN" not in result.model_dump_json()


def test_metrics_formulas_and_zero_division():
    result = binary_metrics(
        [
            prediction(),
            prediction("LEGITIMATE", 0),
            prediction("LEGITIMATE", 50),
            prediction(score=0),
        ]
    )
    assert (
        result.precision
        == result.recall
        == result.f1
        == result.accuracy
        == result.specificity
        == result.false_positive_rate
        == 0.5
    )
    negatives = binary_metrics([prediction("LEGITIMATE", 0)])
    assert negatives.precision is negatives.recall is negatives.f1 is None
    assert negatives.accuracy == negatives.specificity == 1
    assert negatives.false_positive_rate == 0


@pytest.mark.parametrize(
    "score,detect,alert",
    [(39, False, False), (40, True, False), (69, True, False), (70, True, True)],
)
def test_thresholds(score, detect, alert):
    result = evaluate(
        [case()],
        AnalysisContext([], []),
        metadata(),
        detector=lambda email, context: DeterministicAssessment(
            score=score, signals=[], bec_type=None
        ),
    )
    assert result.cases[0].predicted_positive_detection is detect
    assert result.cases[0].predicted_positive_alert is alert


def test_hard_negatives_types_latency_and_serialization():
    rows = [
        prediction("LEGITIMATE", 50, hard=True, elapsed=1),
        prediction("LEGITIMATE", 0, hard=True, elapsed=2),
        prediction(elapsed=3),
        prediction(kind="VENDOR_FRAUD", elapsed=4),
        prediction(error=True, elapsed=5),
    ]
    hard = hard_negative_metrics(rows)
    assert hard.total == 2 and hard.false_positives_detection == 1 and hard.fpr_detection == 0.5
    assert hard.false_positives_alert == 0 and hard.fpr_alert == 0
    types = type_metrics(rows)
    assert types.total_bec == 3 and types.correct == 1 and types.accuracy == 1 / 3
    assert types.breakdown["OTHER"] == {
        "total": 3,
        "correct": 1,
        "incorrect": 1,
        "unclassified": 1,
        "errors": 1,
    }
    latency = latency_metrics(rows)
    assert latency.mean_ms == latency.median_ms == 3 and latency.p95_ms == 5
    assert latency_metrics([]).p95_ms is None
    result = evaluate(
        [case()],
        AnalysisContext([], []),
        metadata(),
        detector=lambda *_: DeterministicAssessment(score=40, signals=[], bec_type=None),
    )
    assert EvaluationResult.model_validate_json(result.model_dump_json()) == result
    for secret in (
        "PRIVATE BODY",
        "PRIVATE SUBJECT",
        "sender@fixture.example",
        "message_id",
        "body_text",
        "authentication_results",
    ):
        assert secret not in result.model_dump_json()


def test_metadata_only_read_after_detector():
    source = case()
    called = False

    class GuardedCase:
        split = source.split
        email = source.email

        def __getattr__(self, name):
            assert called, "Annotation read before prediction"
            return getattr(source, name)

    def detector(email, context):
        nonlocal called
        assert isinstance(email, EmailIngestRequest)
        assert (
            not {"label", "expected_bec_type", "split", "is_hard_negative"}
            & email.model_dump().keys()
        )
        called = True
        return DeterministicAssessment(score=80, signals=[], bec_type=None)

    result = evaluate([GuardedCase()], AnalysisContext([], []), metadata(), detector=detector)
    assert result.completed == 1


def test_development_not_assessed():
    def forbidden(*_):
        raise AssertionError("Development reached holdout evaluator")

    assert (
        evaluate(
            [case(split="development")], AnalysisContext([], []), metadata(), detector=forbidden
        ).cases_total
        == 0
    )


def test_hybrid_consent_before_factory():
    def forbidden():
        raise AssertionError("Factory called without consent")

    with pytest.raises(ValueError, match="consent"):
        evaluate([case()], AnalysisContext([], []), metadata("hybrid"), analyzer_factory=forbidden)


def test_hybrid_uses_production_policy_and_error_coverage():
    class Fake:
        calls = 0

        def assess(self, email, det, context):
            self.calls += 1
            if self.calls == 2:
                raise SemanticAnalysisError(LLMErrorCode.TIMEOUT)
            return SemanticAssessment(
                risk_score=0,
                bec_type=None,
                signals=[],
                summary="Artificial",
                recommended_action="Verify",
            )

    fake = Fake()
    result = evaluate(
        [case(), case()],
        AnalysisContext([], []),
        metadata("hybrid"),
        allow_external_llm=True,
        analyzer_factory=lambda: fake,
        detector=lambda *_: DeterministicAssessment(score=80, signals=[], bec_type="VENDOR_FRAUD"),
    )
    assert result.cases[0].score == 70 and result.cases[0].predicted_bec_type == "VENDOR_FRAUD"
    assert result.errors == 1 and result.completed == 1 and result.coverage == 0.5
    assert result.cases[1].score is result.cases[1].predicted_positive_detection is None
    assert result.detection_metrics.recall == 1 and result.detection_metrics.effective_recall == 0.5
    assert result.detection_metrics.fn == 0


@pytest.mark.parametrize("args", [[], ["--confirm-holdout", "--mode", "hybrid"]])
def test_cli_rejects_before_loading_or_provider(monkeypatch, tmp_path, args):
    from app.scripts import evaluate_holdout as cli

    monkeypatch.setattr(
        cli, "freeze_metadata", lambda *_: pytest.fail("Freeze called without consent")
    )
    argv = args if args else ["--mode", "deterministic"]
    with pytest.raises(SystemExit):
        cli.main([*argv, "--output-dir", str(tmp_path)])
    assert not list(tmp_path.iterdir())


def test_cli_writes_private_reproducible_artifacts(monkeypatch, tmp_path, capsys):
    import json

    from app.evaluation.provenance import sha256
    from app.scripts import evaluate_holdout as cli

    data = tmp_path / "artificial.jsonl"
    context_file = tmp_path / "artificial-context.json"
    data.write_text("artificial fixture, not the reserved corpus")
    context_file.write_text("{}")
    frozen = metadata()
    frozen.dataset_sha256 = sha256(data)
    frozen.context_sha256 = sha256(context_file)
    monkeypatch.setattr(cli, "freeze_metadata", lambda *_: frozen)
    monkeypatch.setattr(cli, "load_dataset", lambda *_: [case()])
    monkeypatch.setattr(cli, "load_synthetic_context", lambda *_: AnalysisContext([], []))
    monkeypatch.setattr(
        cli,
        "evaluate",
        lambda cases, context, metadata, **_: evaluate(
            cases,
            context,
            metadata,
            detector=lambda *_: DeterministicAssessment(score=70, signals=[], bec_type=None),
        ),
    )
    output = tmp_path / "output"
    assert (
        cli.main(
            [
                "--mode",
                "deterministic",
                "--confirm-holdout",
                "--dataset",
                str(data),
                "--context",
                str(context_file),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    [run] = output.iterdir()
    assert {p.name for p in run.iterdir()} == {"freeze.json", "result.json", "predictions.json"}
    assert json.loads((run / "result.json").read_text())["completed"] == 1
    assert json.loads((run / "freeze.json").read_text())["git_commit"] == frozen.git_commit
    all_output = capsys.readouterr().out + "".join(p.read_text() for p in run.iterdir())
    for forbidden in ("PRIVATE BODY", "PRIVATE SUBJECT", "sender@fixture.example", "body_text"):
        assert forbidden not in all_output
