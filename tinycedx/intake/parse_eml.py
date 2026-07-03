import re
from email import message_from_bytes
from email.message import Message
from pathlib import Path
from typing import Any

_FIELD_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9 _-]{0,40}):\s?(.*)$")


def _get_text_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _parse_key_value_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    last_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        m = _FIELD_LINE.match(line)
        if m:
            key, value = m.group(1).strip(), m.group(2).strip()
            fields[key] = value
            last_key = key
        elif last_key is not None:
            fields[last_key] = (fields[last_key] + " " + line.strip()).strip()
    return fields


def parse_eml(eml_path: Path) -> dict[str, Any] | None:
    if not eml_path.exists():
        return None
    with eml_path.open("rb") as f:
        msg = message_from_bytes(f.read())
    body = _get_text_body(msg)
    fields = _parse_key_value_lines(body)
    rec_id = (fields.get("Id") or "").strip() or None
    return {
        "id": rec_id,
        "source_format": "eml",
        "source_file": eml_path.name,
        "raw_fields": fields,
    }
