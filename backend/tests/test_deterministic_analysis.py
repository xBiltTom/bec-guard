import pytest

from app.models import ExecutiveContact, Vendor
from app.models.enums import BECType
from app.schemas.email import EmailIngestRequest
from app.services.deterministic_analysis import (
    AnalysisContext,
    assess_deterministically,
    load_analysis_context,
)
from app.services.domain_similarity import edit_distance, is_domain_lookalike


@pytest.fixture
def context():
    return AnalysisContext(
        [ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example")],
        [
            Vendor(
                name="Suministros Andinos",
                domain="andinos.example",
                contact_email="ventas@andinos.example",
            )
        ],
    )


def assess(payload, context, **changes):
    return assess_deterministically(EmailIngestRequest(**{**payload, **changes}), context)


def codes(result):
    return {s.code for s in result.signals}


@pytest.mark.parametrize(
    "candidate,official,expected",
    [
        ("empresa.example", "empresa.example", False),
        ("ernpresa.example", "empresa.example", True),
        ("empresaa.example", "empresa.example", True),
        ("empres.example", "empresa.example", True),
        ("empresa.exarnple", "empresa.example", True),
        ("otroproveedor.example", "proveedor.example", False),
        ("proveedor.example.evil.example", "proveedor.example", False),
        ("mail.empresa.example", "empresa.example", False),
        ("EMPRESAA.EXAMPLE.", "empresa.example", True),
        ("abc.example", "abd.example", False),
    ],
)
def test_domain_similarity(candidate, official, expected):
    assert is_domain_lookalike(candidate, official) is expected
    assert edit_distance("kitten", "sitting") == 3


def test_legitimate_executive_and_name_alone(email_payload, context):
    result = assess(
        email_payload,
        context,
        sender_name="Dra. Ana Perez",
        sender_email="ana@empresa.example",
        reply_to=None,
        return_path=None,
    )
    assert not codes(result)
    result = assess(email_payload, context, sender_name="Ana", reply_to=None, return_path=None)
    assert "EXECUTIVE_IDENTITY_MISMATCH" not in codes(result)


def test_impersonation_and_lookalike_without_display_name(email_payload, context):
    result = assess(
        email_payload, context, sender_name="Ana Pérez", sender_email="ana@other.example"
    )
    assert "EXECUTIVE_IDENTITY_MISMATCH" in codes(result)
    assert result.bec_type == BECType.EXECUTIVE_IMPERSONATION
    result = assess(email_payload, context, sender_name=None, sender_email="ana@ernpresa.example")
    assert "EXECUTIVE_DOMAIN_LOOKALIKE" in codes(result)


def test_vendor_domain_and_registered_external_contact(email_payload, context):
    for sender in ["newperson@andinos.example", "ventas@andinos.example"]:
        result = assess(
            email_payload, context, sender_name="Suministros Andinos", sender_email=sender
        )
        assert not any(s.source == "CONTEXT" for s in result.signals)
    context.vendors[0].contact_email = "contact@external.example"
    result = assess(
        email_payload,
        context,
        sender_name="Suministros Andinos",
        sender_email="contact@external.example",
    )
    assert not any(s.source == "CONTEXT" for s in result.signals)


def test_vendor_mismatch_and_lookalike(email_payload, context):
    result = assess(
        email_payload,
        context,
        sender_name="Suministros Andinos",
        sender_email="billing@andinoos.example",
    )
    assert {"VENDOR_IDENTITY_MISMATCH", "VENDOR_DOMAIN_LOOKALIKE"} <= codes(result)
    assert result.bec_type == BECType.VENDOR_FRAUD


@pytest.mark.parametrize(
    "reply,weight",
    [
        (None, 0),
        ("nora@luminaria.example", 0),
        ("other@luminaria.example", 3),
        ("other@external.example", 15),
    ],
)
def test_reply_to(email_payload, context, reply, weight):
    result = assess(email_payload, context, reply_to=reply, return_path=None)
    assert sum(s.contribution for s in result.signals if s.code == "REPLY_TO_MISMATCH") == weight


def test_auth_fail_and_moderate_return_path(email_payload, context):
    result = assess(
        email_payload,
        context,
        reply_to=None,
        return_path="bounce@mailer.example",
        authentication_results="mx; SPF=fail; dkim = fail; dmarc=fail",
    )
    assert codes(result) == {"SPF_FAIL", "DKIM_FAIL", "DMARC_FAIL", "RETURN_PATH_MISMATCH"}
    assert result.score == 38
    result = assess(email_payload, context, authentication_results="mx; spf=softfail; dkim=pass")
    assert not ({"SPF_FAIL", "DKIM_FAIL", "DMARC_FAIL"} & codes(result))


@pytest.mark.parametrize(
    "body,expected",
    [
        ("Urgente: reunión hoy", set()),
        ("Necesito pagar la factura hoy", {"PAYMENT_REQUEST", "URGENCY"}),
        ("Please send payment immediately", {"PAYMENT_REQUEST", "URGENCY"}),
        ("Solicito cambiar la cuenta bancaria", {"BANK_ACCOUNT_CHANGE"}),
        ("Replace the bank account for payment", {"BANK_ACCOUNT_CHANGE", "PAYMENT_REQUEST"}),
        ("Envíame las credenciales del portal", {"SENSITIVE_DATA_REQUEST"}),
        ("Please send the payroll records", {"SENSITIVE_DATA_REQUEST"}),
        (
            "Soy el director, paga hoy. No consultes con finanzas.",
            {"PAYMENT_REQUEST", "URGENCY", "AUTHORITY_PRESSURE", "SECRECY_REQUEST"},
        ),
    ],
)
def test_content_rules(email_payload, context, body, expected):
    result = assess(
        email_payload, context, subject="", body_text=body, reply_to=None, return_path=None
    )
    assert codes(result) == expected
    assert result.score == min(100, sum(s.contribution for s in result.signals))
    assert result.policy_version == "det-v1"
    assert all(s.description != body for s in result.signals)


def test_representative_hard_negative(email_payload, context):
    result = assess(
        email_payload,
        context,
        sender_name="Ana Pérez",
        sender_email="ana@empresa.example",
        reply_to=None,
        return_path=None,
        subject="Pago urgente aprobado",
        body_text="Ejecutar el pago autorizado hoy con las dos firmas. No enviar datos personales. "
        "No modificar la cuenta bancaria. El expediente está en el portal interno.",
    )
    assert result.score < 40
    assert "BANK_ACCOUNT_CHANGE" not in codes(result)
    assert "SENSITIVE_DATA_REQUEST" not in codes(result)
    assert "EXECUTIVE_IDENTITY_MISMATCH" not in codes(result)


@pytest.mark.integration
def test_active_context_loaded_from_postgres(db_session, email_payload):
    db_session.add_all(
        [
            ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example"),
            ExecutiveContact(
                name="Inactive Person", position="CEO", email="old@old.example", is_active=False
            ),
            Vendor(name="Suministros Andinos", domain="andinos.example"),
            Vendor(name="Inactive Vendor", domain="old.example", is_active=False),
        ]
    )
    db_session.commit()
    context = load_analysis_context(db_session)
    assert len(context.executives) == len(context.vendors) == 1
    assert "EXECUTIVE_IDENTITY_MISMATCH" in codes(
        assess(email_payload, context, sender_name="Ana Pérez", sender_email="ana@outside.example")
    )
    assert "VENDOR_DOMAIN_LOOKALIKE" in codes(
        assess(email_payload, context, sender_email="new@andinoos.example")
    )
    assert "EXECUTIVE_IDENTITY_MISMATCH" not in codes(
        assess(email_payload, context, sender_name="Ana Pérez", sender_email="ana@empresa.example")
    )
