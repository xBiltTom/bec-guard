from pydantic import EmailStr, TypeAdapter

email_adapter = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_identity_email(value: str) -> str:
    return normalize_email(str(email_adapter.validate_python(normalize_email(value))))
