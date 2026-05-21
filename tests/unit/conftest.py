from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from wxctl.decoders.base import DecodeContext, DecodeResult
from wxctl.decoders.registry import decode_message

import pytest


GOLDEN_DIR = Path(__file__).parents[1] / "golden"


@pytest.fixture
def decode_ctx() -> DecodeContext:
    return DecodeContext(
        conversation_hash="abc123def456abc123def456abc123de",
        xwechat_root=Path("/tmp"),
        self_wxid="wxid_self",
    )


def load_golden(name: str) -> str:
    path = GOLDEN_DIR / name
    return path.read_text(encoding="utf-8")


def assert_decode_result(result: DecodeResult, *, kind: str, text_contains: str | None = None) -> None:
    assert result.kind == kind, f"Expected kind={kind!r}, got {result.kind!r}"
    if text_contains is not None:
        assert result.text is not None, f"Expected text containing {text_contains!r}, got None"
        assert text_contains in result.text, f"Expected text containing {text_contains!r}, got {result.text!r}"
    assert isinstance(result.decoded, dict)
    assert isinstance(result.assets, list)
