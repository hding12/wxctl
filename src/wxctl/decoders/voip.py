from __future__ import annotations

from wxctl.decoders.base import DecodeResult, maybe_text, safe_xml


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    xml_text = maybe_text(message_content)
    if xml_text is None:
        return DecodeResult(kind="voip", text=None, decoded={}, assets=[])
    root = safe_xml(xml_text)
    decoded = {child.tag: (child.text or child.attrib) for child in (root or [])}
    display = None
    if root is not None:
        node = root.find("voiplocalinfo/diaplay_content")
        display = node.text if node is not None else None
    return DecodeResult(kind="voip", text=display, decoded=decoded, assets=[])
