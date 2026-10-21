from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.core.email_limits import (
    MAX_BODY_LENGTH,
    MAX_MIME_DEPTH,
    MAX_MIME_PARTS,
    MAX_RAW_MIME_BYTES,
    MAX_RECIPIENTS,
)
from app.services.mime_parser import MIMEParseError, parse_email

FIXTURES = Path(__file__).parent / "fixtures" / "mime"


def raw_message(body="Body"):
    message = EmailMessage()
    message["Message-ID"] = "<unit@fixtures.example>"
    message["From"] = "Sender <sender@luminaria.example>"
    message["To"] = "receiver@luminaria.example"
    message["Date"] = "Tue, 20 Oct 2026 09:30:00 -0500"
    message["Subject"] = "Synthetic subject"
    message.set_content(body)
    return message


@pytest.mark.parametrize(
    "name",
    ["plain", "alternative", "html", "utf8", "latin1", "headers", "attachments", "duplicate"],
)
def test_supported_fixtures(name):
    result = parse_email((FIXTURES / f"{name}.eml").read_bytes())
    assert result.sender_email == "nora@luminaria.example"
    assert result.to_recipients == ["finanzas@luminaria.example"]
    assert result.received_at == datetime(2026, 10, 20, 14, 30, tzinfo=UTC)
    assert result.thread_id is None
    assert "raw" not in type(result).model_fields
    assert "\r" not in result.body_text


def test_selected_headers_and_no_unrelated_headers():
    result = parse_email((FIXTURES / "headers.eml").read_bytes())
    assert result.message_id == "<headers@fixtures.becguard.example>"
    assert result.sender_name == "Nora Prisma"
    assert result.reply_to == "soporte@luminaria.example"
    assert result.return_path == "bounces@luminaria.example"
    assert result.cc_recipients == ["ana@luminaria.example", "equipo@luminaria.example"]
    assert "spf=pass" in result.authentication_results
    assert "dkim=pass" in result.authentication_results
    assert "\n" in result.authentication_results
    assert "DO_NOT_RETAIN" not in result.model_dump_json()


def test_case_sensitive_message_id_and_plain_body():
    result = parse_email((FIXTURES / "plain.eml").read_bytes())
    assert result.message_id == "<MiXeD-Plain@fixtures.becguard.example>"
    assert result.body_text == "Mensaje sintético de prueba.\n"


def test_alternative_prefers_plain():
    result = parse_email((FIXTURES / "alternative.eml").read_bytes())
    assert result.body_text == "Versión de texto preferida.\n"
    assert "HTML" not in result.body_text


def test_html_is_inert_and_scripts_styles_and_resources_not_retained():
    result = parse_email((FIXTURES / "html.eml").read_bytes())
    assert "Hola & equipo" in result.body_text
    assert "Texto visible." in result.body_text
    assert "Portal" in result.body_text
    assert "HIDDEN" not in result.body_text
    assert "<" not in result.body_text
    assert "https://" not in result.body_text


def test_attachments_and_forwarded_messages_are_ignored():
    result = parse_email((FIXTURES / "attachments.eml").read_bytes())
    assert result.body_text == "Cuerpo principal sin adjuntos.\n"
    assert "MUST_NOT_APPEAR" not in result.model_dump_json()


def test_charsets_and_encoded_headers():
    utf8 = parse_email((FIXTURES / "utf8.eml").read_bytes())
    assert utf8.sender_name == "Nóra Prisma"
    assert utf8.subject == "Reunión de revisión — Perú"
    assert "✓" in utf8.body_text
    latin1 = parse_email((FIXTURES / "latin1.eml").read_bytes())
    assert "reunión y café" in latin1.body_text


@pytest.mark.parametrize(
    "name",
    [
        "invalid_from",
        "multiple_from",
        "multiple_reply_to",
        "invalid_date",
        "naive_date",
        "missing_message_id",
        "unknown_charset",
    ],
)
def test_invalid_fixtures_fail_without_content(name):
    with pytest.raises(MIMEParseError) as error:
        parse_email((FIXTURES / f"{name}.eml").read_bytes())
    assert "luminaria" not in str(error.value)
    assert "revisión" not in str(error.value)


@pytest.mark.parametrize(
    "header", ["From", "Reply-To", "Message-ID", "Date", "To", "Subject", "Return-Path"]
)
def test_duplicate_selected_single_headers_are_rejected(header):
    raw = raw_message().as_bytes()
    values = {
        "From": "other@luminaria.example",
        "Reply-To": "reply@luminaria.example",
        "Message-ID": "<other@fixtures.example>",
        "Date": "Tue, 20 Oct 2026 09:30:00 -0500",
        "To": "other@luminaria.example",
        "Subject": "Duplicate",
        "Return-Path": "<bounce@luminaria.example>",
    }
    extra = f"{header}: {values[header]}\n".encode()
    if header in {"Reply-To", "Return-Path"}:
        raw = extra + raw
    with pytest.raises(MIMEParseError):
        parse_email(extra + raw)


def test_size_and_body_limits():
    with pytest.raises(MIMEParseError, match="size limit"):
        parse_email(b"x" * (MAX_RAW_MIME_BYTES + 1))
    with pytest.raises(MIMEParseError):
        parse_email(raw_message("x" * (MAX_BODY_LENGTH + 1)).as_bytes())


def test_nul_and_line_endings_are_sanitized():
    message = raw_message("Line one\x00\r\nLine two\rLine three")
    message.replace_header("Subject", "Subject\x00value")
    result = parse_email(message.as_bytes())
    assert result.subject == "Subjectvalue"
    assert result.body_text == "Line one\nLine two\nLine three\n"


def test_bad_bytes_known_charset_use_replacement():
    raw = raw_message("marker").as_bytes().replace(b"marker", b"bad\xff")
    assert "bad�" in parse_email(raw).body_text


def test_null_return_path_is_absent():
    message = raw_message()
    message["Return-Path"] = "<>"
    assert parse_email(message.as_bytes()).return_path is None


def test_recipient_limit():
    message = raw_message()
    message.replace_header(
        "To", ", ".join(f"user{i}@luminaria.example" for i in range(MAX_RECIPIENTS + 1))
    )
    with pytest.raises(MIMEParseError):
        parse_email(message.as_bytes())


@pytest.mark.parametrize("kind", ["depth", "parts"])
def test_structure_limits(kind):
    message = raw_message()
    if kind == "parts":
        message.make_mixed()
        for _ in range(MAX_MIME_PARTS):
            part = EmailMessage()
            part.set_content("part")
            message.attach(part)
    else:
        for _ in range(MAX_MIME_DEPTH + 1):
            parent = EmailMessage()
            parent.make_mixed()
            parent.attach(message)
            message = parent
        for name, value in raw_message().items():
            if name not in {"Content-Type", "Content-Transfer-Encoding", "MIME-Version"}:
                message[name] = value
    with pytest.raises(MIMEParseError, match="structure"):
        parse_email(message.as_bytes())


@pytest.mark.parametrize(
    "header,value",
    [
        ("Content-Type", "text/html"),
        ("Content-Transfer-Encoding", "base64"),
        ("Content-Disposition", "inline"),
    ],
)
def test_ambiguous_mime_metadata_is_rejected(header, value):
    message = raw_message().as_bytes()
    extra = f"{header}: {value}\n".encode()
    if header == "Content-Disposition":
        message = extra + message
    with pytest.raises(MIMEParseError, match="Ambiguous"):
        parse_email(extra + message)
