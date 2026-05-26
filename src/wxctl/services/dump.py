from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from wxctl.config import AppConfig
from wxctl.resolvers.sender_resolver import SenderResolver
from wxctl.resolvers.target_resolver import ContactDB
from wxctl.store.engine import Warehouse
from wxctl.services.sync import sync_targets


def _load_jsonl(path: str) -> list[dict]:
    p = Path(path).expanduser().resolve()
    if not p.exists() or p.stat().st_size == 0:
        return []
    records: list[dict] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _stable_key(record: dict) -> str:
    return f"{record.get('target_id', '')}:{record.get('source_db', '')}:{record.get('local_id', '')}"


def _merge_records(old_records: list[dict], warehouse_records: list[dict]) -> list[dict]:
    merged_by_key: dict[str, dict] = {}
    for record in old_records:
        merged_by_key[_stable_key(record)] = record
    for record in warehouse_records:
        merged_by_key[_stable_key(record)] = record
    merged = list(merged_by_key.values())
    merged.sort(key=lambda r: (r.get("ts", 0), r.get("local_id", 0)))
    return merged


def dump_target(
    config: AppConfig,
    target: str,
    refresh: bool = False,
    limit: int | None = None,
    input_path: str | None = None,
) -> list[dict]:
    if refresh:
        sync_targets(config, [target])
    warehouse = Warehouse(config.runtime)
    contacts = ContactDB(config.wechat.decrypted_root)
    sender_resolver = SenderResolver(config.wechat.decrypted_root)
    try:
        target_info = contacts.build_target_info(target)
        warehouse_records: list[dict] = []
        for row in warehouse.fetch_messages(target, limit=limit):
            assets = warehouse.fetch_assets(row["source_db"], row["target_id"], row["local_id"])
            sender_info_raw = row["sender_info_json"]
            sender_info_from_row = json.loads(sender_info_raw) if sender_info_raw else None
            sender_info_live = sender_resolver.resolve(row["sender_wxid"]) if row["sender_wxid"] else None
            sender_info = sender_info_from_row or sender_info_live
            if sender_info_from_row and sender_info_live:
                sender_info = {**sender_info_from_row, **sender_info_live}
            warehouse_records.append(
                {
                    "target_id": row["target_id"],
                    "target_info": target_info,
                    "conversation_hash": row["conversation_hash"],
                    "source_db": row["source_db"],
                    "local_id": row["local_id"],
                    "server_id": row["server_id"],
                    "ts": row["ts"],
                    "datetime": row["datetime"],
                    "sender_wxid": row["sender_wxid"],
                    "sender_info": sender_info,
                    "is_self": bool(row["is_self"]),
                    "raw_type": row["raw_type"],
                    "kind": row["kind"],
                    "text": row["text"],
                    "decoded": json.loads(row["decoded_json"]),
                    "assets": assets,
                    "raw": {
                        "payload_path": row["raw_payload_path"],
                        "packed_info_hex": row["packed_info_hex"],
                    },
                }
            )
    finally:
        sender_resolver.close()
        contacts.close()
    if input_path:
        return _merge_records(_load_jsonl(input_path), warehouse_records)
    return warehouse_records


def write_jsonl(records: list[dict], output_path: str | None) -> str:
    if output_path is None:
        raise ValueError("output_path is required when not using stdout")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(path)
