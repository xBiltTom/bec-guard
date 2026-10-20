"""Canonical organizational identifiers; no DNS or similarity checks."""

import re
from ipaddress import ip_address


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().removesuffix(".")
    labels = domain.split(".")
    if (
        len(domain) > 253
        or len(labels) < 2
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    ):
        raise ValueError("Invalid domain")
    try:
        ip_address(domain)
    except ValueError:
        return domain
    raise ValueError("Invalid domain")
