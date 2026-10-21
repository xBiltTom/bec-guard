"""Small fixed policy. Content indicators are evidence, never a BEC verdict alone."""

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Email, ExecutiveContact, Vendor
from app.models.enums import BECType
from app.schemas.analysis import DeterministicAssessment, Signal
from app.schemas.email import EmailIngestRequest
from app.services.domain_similarity import is_domain_lookalike

DETERMINISTIC_POLICY_VERSION = "det-v1"


@dataclass
class AnalysisContext:
    executives: list[ExecutiveContact]
    vendors: list[Vendor]


def load_analysis_context(session: Session) -> AnalysisContext:
    return AnalysisContext(
        list(session.scalars(select(ExecutiveContact).where(ExecutiveContact.is_active.is_(True)))),
        list(session.scalars(select(Vendor).where(Vendor.is_active.is_(True)))),
    )


def normalize_text(value: str) -> str:
    return " ".join(
        "".join(
            c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
        ).split()
    )


def domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower()


def name_matches(display: str, known: str, *, min_tokens: int = 2) -> bool:
    # Whole normalized tokens, allowing titles/additional surnames, never a first
    # name alone. A matching name needs an address mismatch to become a signal.
    tokens, expected = set(re.findall(r"\w+", display)), set(re.findall(r"\w+", known))
    return len(expected) >= min_tokens and expected <= tokens


def assess_deterministically(
    email: Email | EmailIngestRequest, context: AnalysisContext
) -> DeterministicAssessment:
    signals: list[Signal] = []

    def add(code: str, description: str, weight: int, source: str = "RULE") -> None:
        if not any(s.code == code for s in signals):
            signals.append(
                Signal(code=code, description=description, source=source, contribution=weight)
            )

    sender = email.sender_email.lower()
    host = domain(sender)
    display = normalize_text(email.sender_name or "")
    known_domains = {domain(e.email) for e in context.executives} | {
        v.domain.lower() for v in context.vendors
    }
    legitimate_executive = any(sender == e.email.lower() for e in context.executives)
    legitimate_vendor = any(
        host == v.domain.lower() or sender == (v.contact_email or "").lower()
        for v in context.vendors
    )
    if not legitimate_executive:
        for executive in context.executives:
            official = domain(executive.email)
            if name_matches(display, normalize_text(executive.name)):
                add(
                    "EXECUTIVE_IDENTITY_MISMATCH",
                    "Nombre ejecutivo conocido con dirección no oficial.",
                    35 if host not in known_domains else 15,
                    "CONTEXT",
                )
            if is_domain_lookalike(host, official):
                add(
                    "EXECUTIVE_DOMAIN_LOOKALIKE",
                    "Dominio similar al de un ejecutivo conocido.",
                    25,
                    "CONTEXT",
                )
    if not legitimate_vendor:
        for vendor in context.vendors:
            if name_matches(display, normalize_text(vendor.name), min_tokens=1):
                add(
                    "VENDOR_IDENTITY_MISMATCH",
                    "Nombre de proveedor conocido con dominio/contacto distinto.",
                    30,
                    "CONTEXT",
                )
            if is_domain_lookalike(host, vendor.domain):
                add(
                    "VENDOR_DOMAIN_LOOKALIKE",
                    "Dominio similar al de un proveedor conocido.",
                    25,
                    "CONTEXT",
                )

    if email.reply_to and email.reply_to.lower() != sender:
        cross_domain = domain(email.reply_to) != host
        add(
            "REPLY_TO_MISMATCH",
            "Reply-To tiene un dominio distinto al remitente."
            if cross_domain
            else "Reply-To tiene otra dirección dentro del dominio del remitente.",
            15 if cross_domain else 3,
        )
    if email.return_path and domain(email.return_path) != host:
        add(
            "RETURN_PATH_MISMATCH",
            "Return-Path usa otro dominio; puede ser infraestructura de envío.",
            4,
        )
    for mechanism, weight in [("spf", 8), ("dkim", 8), ("dmarc", 18)]:
        if re.search(
            rf"(?:^|[;\s]){mechanism}\s*=\s*fail\b", email.authentication_results or "", re.I
        ):
            add(
                f"{mechanism.upper()}_FAIL",
                f"Authentication-Results declara {mechanism.upper()} fail.",
                weight,
            )

    text = normalize_text(email.subject + "\n" + email.body_text)
    # Inspect clauses so negated instructions do not create a payment/data request.
    clauses = re.split(
        r"[.!?;\n]", normalize_text(email.subject) + "\n" + normalize_text(email.body_text)
    )
    positive = " ".join(
        c for c in clauses if not re.search(r"\b(no|not|never|sin|without|don't|do not)\b", c)
    )
    payment = bool(
        re.search(
            r"\b(pag\w*|abon\w*|transfer\w*|fondos|payment|pay|wire|compra\w*|buy)\b", positive
        )
    )
    if payment:
        add("PAYMENT_REQUEST", "El mensaje plantea un pago, transferencia o compra.", 8)
    bank = bool(
        re.search(
            r"\b(cambi\w*|reempla\w*|sustit\w*|nuev\w*|change\w*|replac\w*|new)\b"
            r".{0,100}\b(cuenta|bancari\w*|beneficiari\w*|referencia de pago|account|bank|payee)\b"
            r"|\b(cuenta|account)\s+(?:de\s+)?(?:reemplazo|replacement)",
            positive,
        )
    )
    if bank:
        add(
            "BANK_ACCOUNT_CHANGE",
            "Se propone cambiar cuenta, beneficiario o referencia de pago.",
            24,
        )
    sensitive = bool(
        re.search(
            r"\b(envia\w*|remit\w*|necesit\w*|solicit\w*|send|share|need|provide)\b.{0,100}"
            r"\b(nomina|credenciales|contrasen\w*|identificaciones|datos individuales|"
            r"maestro completo|"
            r"payroll|credentials|passwords?|personal data|tax records)\b",
            positive,
        )
    )
    if sensitive:
        add(
            "SENSITIVE_DATA_REQUEST",
            "Se solicita información personal, financiera masiva o credenciales.",
            22,
        )
    actionable = payment or bank or sensitive
    if actionable and re.search(
        r"\b(urgente?|inmediat\w*|hoy|ahora|sin esperar|no hay tiempo|"
        r"today|now|asap|immediately)\b",
        text,
    ):
        add("URGENCY", "Solicitud de acción con presión temporal.", 8)
    if actionable and re.search(
        r"\b(soy|habla|en nombre de|orden\w*|instruccion\w*|director\w*|gerencia|"
        r"ceo|cfo|on behalf|i am|i authorize)\b",
        text,
    ):
        add("AUTHORITY_PRESSURE", "La solicitud invoca identidad o autoridad directiva.", 10)
    if re.search(
        r"\b(no|sin|evita\w*)\s+(?:\w+\s+){0,3}"
        r"(consult\w*|contact\w*|valid\w*|verific\w*|registr\w*|archiv\w*|llam\w*|inform\w*)\b"
        r"|\b(no involucres|fuera del expediente|fuera del sistema|no uses el portal|"
        r"do not (?:tell|call|verify)|keep (?:it|this) secret|skip approval)\b",
        text,
    ):
        add(
            "SECRECY_REQUEST", "Se pide evitar registro, consulta o verificación independiente.", 12
        )

    codes = {s.code for s in signals}
    suggested = None
    for code, kind in [
        ("BANK_ACCOUNT_CHANGE", BECType.BANK_ACCOUNT_CHANGE),
        ("SENSITIVE_DATA_REQUEST", BECType.SENSITIVE_DATA_REQUEST),
        ("EXECUTIVE_IDENTITY_MISMATCH", BECType.EXECUTIVE_IMPERSONATION),
        ("EXECUTIVE_DOMAIN_LOOKALIKE", BECType.EXECUTIVE_IMPERSONATION),
        ("VENDOR_IDENTITY_MISMATCH", BECType.VENDOR_FRAUD),
        ("VENDOR_DOMAIN_LOOKALIKE", BECType.VENDOR_FRAUD),
    ]:
        if code in codes:
            suggested = kind
            break
    return DeterministicAssessment(
        score=min(100, sum(s.contribution for s in signals)),
        signals=signals,
        bec_type=suggested,
        policy_version=DETERMINISTIC_POLICY_VERSION,
    )
