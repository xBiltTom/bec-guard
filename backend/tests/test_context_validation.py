import pytest
from pydantic import ValidationError

from app.core.context_validation import normalize_domain
from app.schemas.organizational_context import ExecutiveContactCreate, VendorCreate


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" Example.COM. ", "example.com"),
        ("payments.Example.org", "payments.example.org"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
    ],
)
def test_domain_normalization(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "domain",
    [
        "https://empresa.com",
        "empresa.com/login",
        "empresa.com:443",
        "foo bar.com",
        "example.com?x=1",
        "example.com#fragment",
        "example.com..",
        "example..com",
        "-bad.example.com",
        "bad-.example.com",
        "a" * 64 + ".com",
        "localhost",
        "127.0.0.1",
        "::1",
        "bücher.example",
        "",
        "example_com.org",
    ],
)
def test_invalid_domains(domain):
    with pytest.raises(ValueError):
        normalize_domain(domain)
    with pytest.raises(ValidationError):
        VendorCreate(name="Vendor", domain=domain)


@pytest.mark.parametrize(
    "schema,body",
    [
        (ExecutiveContactCreate, {"name": "CEO", "position": "CEO", "email": "not-an-email"}),
        (ExecutiveContactCreate, {"name": "CEO", "position": " ", "email": "ceo@example.com"}),
        (VendorCreate, {"name": "Vendor", "domain": "example.com", "contact_email": "invalid"}),
        (VendorCreate, {"name": "Vendor", "domain": None}),
        (VendorCreate, {"name": "Vendor", "domain": 123}),
        (VendorCreate, {"name": " ", "domain": "example.com"}),
        (VendorCreate, {"name": "Vendor", "domain": "example.com", "unknown": "value"}),
    ],
)
def test_invalid_context_input(schema, body):
    with pytest.raises(ValidationError):
        schema.model_validate(body)
