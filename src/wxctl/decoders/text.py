from __future__ import annotations

from wxctl.decoders.base import DecodeResult, maybe_text


def decode(raw_type: int, message_content: bytes | str | None, packed_info_data: bytes | None, context) -> DecodeResult:
    text_content = maybe_text(message_content) or ""
    return DecodeResult(kind="text", text=text_content, decoded={"text": text_content}, assets=[])
