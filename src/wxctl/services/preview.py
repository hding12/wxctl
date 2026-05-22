from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any

from wxctl.adapters.sqlite_source import SourceRepository
from wxctl.config import AppConfig
from wxctl.services.sync import sync_targets
from wxctl.store.engine import Warehouse


_GENERIC_KIND_LABELS = {
    "emoji": "[emoji]",
    "file_share": "[file]",
    "image": "[image]",
    "location": "[location]",
    "mini_program": "[mini_program]",
    "payment": "[payment]",
    "quote_reply": "[quote_reply]",
    "share_card": "[share_card]",
    "system": "[system]",
    "transfer": "[transfer]",
    "unknown": "[unknown]",
    "video": "[video]",
    "voice": "[voice]",
    "voip": "[voip]",
}

_DECODED_FIELDS = (
    "text",
    "title",
    "description",
    "desc",
    "name",
    "label",
    "file_name",
    "fileName",
    "url",
    "source_app",
)

_URL_PATTERN = re.compile(r"https?://\S+")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_PASSWORD_PATTERN = re.compile(r"(?P<label>密码|[Pp]assword)\s*[:：]\s*(?P<secret>\S+)")


def _format_ts(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _compact_text(value: str | None, limit: int = 120) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return None
    normalized = _PASSWORD_PATTERN.sub(lambda match: f"{match.group('label')}: [redacted]", normalized)
    normalized = _EMAIL_PATTERN.sub("[email]", normalized)
    normalized = _URL_PATTERN.sub("[url]", normalized)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _summarize_decoded(kind: str, decoded: dict[str, Any]) -> str | None:
    for field in _DECODED_FIELDS:
        summary = _compact_text(decoded.get(field))
        if summary:
            return summary
    return _GENERIC_KIND_LABELS.get(kind, f"[{kind}]")


def summarize_record(record: dict[str, Any]) -> str | None:
    text_summary = _compact_text(record.get("text"))
    if text_summary:
        return text_summary
    kind = record.get("kind") or "unknown"
    decoded = record.get("decoded") or {}
    if not isinstance(decoded, dict):
        decoded = {}
    return _summarize_decoded(kind, decoded)


def _snippet_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": record["ts"],
        "datetime": record["datetime"],
        "is_self": bool(record["is_self"]),
        "sender_wxid": record.get("sender_wxid"),
        "kind": record["kind"],
        "summary": summarize_record(record),
    }


def select_representative_snippets(records: list[dict[str, Any]], count: int = 2) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    readable_any = [(idx, record) for idx, record in enumerate(records) if summarize_record(record)]
    if not readable_any:
        return []

    readable_text = [
        (idx, record)
        for idx, record in readable_any
        if record.get("kind") == "text" and _compact_text(record.get("text"))
    ]

    primary_pool = readable_text or readable_any
    snippets: list[tuple[int, dict[str, Any]]] = [primary_pool[-1]]

    if count > 1:
        secondary = None
        if len(primary_pool) >= 4:
            secondary = primary_pool[-4]
        elif len(primary_pool) >= 2:
            secondary = primary_pool[0]
        else:
            fallback_pool = [item for item in readable_any if item[0] != snippets[0][0]]
            if fallback_pool:
                secondary = fallback_pool[-1]

        if secondary and secondary[0] != snippets[0][0]:
            snippets.append(secondary)

    if count > 2:
        used = {idx for idx, _ in snippets}
        for idx, record in reversed(readable_any):
            if idx in used:
                continue
            snippets.append((idx, record))
            used.add(idx)
            if len(snippets) >= count:
                break

    ordered = sorted(snippets, key=lambda item: item[0], reverse=True)
    return [_snippet_payload(record) for _, record in ordered[:count]]


def _warehouse_record(row: Any) -> dict[str, Any]:
    decoded_raw = row["decoded_json"]
    return {
        "target_id": row["target_id"],
        "local_id": row["local_id"],
        "ts": row["ts"],
        "datetime": row["datetime"],
        "is_self": bool(row["is_self"]),
        "sender_wxid": row["sender_wxid"],
        "kind": row["kind"],
        "text": row["text"],
        "decoded": json.loads(decoded_raw) if decoded_raw else {},
    }


def preview_targets(
    config: AppConfig,
    kind: str = "direct",
    limit: int = 30,
    snippets_per_target: int = 2,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    source = SourceRepository(config.wechat.decrypted_root)
    targets = source.list_targets(kind=kind)[:limit]
    if not targets:
        return []

    warehouse = Warehouse(config.runtime)
    target_ids = [target.target_id for target in targets]
    missing = [target_id for target_id in target_ids if not warehouse.fetch_messages(target_id, limit=1)]
    if refresh or missing:
        sync_targets(config, target_ids if refresh else missing)
        warehouse = Warehouse(config.runtime)

    previews: list[dict[str, Any]] = []
    for target in targets:
        rows = warehouse.fetch_messages(target.target_id)
        records = [_warehouse_record(row) for row in rows]
        previews.append(
            {
                "target_id": target.target_id,
                "kind": target.kind,
                "conversation_hash": target.conversation_hash,
                "total_count": target.total_count,
                "text_count": target.text_count,
                "first_ts": target.first_ts,
                "first_datetime": _format_ts(target.first_ts),
                "last_ts": target.last_ts,
                "last_datetime": _format_ts(target.last_ts),
                "snippet_count": snippets_per_target,
                "snippets": select_representative_snippets(records, count=snippets_per_target),
            }
        )
    return previews


def preview_direct_targets(
    config: AppConfig,
    limit: int = 30,
    snippets_per_target: int = 2,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    return preview_targets(
        config,
        kind="direct",
        limit=limit,
        snippets_per_target=snippets_per_target,
        refresh=refresh,
    )


def format_preview_blocks(previews: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, preview in enumerate(previews, start=1):
        lines = [
            f"[{index}] {preview['target_id']}",
            (
                f"messages={preview['total_count']} text={preview['text_count']} "
                f"first={preview['first_datetime'] or '-'} last={preview['last_datetime'] or '-'}"
            ),
        ]
        snippets = preview.get("snippets") or []
        if snippets:
            for snippet_index, snippet in enumerate(snippets, start=1):
                if preview["kind"] == "group":
                    sender_wxid = snippet.get("sender_wxid") or "unknown"
                    speaker = f"me({sender_wxid})" if snippet["is_self"] else sender_wxid
                else:
                    speaker = "me" if snippet["is_self"] else "them"
                lines.append(
                    f"{snippet_index}. {snippet['datetime']} {speaker} {snippet['kind']}: {snippet['summary']}"
                )
        else:
            lines.append("1. no readable snippet found")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
