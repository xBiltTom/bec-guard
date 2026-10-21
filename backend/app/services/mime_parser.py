"""Bounded RFC 5322/MIME conversion. Never executes content or accesses the network."""

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from html.parser import HTMLParser

from app.core.email_limits import MAX_MIME_DEPTH, MAX_MIME_PARTS, MAX_RAW_MIME_BYTES, MAX_RECIPIENTS
from app.schemas.email import EmailIngestRequest


class MIMEParseError(ValueError):
    """Safe error: messages never contain the source content."""


class _HTMLText(HTMLParser):
    _ignored = {"script", "style", "head", "template"}
    _blocks = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "section", "blockquote", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._ignored:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in self._blocks:
            self.fragments.append("\n")

    def handle_endtag(self, tag):
        if tag in self._ignored:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        elif not self.hidden_depth and tag in self._blocks:
            self.fragments.append("\n")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.fragments.append(data)


def _header(message: EmailMessage, name: str, *, required: bool = False):
    values = message.get_all(name, [])
    if len(values) > 1 or (required and not values):
        raise MIMEParseError("Missing or ambiguous selected header")
    return values[0] if values else None


def _addresses(header, *, exactly_one: bool = False) -> list[str]:
    if header is None:
        return []
    if header.defects:
        raise MIMEParseError("Invalid address header")
    values = list(header.addresses)
    if (exactly_one and len(values) != 1) or len(values) > MAX_RECIPIENTS:
        raise MIMEParseError("Unsupported address count")
    return [value.addr_spec for value in values]


def _body(message: EmailMessage, *, depth: int = 0, count: list[int]) -> tuple[int, str] | None:
    count[0] += 1
    if depth > MAX_MIME_DEPTH or count[0] > MAX_MIME_PARTS:
        raise MIMEParseError("MIME structure exceeds limits")
    if any(
        len(message.get_all(header, [])) > 1
        for header in ("Content-Type", "Content-Transfer-Encoding", "Content-Disposition")
    ):
        raise MIMEParseError("Ambiguous MIME metadata")
    if message.defects:
        raise MIMEParseError("Malformed MIME structure")
    if message.get_content_disposition() == "attachment" or message.get_filename() is not None:
        return None
    # Attached/forwarded messages are not the message body, even without a filename.
    if message.get_content_maintype() == "message":
        return None
    if message.is_multipart():
        parts = list(message.iter_parts())
        if message.get_content_subtype() == "related":
            start = message.get_param("start")
            if start is not None:
                parts = [part for part in parts if part.get("Content-ID") == start]
            else:
                parts = parts[:1]
        choices = [
            candidate
            for part in parts
            if (candidate := _body(part, depth=depth + 1, count=count)) is not None
        ]
        return min(choices, key=lambda item: item[0]) if choices else None
    content_type = message.get_content_type()
    if content_type not in {"text/plain", "text/html"}:
        return None
    # Known charset: replace malformed byte sequences; unknown charset: clean parser error.
    content = message.get_content(errors="replace")
    if content_type == "text/plain":
        return 0, content
    converter = _HTMLText()
    converter.feed(content)
    converter.close()
    return 1, "".join(converter.fragments).strip()


def parse_email(raw: bytes) -> EmailIngestRequest:
    if not isinstance(raw, bytes):
        raise MIMEParseError("Expected raw MIME bytes")
    if len(raw) > MAX_RAW_MIME_BYTES:
        raise MIMEParseError("Raw MIME exceeds size limit")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        from_header = _header(message, "From", required=True)
        [sender] = _addresses(from_header, exactly_one=True)
        reply_header = _header(message, "Reply-To")
        replies = _addresses(reply_header, exactly_one=True) if reply_header is not None else []
        return_header = _header(message, "Return-Path")
        return_address = None
        if return_header is not None and str(return_header).strip() != "<>":
            parsed_return = policy.default.header_factory("To", str(return_header))
            [return_address] = _addresses(parsed_return, exactly_one=True)
        date_header = _header(message, "Date", required=True)
        if date_header.defects or date_header.datetime is None:
            raise MIMEParseError("Invalid message date")
        selected = _body(message, count=[0])
        return EmailIngestRequest(
            message_id=str(_header(message, "Message-ID", required=True)),
            sender_name=from_header.addresses[0].display_name or None,
            sender_email=sender,
            reply_to=replies[0] if replies else None,
            return_path=return_address,
            to_recipients=_addresses(_header(message, "To")),
            cc_recipients=_addresses(_header(message, "Cc")),
            subject=str(_header(message, "Subject") or ""),
            body_text=selected[1] if selected else "",
            authentication_results="\n".join(
                str(header) for header in message.get_all("Authentication-Results", [])
            )
            or None,
            received_at=date_header.datetime,
        )
    except MIMEParseError:
        raise
    except ValueError, TypeError, LookupError, RecursionError, AttributeError:
        raise MIMEParseError("Invalid or unsupported MIME message") from None
