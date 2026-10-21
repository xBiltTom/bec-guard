"""Load the fixed synthetic corpus without network, database writes or classification."""

import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.schemas.dataset import DatasetCase

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[3] / "datasets" / "bec_eval.jsonl"
EXPECTED_SPLITS = {
    ("development", "LEGITIMATE"): 70,
    ("development", "BEC"): 28,
    ("holdout", "LEGITIMATE"): 30,
    ("holdout", "BEC"): 12,
}
EXPECTED_TYPES = {
    "EXECUTIVE_IMPERSONATION": 12,
    "VENDOR_FRAUD": 10,
    "BANK_ACCOUNT_CHANGE": 8,
    "SENSITIVE_DATA_REQUEST": 6,
    "OTHER": 4,
}


class DatasetValidationError(ValueError):
    """Content-free validation error suitable for CLI output."""


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[DatasetCase]:
    cases: list[DatasetCase] = []
    case_ids: set[str] = set()
    message_ids: set[str] = set()
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    case = DatasetCase.model_validate_json(line)
                except ValidationError:
                    raise DatasetValidationError(f"Invalid dataset row {line_number}") from None
                if case.case_id in case_ids or case.email.message_id in message_ids:
                    raise DatasetValidationError(f"Duplicate identity at row {line_number}")
                addresses = [
                    case.email.sender_email,
                    *case.email.to_recipients,
                    *case.email.cc_recipients,
                ]
                addresses += [
                    value for value in (case.email.reply_to, case.email.return_path) if value
                ]
                if any(
                    not value.rsplit("@", 1)[1].endswith((".example", ".test"))
                    for value in addresses
                ):
                    raise DatasetValidationError(f"Non-reserved address at row {line_number}")
                links = re.findall(
                    r"https?://[^\s<>\"']+",
                    case.email.subject + "\n" + case.email.body_text,
                    flags=re.I,
                )
                try:
                    hosts = [urlsplit(link).hostname or "" for link in links]
                except ValueError:
                    raise DatasetValidationError(
                        f"Invalid synthetic URL at row {line_number}"
                    ) from None
                if any(not host.endswith((".example", ".test")) for host in hosts):
                    raise DatasetValidationError(f"Non-reserved URL at row {line_number}")
                case_ids.add(case.case_id)
                message_ids.add(case.email.message_id)
                cases.append(case)
    except OSError, UnicodeError:
        raise DatasetValidationError("Dataset cannot be read as UTF-8") from None
    if Counter((case.split, case.label) for case in cases) != EXPECTED_SPLITS:
        raise DatasetValidationError(
            "Dataset must contain 140 cases with the approved label/split counts"
        )
    if Counter(case.expected_bec_type for case in cases if case.label == "BEC") != EXPECTED_TYPES:
        raise DatasetValidationError("Unexpected BEC type counts")
    if sum(case.is_hard_negative for case in cases) < 20:
        raise DatasetValidationError("Dataset must contain at least 20 legitimate hard negatives")
    return cases


def dataset_summary(cases: list[DatasetCase]) -> dict[str, object]:
    return {
        "total": len(cases),
        "labels": dict(Counter(case.label.value for case in cases)),
        "splits": dict(Counter(case.split.value for case in cases)),
        "bec_types": dict(
            Counter(case.expected_bec_type.value for case in cases if case.expected_bec_type)
        ),
        "hard_negatives": sum(case.is_hard_negative for case in cases),
    }
