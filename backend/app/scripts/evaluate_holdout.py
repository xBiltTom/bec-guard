"""Explicit academic evaluation; no HTTP endpoint, database writes or email content output."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import LLMSettings
from app.evaluation.provenance import freeze_metadata, sha256
from app.evaluation.runner import evaluate
from app.scripts.check_development import DEFAULT_CONTEXT_PATH, load_synthetic_context
from app.services.dataset import DEFAULT_DATASET_PATH, load_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["deterministic", "hybrid"], required=True)
    parser.add_argument("--confirm-holdout", action="store_true")
    parser.add_argument("--allow-external-llm", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.confirm_holdout:
        parser.error("--confirm-holdout is required; no evaluation was started")
    if args.mode == "hybrid" and not args.allow_external_llm:
        parser.error("hybrid requires --allow-external-llm; no provider was initialized")
    try:
        metadata = freeze_metadata(args.mode, args.dataset, args.context)
        cases = load_dataset(args.dataset)
        context = load_synthetic_context(args.context)
        if args.mode == "hybrid":
            settings = LLMSettings()
            metadata.provider = settings.llm_provider.strip().lower() or None
            metadata.model = settings.llm_model.strip() or None
        output = args.output_dir / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        )
        output.mkdir(parents=True, exist_ok=False)
        (output / "freeze.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        result = evaluate(cases, context, metadata, allow_external_llm=args.allow_external_llm)
        if (
            sha256(args.dataset) != metadata.dataset_sha256
            or sha256(args.context) != metadata.context_sha256
        ):
            raise ValueError("Inputs changed during evaluation")
        summary = result.model_dump(mode="json", exclude={"cases"})
        (output / "result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        (output / "predictions.json").write_text(
            json.dumps(
                [c.model_dump(mode="json") for c in result.cases], indent=2, allow_nan=False
            ),
            encoding="utf-8",
        )
    except OSError, ValueError, ValidationError, subprocess.SubprocessError:
        print("Evaluation could not be completed; verify configuration and frozen inputs.")
        return 1
    print(
        json.dumps(
            {**summary, "artifact_directory": str(output)},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
