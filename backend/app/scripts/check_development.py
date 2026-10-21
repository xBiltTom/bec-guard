"""Development-only regression. No persistence, bodies in output, or holdout scoring."""

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

from pydantic import ValidationError

from app.models import ExecutiveContact, Vendor
from app.schemas.dataset import DatasetCase, DatasetSplit
from app.services.dataset import DEFAULT_DATASET_PATH, DatasetValidationError, load_dataset
from app.services.deterministic_analysis import AnalysisContext, assess_deterministically
from app.services.email_analysis import POLICY_VERSION, create_semantic_analyzer
from app.services.hybrid_scoring import combine_scores, risk_level
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError, SemanticAnalyzer

DEFAULT_CONTEXT_PATH = DEFAULT_DATASET_PATH.with_name("context.json")


def load_synthetic_context(path: Path = DEFAULT_CONTEXT_PATH) -> AnalysisContext:
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalysisContext(
        [ExecutiveContact(**e) for e in data["executives"]],
        [Vendor(**v) for v in data["vendors"]],
    )


def check_development(
    cases: Iterable[DatasetCase],
    context: AnalysisContext,
    analyzer_factory: Callable[[], SemanticAnalyzer] | None = None,
) -> dict:
    scores: dict[str, list[int]] = defaultdict(list)
    levels, signals, errors, hard_negatives = Counter(), Counter(), Counter(), Counter()
    total = 0
    for case in cases:
        # Filter BEFORE reading labels or passing any email to either engine.
        if case.split != DatasetSplit.DEVELOPMENT:
            continue
        total += 1
        det = assess_deterministically(case.email, context)
        signals.update(s.code for s in det.signals)
        score = det.score
        if analyzer_factory is not None:
            try:
                semantic = analyzer_factory().assess(case.email, det, context)
            except ValidationError:
                errors[LLMErrorCode.NOT_CONFIGURED.value] += 1
                continue
            except SemanticAnalysisError as error:
                errors[error.code.value] += 1
                continue
            score = combine_scores(det.score, semantic.risk_score)
        scores[case.label.value].append(score)
        level = risk_level(score).value
        levels[level] += 1
        if case.is_hard_negative:
            hard_negatives[level] += 1
    return {
        "split": "development",
        "total": total,
        "policy_version": POLICY_VERSION,
        "mode": "hybrid" if analyzer_factory else "deterministic",
        "scores_by_label": {
            label: {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": round(sum(values) / len(values), 2),
            }
            for label, values in sorted(scores.items())
        },
        "risk_levels": dict(sorted(levels.items())),
        "hard_negative_levels": dict(sorted(hard_negatives.items())),
        "signals": dict(sorted(signals.items())),
        "errors": dict(sorted(errors.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT_PATH)
    parser.add_argument("--llm", action="store_true", help="Explicitly allow paid provider calls")
    args = parser.parse_args()
    try:
        # The existing loader performs approved structural validation over the full
        # file. Only development is ever assessed or summarized by this harness.
        cases = load_dataset(args.dataset)
        result = check_development(
            cases,
            load_synthetic_context(args.context),
            create_semantic_analyzer if args.llm else None,
        )
    except OSError, ValueError, KeyError, TypeError, DatasetValidationError:
        print("Invalid development dataset or synthetic context")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
