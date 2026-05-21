from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable


WXID_DIR_RE = re.compile(r"^(wxid_[^_]+)")
HEX32_RE = re.compile(r"[0-9a-f]{32}")


def resolve_self_wxid(xwechat_root: Path) -> str | None:
    if not xwechat_root.exists():
        return None
    candidates: list[str] = []
    for child in xwechat_root.iterdir():
        if not child.is_dir():
            continue
        match = WXID_DIR_RE.match(child.name)
        if match:
            candidates.append(match.group(1))
    if len(candidates) == 1:
        return candidates[0]
    return candidates[0] if candidates else None


def find_db_storage_dir(xwechat_root: Path) -> Path | None:
    if not xwechat_root.exists():
        return None
    if xwechat_root.name == "db_storage":
        return xwechat_root
    candidates = sorted(
        child / "db_storage"
        for child in xwechat_root.iterdir()
        if child.is_dir() and (child / "db_storage").is_dir()
    )
    return candidates[0] if candidates else None


def conversation_attach_dir(xwechat_root: Path, self_wxid: str, conversation_hash: str) -> Path:
    account_dir = next((p for p in xwechat_root.iterdir() if p.is_dir() and p.name.startswith(self_wxid)), None)
    if account_dir is None:
        return xwechat_root / self_wxid / "msg" / "attach" / conversation_hash
    return account_dir / "msg" / "attach" / conversation_hash


def extract_hex_candidates(blob: bytes | str | None) -> list[str]:
    if blob is None:
        return []
    if isinstance(blob, bytes):
        text = blob.decode("utf-8", errors="ignore")
    else:
        text = blob
    seen: list[str] = []
    for match in HEX32_RE.finditer(text.lower()):
        item = match.group(0)
        if item not in seen:
            seen.append(item)
    return seen


def iter_matching_files(base: Path, names: Iterable[str]) -> list[Path]:
    if not base.exists():
        return []
    matches: list[Path] = []
    for name in names:
        matches.extend(base.rglob(f"{name}*"))
    return sorted({path for path in matches if path.is_file()})
