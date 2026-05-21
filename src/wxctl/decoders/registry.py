from __future__ import annotations

from typing import Any

from wxctl.decoders import appmsg, emoji, image, system, text, video, voice, voip
from wxctl.decoders.base import DecodeContext, DecodeResult  # noqa: F401


# raw_type -> decoder module mapping
# Each module must expose: decode(raw_type, message_content, packed_info_data, context) -> DecodeResult
_DECODER_MAP: dict[int, Any] = {
    1: text,       # plain text
    3: image,      # image message
    34: voice,     # voice message
    43: video,     # video message
    47: emoji,     # emoji / sticker
    50: voip,      # VoIP call
    10000: system, # system/revoke notification
}

# AppMsg types: raw_type values that contain appmsg XML payloads
_APPMSG_TYPES = frozenset({
    244813135921,
    25769803825,
    21474836529,
    318767153,
    436207661,
    822083633,
    1000000000,
    10401874641,
    16724785713,
    17609373617,
    18790482193,
    21323448369,
    21323448370,
    318767104,
    436207616,
    822083584,
})


def decode_message(
    raw_type: int,
    message_content: bytes | str | None,
    packed_info_data: bytes | None,
    context: DecodeContext,
) -> DecodeResult:
    if raw_type in _DECODER_MAP:
        return _DECODER_MAP[raw_type].decode(raw_type, message_content, packed_info_data, context)

    if raw_type in _APPMSG_TYPES:
        return appmsg.decode(raw_type, message_content, packed_info_data, context)

    return DecodeResult(kind="unknown", text=None, decoded={"raw_type": raw_type}, assets=[])
