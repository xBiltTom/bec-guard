from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.email_limits import (
    MAX_AUTH_RESULTS_LENGTH,
    MAX_BODY_LENGTH,
    MAX_MESSAGE_ID_LENGTH,
    MAX_RECIPIENTS,
    MAX_SUBJECT_LENGTH,
)
from app.schemas.email import EmailIngestRequest


def test_normalized_contract(email_payload):
    email_payload["subject"] = "Case\x00 PRESERVED"
    email = EmailIngestRequest(**email_payload)
    assert email.message_id == "<MiXeD-unit@fixtures.becguard.example>"
    assert email.sender_name == "Nora Prisma"
    assert email.sender_email == "nora@luminaria.example"
    assert email.reply_to == "reply@luminaria.example"
    assert email.return_path == "bounce@luminaria.example"
    assert email.to_recipients == ["finanzas@luminaria.example", "team@luminaria.example"]
    assert email.cc_recipients == ["cc@luminaria.example"]
    assert email.subject == "Case PRESERVED"
    assert email.body_text == "Contenido PRIVADO\nSegunda línea\nTercera línea"
    assert email.received_at == datetime(2026, 10, 20, 14, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "field",
    [
        "label",
        "expected_label",
        "expected_bec_type",
        "bec_type",
        "risk_score",
        "risk_level",
        "verdict",
        "split",
        "raw_mime",
        "id",
        "ingested_at",
    ],
)
def test_evaluation_and_internal_fields_are_forbidden(email_payload, field):
    with pytest.raises(ValidationError):
        EmailIngestRequest(**{**email_payload, field: "NOT_AN_INPUT"})


@pytest.mark.parametrize(
    "value", ["", " ", None, "x" * (MAX_MESSAGE_ID_LENGTH + 1), "id\nvalue", "id\x00value"]
)
def test_invalid_message_ids(email_payload, value):
    with pytest.raises(ValidationError):
        EmailIngestRequest(**{**email_payload, "message_id": value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("sender_email", "a@luminaria.example,b@luminaria.example"),
        ("reply_to", "not-an-email"),
        ("return_path", "not-an-email"),
        ("to_recipients", "user@luminaria.example"),
        ("cc_recipients", ["invalid"]),
        ("to_recipients", ["a@luminaria.example"] * (MAX_RECIPIENTS + 1)),
        ("subject", "s" * (MAX_SUBJECT_LENGTH + 1)),
        ("body_text", "b" * (MAX_BODY_LENGTH + 1)),
        ("authentication_results", "a" * (MAX_AUTH_RESULTS_LENGTH + 1)),
        ("sender_name", "n" * 201),
        ("thread_id", "t" * 256),
        ("received_at", "2026-10-20T12:00:00"),
        ("received_at", datetime(2026, 10, 20)),
        ("received_at", 1000000),
        ("received_at", "0001-01-01T00:00:00+14:00"),
        ("received_at", "9999-12-31T23:59:59-12:00"),
    ],
)
def test_invalid_fields(email_payload, field, value):
    with pytest.raises(ValidationError):
        EmailIngestRequest(**{**email_payload, field: value})


def test_combined_recipient_limit(email_payload):
    email_payload["to_recipients"] = [f"to{i}@luminaria.example" for i in range(60)]
    email_payload["cc_recipients"] = [f"cc{i}@luminaria.example" for i in range(41)]
    with pytest.raises(ValidationError):
        EmailIngestRequest(**email_payload)


def test_empty_optional_fields_and_text(email_payload):
    for field in [
        "thread_id",
        "sender_name",
        "reply_to",
        "return_path",
        "authentication_results",
        "subject",
        "body_text",
    ]:
        email_payload[field] = None
    email = EmailIngestRequest(**email_payload)
    assert email.thread_id is email.sender_name is email.authentication_results is None
    assert email.reply_to is email.return_path is None
    assert email.subject == email.body_text == ""
    for field in ["thread_id", "subject", "body_text", "to_recipients", "cc_recipients"]:
        email_payload.pop(field)
    assert EmailIngestRequest(**email_payload).to_recipients == []
