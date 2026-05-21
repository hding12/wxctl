from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from wxctl.adapters.wechat_fs import (
    conversation_attach_dir,
    extract_hex_candidates,
    iter_matching_files,
)


SUPPORTED_ASSET_TYPES = frozenset({
    "image", "voice", "video", "file", "share_card",
})

# Common signature bytes used by WeChat for different media types
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89\x50\x4e\x47": "png",
    b"\x47\x49\x46\x38": "gif",
    b"\x52\x49\x46\x46": "webp",
}


def _try_parse_packed_info(packed_info_data: bytes | None) -> dict[str, Any] | None:
    """Attempt to parse packed_info_data as JSON."""
    if packed_info_data is None:
        return None
    try:
        text = packed_info_data.decode("utf-8", errors="ignore")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def _resolve_image_assets(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[dict[str, Any]]:
    """Resolve image assets from packed_info_data and attach directory."""
    assets: list[dict[str, Any]] = []

    # Try JSON parsing first
    info = _try_parse_packed_info(packed_info_data)
    if info and isinstance(info, dict):
        # Check for common WeChat image info fields
        img_path = info.get("ImgLocalPath") or info.get("LocalPath") or info.get("FilePath")
        if img_path:
            candidate = Path(img_path)
            if candidate.exists():
                assets.append({
                    "kind": "image_candidate",
                    "local_path": str(candidate),
                    "source": "packed_info_path",
                    "file_size": candidate.stat().st_size,
                })

        # Check for MD5-based resolution
        md5 = info.get("Md5") or info.get("MD5")
        if md5:
            attach_dir = conversation_attach_dir(xwechat_root, self_wxid, conversation_hash)
            matches = list(attach_dir.rglob(f"{md5.lower()}*"))
            for m in matches:
                if m.is_file():
                    assets.append({
                        "kind": "image_candidate",
                        "local_path": str(m),
                        "source": "packed_info_md5",
                        "file_size": m.stat().st_size,
                    })

    # Fallback: extract hex candidates from raw blob
    if not assets:
        candidates = extract_hex_candidates(packed_info_data)
        if candidates:
            attach_dir = conversation_attach_dir(xwechat_root, self_wxid, conversation_hash)
            for path in iter_matching_files(attach_dir, candidates):
                assets.append({
                    "kind": "image_candidate",
                    "local_path": str(path),
                    "source": "hex_fallback",
                    "file_size": path.stat().st_size,
                })

    return assets


def _resolve_voice_assets(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[dict[str, Any]]:
    """Resolve voice (.silk) assets."""
    assets: list[dict[str, Any]] = []
    candidates = extract_hex_candidates(packed_info_data)
    if candidates:
        attach_dir = conversation_attach_dir(xwechat_root, self_wxid, conversation_hash)
        for path in iter_matching_files(attach_dir, candidates):
            if path.suffix.lower() in {".silk", ".amr", ".wav", ".mp3", ".aud"}:
                assets.append({
                    "kind": "voice_candidate",
                    "local_path": str(path),
                    "source": "hex_fallback",
                    "file_size": path.stat().st_size,
                })
    return assets


def _resolve_video_assets(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[dict[str, Any]]:
    """Resolve video (.mp4) assets."""
    assets: list[dict[str, Any]] = []
    candidates = extract_hex_candidates(packed_info_data)
    if candidates:
        attach_dir = conversation_attach_dir(xwechat_root, self_wxid, conversation_hash)
        for path in iter_matching_files(attach_dir, candidates):
            if path.suffix.lower() in {".mp4", ".mov", ".avi", ".video"}:
                assets.append({
                    "kind": "video_candidate",
                    "local_path": str(path),
                    "source": "hex_fallback",
                    "file_size": path.stat().st_size,
                })
    return assets


def _resolve_file_assets(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[dict[str, Any]]:
    """Resolve file share assets."""
    assets: list[dict[str, Any]] = []
    info = _try_parse_packed_info(packed_info_data)
    if info and isinstance(info, dict):
        # File message may contain download path info
        for key in ("FilePath", "LocalPath", "DownloadPath"):
            path_val = info.get(key)
            if path_val:
                candidate = Path(path_val)
                if candidate.exists():
                    assets.append({
                        "kind": "file_candidate",
                        "local_path": str(candidate),
                        "source": f"packed_info.{key}",
                        "file_size": candidate.stat().st_size,
                    })
    return assets


def resolve_asset_paths(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[str]:
    """Legacy API: return flat list of candidate paths."""
    assets = resolve_structured_assets(
        xwechat_root, self_wxid, conversation_hash, packed_info_data
    )
    return [a["local_path"] for a in assets if "local_path" in a]


def resolve_structured_assets(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
    asset_kind: str | None = None,
) -> list[dict[str, Any]]:
    """Type-aware asset resolution returning structured asset records.

    Args:
        xwechat_root: WeChat data root path
        self_wxid: Current user's wxid
        conversation_hash: MD5 hash of target_id
        packed_info_data: Raw bytes from message's packed_info_data field
        asset_kind: Optional hint about expected asset type (image/voice/video/file)

    Returns:
        List of structured asset candidate records, each with kind, local_path, source.
    """
    if packed_info_data is None or len(packed_info_data) == 0:
        return []

    resolver = {
        "image": _resolve_image_assets,
        "voice": _resolve_voice_assets,
        "video": _resolve_video_assets,
        "file": _resolve_file_assets,
    }

    # If asset_kind is specified, use the type-specific resolver
    if asset_kind and asset_kind in resolver:
        return resolver[asset_kind](xwechat_root, self_wxid, conversation_hash, packed_info_data)

    # Otherwise try all applicable resolvers and deduplicate
    seen: set[str] = set()
    all_assets: list[dict[str, Any]] = []
    for kind, res_fn in resolver.items():
        for asset in res_fn(xwechat_root, self_wxid, conversation_hash, packed_info_data):
            path = asset.get("local_path", "")
            if path and path not in seen:
                seen.add(path)
                all_assets.append(asset)

    # Fallback: generic hex candidate extraction
    if not all_assets:
        for path in resolve_asset_paths_legacy(xwechat_root, self_wxid, conversation_hash, packed_info_data):
            if path not in seen:
                seen.add(path)
                all_assets.append({
                    "kind": "asset_candidate",
                    "local_path": path,
                    "source": "generic_hex",
                })

    return all_assets


def resolve_asset_paths_legacy(
    xwechat_root: Path,
    self_wxid: str,
    conversation_hash: str,
    packed_info_data: bytes | None,
) -> list[str]:
    """Original fallback: pure hex-candidate extraction."""
    candidates = extract_hex_candidates(packed_info_data)
    if not candidates:
        return []
    attach_dir = conversation_attach_dir(xwechat_root, self_wxid, conversation_hash)
    return [str(path) for path in iter_matching_files(attach_dir, candidates)]
