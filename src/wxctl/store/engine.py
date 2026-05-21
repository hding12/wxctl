from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from wxctl.config import RuntimeConfig


class Warehouse:
    def __init__(self, runtime: RuntimeConfig) -> None:
        self.runtime = runtime
        self.runtime.app_support_root.mkdir(parents=True, exist_ok=True)
        self.runtime.raw_root.mkdir(parents=True, exist_ok=True)
        self.runtime.export_root.mkdir(parents=True, exist_ok=True)
        self.runtime.log_root.mkdir(parents=True, exist_ok=True)
        self.runtime.state_root.mkdir(parents=True, exist_ok=True)
        self.runtime.warehouse_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.runtime.warehouse_db)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        self.conn.executescript(schema_path.read_text(encoding="utf-8"))
        # Migration: add sender_info_json column if this is an existing database
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN sender_info_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        self.conn.commit()

    def start_sync_run(self, scope: str) -> int:
        cur = self.conn.execute("INSERT INTO sync_runs(scope) VALUES (?)", (scope,))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_sync_run(
        self,
        sync_run_id: int,
        inserted: int,
        updated: int,
        skipped: int,
        failures: int,
        failure_samples: list[dict[str, Any]],
        notes: dict[str, Any],
    ) -> None:
        self.conn.execute(
            "UPDATE sync_runs SET finished_at = CURRENT_TIMESTAMP, "
            "inserted_messages = ?, updated_messages = ?, decode_failures = ?, notes_json = ? WHERE id = ?",
            (inserted, updated, failures, json.dumps({**notes, "skipped": skipped, "failure_samples": failure_samples}, ensure_ascii=False), sync_run_id),
        )
        self.conn.commit()

    def upsert_conversation(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO conversations(target_id, kind, conversation_hash, first_ts, last_ts, total_count, text_count, updated_at)
            VALUES(:target_id, :kind, :conversation_hash, :first_ts, :last_ts, :total_count, :text_count, CURRENT_TIMESTAMP)
            ON CONFLICT(target_id) DO UPDATE SET
              kind = excluded.kind,
              conversation_hash = excluded.conversation_hash,
              first_ts = excluded.first_ts,
              last_ts = excluded.last_ts,
              total_count = excluded.total_count,
              text_count = excluded.text_count,
              updated_at = CURRENT_TIMESTAMP
            """,
            payload,
        )

    def message_exists(self, source_db: str, target_id: str, local_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM messages WHERE source_db = ? AND target_id = ? AND local_id = ?",
            (source_db, target_id, local_id),
        ).fetchone()
        return row is not None

    def _write_raw_payload(
        self,
        target_id: str,
        source_db: str,
        local_id: int,
        message_content: bytes | str | None,
        packed_info_data: bytes | None,
    ) -> str:
        safe_target = target_id.replace("/", "_")
        path = self.runtime.raw_root / safe_target / source_db
        path.mkdir(parents=True, exist_ok=True)
        payload_path = path / f"{local_id}.json"
        record = {
            "message_content_b64": base64.b64encode(message_content).decode("ascii") if isinstance(message_content, (bytes, bytearray)) else None,
            "message_content_text": message_content if isinstance(message_content, str) else None,
            "packed_info_data_b64": base64.b64encode(packed_info_data).decode("ascii") if packed_info_data else None,
        }
        payload_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(payload_path)

    def upsert_message(
        self,
        sync_run_id: int,
        payload: dict[str, Any],
        decoded: dict[str, Any],
        assets: list[dict[str, Any]],
        sender_info: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """Insert or update a message. Returns (raw_payload_path, was_inserted)."""
        source_db = payload["source_db"]
        target_id = payload["target_id"]
        local_id = int(payload["local_id"])
        was_inserted = not self.message_exists(source_db, target_id, local_id)

        payload_path = self._write_raw_payload(
            target_id, source_db, local_id,
            payload.get("message_content"), payload.get("packed_info_data"),
        )
        packed_info = payload.get("packed_info_data")
        packed_info_hex = packed_info.hex() if isinstance(packed_info, (bytes, bytearray)) else None
        row = {
            "source_db": source_db,
            "target_id": target_id,
            "conversation_hash": payload["conversation_hash"],
            "local_id": local_id,
            "server_id": payload.get("server_id"),
            "ts": payload["ts"],
            "datetime": datetime.fromtimestamp(payload["ts"], tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "sender_wxid": payload.get("sender_wxid"),
            "is_self": payload.get("is_self", 0),
            "raw_type": payload["raw_type"],
            "kind": decoded["kind"],
            "text": decoded.get("text"),
            "decoded_json": json.dumps(decoded.get("decoded", {}), ensure_ascii=False),
            "sender_info_json": json.dumps(sender_info, ensure_ascii=False) if sender_info else None,
            "packed_info_hex": packed_info_hex,
            "raw_payload_path": payload_path,
            "sync_run_id": sync_run_id,
        }
        self.conn.execute(
            """INSERT INTO messages(source_db, target_id, conversation_hash, local_id, server_id, ts, datetime, sender_wxid, is_self, raw_type, kind, text, decoded_json, sender_info_json, packed_info_hex, raw_payload_path, sync_run_id)
            VALUES(:source_db, :target_id, :conversation_hash, :local_id, :server_id, :ts, :datetime, :sender_wxid, :is_self, :raw_type, :kind, :text, :decoded_json, :sender_info_json, :packed_info_hex, :raw_payload_path, :sync_run_id)
            ON CONFLICT(source_db, target_id, local_id) DO UPDATE SET
              server_id = excluded.server_id,
              ts = excluded.ts,
              datetime = excluded.datetime,
              sender_wxid = excluded.sender_wxid,
              is_self = excluded.is_self,
              raw_type = excluded.raw_type,
              kind = excluded.kind,
              text = excluded.text,
              decoded_json = excluded.decoded_json,
              sender_info_json = excluded.sender_info_json,
              packed_info_hex = excluded.packed_info_hex,
              raw_payload_path = excluded.raw_payload_path,
              sync_run_id = excluded.sync_run_id
            """,
            row,
        )
        self.conn.execute(
            "DELETE FROM assets WHERE source_db = ? AND target_id = ? AND local_id = ?",
            (source_db, target_id, local_id),
        )
        for asset in assets:
            self.conn.execute(
                "INSERT OR IGNORE INTO assets(source_db, target_id, local_id, kind, local_path, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source_db,
                    target_id,
                    local_id,
                    asset.get("kind", "asset"),
                    asset.get("local_path"),
                    json.dumps(asset, ensure_ascii=False),
                ),
            )
        return payload_path, was_inserted

    def get_sync_run_history(self, limit: int = 5) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ))

    def get_coverage_summary(self) -> dict[str, Any]:
        """Return kind coverage across all warehouse messages."""
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) AS cnt FROM messages GROUP BY kind ORDER BY cnt DESC"
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        return {
            "total": total,
            "by_kind": {r["kind"]: r["cnt"] for r in rows},
            "unknown_count": next((r["cnt"] for r in rows if r["kind"] == "unknown"), 0),
        }

    def commit(self) -> None:
        self.conn.commit()

    def fetch_messages(self, target_id: str, limit: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM messages WHERE target_id = ? ORDER BY ts ASC, local_id ASC"
        params: list[Any] = [target_id]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params))

    def fetch_assets(self, source_db: str, target_id: str, local_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT kind, local_path, meta_json FROM assets WHERE source_db = ? AND target_id = ? AND local_id = ? ORDER BY id ASC",
            (source_db, target_id, local_id),
        )
        return [json.loads(row["meta_json"]) for row in rows]
