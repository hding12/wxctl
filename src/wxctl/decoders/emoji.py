from __future__ import annotations

from wxctl.decoders.base import DecodeResult, attrs, maybe_text, safe_xml


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    xml_text = maybe_text(message_content)
    if xml_text is None:
        return DecodeResult(kind="emoji", text=None, decoded={}, assets=[])
    root = safe_xml(xml_text)
    emoji = root.find("emoji") if root is not None else None
    return DecodeResult(kind="emoji", text=None, decoded=attrs(emoji), assets=[])
