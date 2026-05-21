from __future__ import annotations

from typing import Any

from wxctl.decoders.base import DecodeResult, children_to_dict, maybe_text, safe_xml, text
from wxctl.resolvers.asset_resolver import resolve_structured_assets


# Known appmsg type numbers that don't yet have a dedicated semantic classification.
# Falls back to kind="appmsg" rather than "unknown".
_KNOWN_APPMSG_FALLBACK = frozenset({
    2, 3, 4, 7, 8, 10, 13, 14, 15, 16, 17, 19, 34, 49,
})


def _safe_int(value: str | None) -> int | None:
    """Safe integer conversion that returns None on failure instead of crashing."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    xml_text = maybe_text(message_content)
    if xml_text is None:
        return DecodeResult(kind="unknown", text=None, decoded={"raw_type": raw_type}, assets=[])
    root = safe_xml(xml_text)
    if root is None:
        return DecodeResult(kind="appmsg", text=None, decoded={"xml": xml_text}, assets=[])

    appmsg = root.find("appmsg")
    if appmsg is not None:
        return _decode_appmsg_xml(root, appmsg, xml_text, packed_info_data, context)

    return _decode_other_xml_formats(root, xml_text, packed_info_data, context)


def _resolve_appmsg_assets(
    app_type_int: int | None,
    packed_info_data: bytes | None,
    context,
) -> list[dict[str, Any]]:
    """Resolve assets based on appmsg type."""
    if packed_info_data is None:
        return []
    # File shares may contain file attachment paths
    if app_type_int == 6:
        return [
            dict(a) for a in resolve_structured_assets(
                context.xwechat_root, context.self_wxid, context.conversation_hash,
                packed_info_data, asset_kind="file",
            )
        ]
    # Share cards may contain thumbnail images
    if app_type_int in (1, 5):
        return [
            dict(a) for a in resolve_structured_assets(
                context.xwechat_root, context.self_wxid, context.conversation_hash,
                packed_info_data, asset_kind="image",
            )
        ]
    return []


def _decode_appmsg_xml(root, appmsg, xml_text: str, packed_info_data: bytes | None, context) -> DecodeResult:
    app_type_raw = text(root, "appmsg/type")
    data: dict[str, Any] = {
        "appid": appmsg.attrib.get("appid") if appmsg is not None else None,
        "sdkver": appmsg.attrib.get("sdkver") if appmsg is not None else None,
        "type": app_type_raw,
        "title": text(root, "appmsg/title"),
        "description": text(root, "appmsg/des"),
        "url": text(root, "appmsg/url"),
        "source_app": text(root, "appinfo/appname"),
        "appattach": children_to_dict(root.find("appmsg/appattach")),
        "refermsg": children_to_dict(root.find("appmsg/refermsg")),
    }

    app_type_int = _safe_int(app_type_raw)
    kind, text_content = _classify_appmsg(app_type_int, app_type_raw, data, xml_text)
    assets = _resolve_appmsg_assets(app_type_int, packed_info_data, context)
    return DecodeResult(kind=kind, text=text_content, decoded=data, assets=assets)


def _classify_appmsg(
    app_type_int: int | None,
    app_type_raw: str | None,
    data: dict,
    xml_text: str,
) -> tuple[str, str | None]:
    """Classify appmsg by type number into a semantic kind.

    Falls back gracefully when app_type is None, non-numeric, or unclassified.
    """
    if app_type_int == 1:
        # URL / link card (news article, web link)
        return ("share_card", data.get("title"))
    if app_type_int == 5:
        return ("share_card", data.get("title"))
    if app_type_int == 6:
        return ("file_share", data.get("title"))
    if app_type_int == 33:
        # Mini program
        return ("mini_program", data.get("title"))
    if app_type_int == 36:
        # Location share
        return ("location", data.get("title"))
    if app_type_int == 57:
        return ("quote_reply", data.get("title"))
    if app_type_int == 63:
        # Transfer / red packet
        return ("transfer", data.get("title"))
    if app_type_int == 2000:
        # Transfer notification
        return ("transfer", data.get("title"))
    if app_type_int == 10000000:
        # Wallet / payment notification
        return ("payment", data.get("title"))
    # Known but unclassified appmsg types fall back to "appmsg" not "unknown"
    if app_type_int is not None and app_type_int in _KNOWN_APPMSG_FALLBACK:
        return ("appmsg", data.get("title"))
    # Non-numeric, None, or truly unknown type — still "appmsg" not crash
    return ("appmsg", data.get("title"))


def _decode_other_xml_formats(
    root,
    xml_text: str,
    packed_info_data: bytes | None,
    context,
) -> DecodeResult:
    """Handle non-standard XML message formats."""
    # Some group chat messages use <sysmsg> or other top-level elements
    sysmsg = root.find("sysmsg")
    if sysmsg is not None:
        return DecodeResult(kind="system", text=sysmsg.text or xml_text, decoded={"xml": xml_text}, assets=[])

    return DecodeResult(kind="unknown", text=xml_text, decoded={"xml": xml_text}, assets=[])
