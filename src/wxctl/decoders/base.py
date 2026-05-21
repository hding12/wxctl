from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any


ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


@dataclass(slots=True)
class DecodeContext:
    conversation_hash: str
    xwechat_root: Any
    self_wxid: str


@dataclass(slots=True)
class DecodeResult:
    kind: str
    text: str | None
    decoded: dict[str, Any]
    assets: list[dict[str, Any]]


def decompress_zstd(payload: bytes) -> bytes:
    result = subprocess.run(
        ["zstd", "-d", "-q", "-c"],
        input=payload,
        capture_output=True,
        check=True,
    )
    return result.stdout


def maybe_text(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        payload = value
        if payload[:4] == ZSTD_MAGIC:
            try:
                payload = decompress_zstd(payload)
            except Exception:
                return payload.decode("utf-8", errors="replace")
        return payload.decode("utf-8", errors="replace")
    return str(value)


def safe_xml(xml_text: str) -> ET.Element | None:
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        try:
            return ET.fromstring(f"<root>{xml_text}</root>")
        except ET.ParseError:
            return None


def attrs(node: ET.Element | None) -> dict[str, Any]:
    return dict(node.attrib) if node is not None else {}


def text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    item = node.find(path)
    return item.text if item is not None else None


def children_to_dict(node: ET.Element | None) -> dict[str, Any]:
    if node is None:
        return {}
    data: dict[str, Any] = {}
    for child in node:
        if list(child):
            data[child.tag] = {grand.tag: grand.text for grand in child}
        else:
            data[child.tag] = child.text
    return data
