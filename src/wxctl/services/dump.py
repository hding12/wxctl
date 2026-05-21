from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from wxctl.config import AppConfig
from wxctl.store.engine import Warehouse
from wxctl.services.sync import sync_targets


def dump_target(config: AppConfig, target: str, refresh: bool = False, limit: int | None = None) -> list[dict]:
    if refresh:
        sync_targets(config, [target])
    warehouse = Warehouse(config.runtime)
    records: list[dict] = []
    for row in warehouse.fetch_messages(target, limit=limit):
        assets = warehouse.fetch_assets(row["source_db"], row["target_id"], row["local_id"])
        sender_info_raw = row["sender_info_json"]
        records.append(
            {
                "target_id": row["target_id"],
                "conversation_hash": row["conversation_hash"],
                "source_db": row["source_db"],
                "local_id": row["local_id"],
                "server_id": row["server_id"],
                "ts": row["ts"],
                "datetime": row["datetime"],
                "sender_wxid": row["sender_wxid"],
                "sender_info": json.loads(sender_info_raw) if sender_info_raw else None,
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
    return records


def write_jsonl(records: list[dict], output_path: str | None) -> str:
    if output_path is None:
        raise ValueError("output_path is required when not using stdout")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(path)
