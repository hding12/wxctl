from __future__ import annotations

from wxctl.decoders.base import DecodeResult, maybe_text, safe_xml, text


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    xml_text = maybe_text(message_content)
    if xml_text is None:
        return DecodeResult(kind="system", text=None, decoded={}, assets=[])
    root = safe_xml(xml_text)
    revoke_text = text(root, "revokemsg/content") if raw_type == 10000 else None
    return DecodeResult(kind="system", text=revoke_text or xml_text, decoded={"xml": xml_text}, assets=[])
