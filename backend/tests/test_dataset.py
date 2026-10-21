import json
import re
from collections import Counter
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from app.schemas.email import EmailIngestRequest
from app.schemas.organizational_context import ExecutiveContactCreate, VendorCreate
from app.scripts.validate_dataset import main
from app.services.dataset import (
    DEFAULT_DATASET_PATH,
    EXPECTED_SPLITS,
    EXPECTED_TYPES,
    DatasetValidationError,
    dataset_summary,
    load_dataset,
)


@pytest.fixture(scope="module")
def corpus():
    return load_dataset()


def test_exact_counts_labels_splits_and_hard_negatives(corpus):
    summary = dataset_summary(corpus)
    assert summary["total"] == 140
    assert summary["labels"] == {"LEGITIMATE": 100, "BEC": 40}
    assert summary["splits"] == {"development": 98, "holdout": 42}
    assert Counter((case.split, case.label) for case in corpus) == EXPECTED_SPLITS
    assert summary["bec_types"] == EXPECTED_TYPES
    assert summary["hard_negatives"] == 30
    assert len({case.case_id for case in corpus}) == 140
    assert len({case.email.message_id for case in corpus}) == 140
    assert len({case.email.body_text for case in corpus}) == 140


def test_all_emails_valid_synthetic_and_metadata_separate(corpus):
    for case in corpus:
        assert isinstance(case.email, EmailIngestRequest)
        assert EmailIngestRequest.model_validate_json(case.email.model_dump_json()) == case.email
        assert (case.expected_bec_type is None) == (case.label == "LEGITIMATE")
        for field in ["label", "split", "expected_bec_type", "is_hard_negative"]:
            assert field not in type(case.email).model_fields
        assert "BEC" not in case.email.message_id and "LEGITIMATE" not in case.email.message_id
        addresses = [case.email.sender_email, *case.email.to_recipients, *case.email.cc_recipients]
        addresses += [value for value in [case.email.reply_to, case.email.return_path] if value]
        assert all(address.rsplit("@", 1)[1].endswith(".example") for address in addresses)
        for address in re.findall(r"[\w.+-]+@[\w.-]+", case.email.body_text):
            assert address.rstrip(".").endswith(".example")
        for url in re.findall(r"https?://[^\s]+", case.email.body_text):
            assert urlsplit(url).hostname.endswith(".example")
        with pytest.raises(ValidationError):
            EmailIngestRequest.model_validate_json(case.model_dump_json())


def test_synthetic_context_is_valid_and_not_loaded_into_database():
    context = json.loads(DEFAULT_DATASET_PATH.with_name("context.json").read_text())
    assert "ficticio" in context["notice"].lower()
    assert len(context["executives"]) == len(context["vendors"]) == 4
    for row in context["executives"]:
        assert ExecutiveContactCreate(**row).email.endswith(".example")
    for row in context["vendors"]:
        vendor = VendorCreate(**row)
        assert vendor.domain.endswith(".example")
        assert vendor.bank_account_reference.startswith("REF-FICTICIA-")


def write_cases(tmp_path, cases):
    path = tmp_path / "corpus.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in cases), encoding="utf-8")
    return path


@pytest.fixture
def rows():
    return [json.loads(line) for line in DEFAULT_DATASET_PATH.read_text().splitlines()]


@pytest.mark.parametrize("identity", ["case_id", "message_id"])
def test_loader_rejects_duplicate_identities(tmp_path, rows, identity):
    if identity == "case_id":
        rows[1]["case_id"] = rows[0]["case_id"]
    else:
        rows[1]["email"]["message_id"] = rows[0]["email"]["message_id"]
    with pytest.raises(DatasetValidationError, match="Duplicate identity"):
        load_dataset(write_cases(tmp_path, rows))


@pytest.mark.parametrize(
    "change", ["label", "split", "expected_type", "leak", "unknown", "hard_bec"]
)
def test_loader_validates_every_row(tmp_path, rows, change):
    row = rows[-1]
    if change == "label":
        row["label"] = "UNKNOWN"
    elif change == "split":
        row["split"] = "training"
    elif change == "expected_type":
        row["expected_bec_type"] = None if row["label"] == "BEC" else "OTHER"
    elif change == "leak":
        row["email"]["risk_score"] = 90
    elif change == "unknown":
        row["extra"] = "DO_NOT_PRINT"
    else:
        row = next(row for row in rows if row["label"] == "BEC")
        row["is_hard_negative"] = True
    with pytest.raises(DatasetValidationError, match="Invalid dataset row") as error:
        load_dataset(write_cases(tmp_path, rows))
    assert "DO_NOT_PRINT" not in str(error.value)


@pytest.mark.parametrize("change", ["missing", "split_counts", "type_counts", "hard_negatives"])
def test_loader_enforces_corpus_counts(tmp_path, rows, change):
    if change == "missing":
        rows.pop()
    elif change == "split_counts":
        rows[0]["split"] = "holdout" if rows[0]["split"] == "development" else "development"
    elif change == "type_counts":
        row = next(row for row in rows if row["label"] == "BEC")
        row["expected_bec_type"] = (
            "OTHER" if row["expected_bec_type"] != "OTHER" else "VENDOR_FRAUD"
        )
    else:
        for row in rows:
            row["is_hard_negative"] = False
    with pytest.raises(DatasetValidationError):
        load_dataset(write_cases(tmp_path, rows))


@pytest.mark.parametrize("change", ["address", "url"])
def test_accidental_nonreserved_domains_are_rejected(tmp_path, rows, change):
    if change == "address":
        rows[0]["email"]["sender_email"] = "sender@not-reserved.org"
    else:
        rows[0]["email"]["body_text"] = "https://not-reserved.org/private"
    with pytest.raises(DatasetValidationError, match="Non-reserved"):
        load_dataset(write_cases(tmp_path, rows))


@pytest.mark.parametrize("contents", [b"not-json\n", b"\xff", b"\n"])
def test_malformed_dataset_is_sanitized(tmp_path, contents):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(contents)
    with pytest.raises(DatasetValidationError):
        load_dataset(path)


def test_cli_only_prints_counts(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["validate_dataset"])
    assert main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["total"] == 140
    assert "sender_email" not in output.out and "body_text" not in output.out
    assert output.err == ""


def test_cli_missing_file_returns_clean_error(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("sys.argv", ["validate_dataset", str(tmp_path / "missing.jsonl")])
    assert main() == 1
    assert "cannot be read" in capsys.readouterr().err
