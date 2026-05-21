from __future__ import annotations

from wxctl.decoders.base import DecodeResult, attrs, maybe_text, safe_xml
from wxctl.resolvers.asset_resolver import resolve_structured_assets


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    xml_text = maybe_text(message_content)
    if xml_text is None:
        return DecodeResult(kind="image", text=None, decoded={}, assets=[])
    root = safe_xml(xml_text)
    img = root.find("img") if root is not None else None
    assets = [
        dict(a) for a in resolve_structured_assets(
            context.xwechat_root, context.self_wxid, context.conversation_hash,
            packed_info_data, asset_kind="image",
        )
    ]
    return DecodeResult(kind="image", text=None, decoded=attrs(img), assets=assets)
