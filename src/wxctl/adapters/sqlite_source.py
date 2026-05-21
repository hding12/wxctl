from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
import sqlite3
import re
from typing import Any, Iterable


@dataclass(slots=True)
class TargetSummary:
    target_id: str
    kind: str
    conversation_hash: str
    total_count: int
    text_count: int
    first_ts: int | None
    last_ts: int | None


class SourceRepository:
    def __init__(self, decrypted_root: Path) -> None:
        self.decrypted_root = decrypted_root
        self.message_dir = decrypted_root / "message"

    def message_dbs(self) -> list[Path]:
        if not self.message_dir.exists():
            return []
        numbered: list[tuple[int, Path]] = []
        for path in self.message_dir.glob("message_*.db"):
            match = re.fullmatch(r"message_(\d+)\.db", path.name)
            if match:
                numbered.append((int(match.group(1)), path))
        return [path for _, path in sorted(numbered)]

    def _connect(self, db_path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _name2id(self, conn: sqlite3.Connection) -> dict[int, str]:
        return {row["rowid"]: row["user_name"] for row in conn.execute("SELECT rowid, user_name FROM Name2Id")}

    def list_targets(self, kind: str | None = None) -> list[TargetSummary]:
        merged: dict[str, TargetSummary] = {}
        for db_path in self.message_dbs():
            conn = self._connect(db_path)
            names = [row["user_name"] for row in conn.execute("SELECT user_name FROM Name2Id") if row["user_name"]]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for target_id in names:
                conversation_hash = md5(target_id.encode()).hexdigest()
                table = f"Msg_{conversation_hash}"
                if table not in tables:
                    continue
                row = conn.execute(
                    f'SELECT COUNT(*) AS total_count, '
                    f'SUM(CASE WHEN local_type = 1 THEN 1 ELSE 0 END) AS text_count, '
                    f'MIN(create_time) AS first_ts, MAX(create_time) AS last_ts FROM "{table}"'
                ).fetchone()
                target_kind = "group" if target_id.endswith("@chatroom") else "direct"
                if kind and target_kind != kind:
                    continue
                current = merged.get(target_id)
                total_count = int(row["total_count"] or 0)
                text_count = int(row["text_count"] or 0)
                first_ts = row["first_ts"]
                last_ts = row["last_ts"]
                if current is None:
                    merged[target_id] = TargetSummary(
                        target_id=target_id,
                        kind=target_kind,
                        conversation_hash=conversation_hash,
                        total_count=total_count,
                        text_count=text_count,
                        first_ts=first_ts,
                        last_ts=last_ts,
                    )
                else:
                    current.total_count += total_count
                    current.text_count += text_count
                    current.first_ts = min(x for x in [current.first_ts, first_ts] if x is not None)
                    current.last_ts = max(x for x in [current.last_ts, last_ts] if x is not None)
            conn.close()
        return sorted(merged.values(), key=lambda item: item.total_count, reverse=True)

    def iter_messages(self, target_id: str, self_wxid: str | None) -> Iterable[dict[str, Any]]:
        conversation_hash = md5(target_id.encode()).hexdigest()
        table = f"Msg_{conversation_hash}"
        for db_path in self.message_dbs():
            conn = self._connect(db_path)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in tables:
                conn.close()
                continue
            name_map = self._name2id(conn)
            for row in conn.execute(
                f'SELECT local_id, server_id, local_type, sort_seq, real_sender_id, create_time, '
                f'status, upload_status, download_status, server_seq, origin_source, source, '
                f'message_content, compress_content, packed_info_data '
                f'FROM "{table}" ORDER BY create_time ASC, local_id ASC'
            ):
                sender_wxid = name_map.get(row["real_sender_id"])
                yield {
                    "source_db": db_path.name,
                    "target_id": target_id,
                    "conversation_hash": conversation_hash,
                    "local_id": row["local_id"],
                    "server_id": row["server_id"],
                    "raw_type": row["local_type"],
                    "sort_seq": row["sort_seq"],
                    "sender_wxid": sender_wxid,
                    "is_self": int(sender_wxid == self_wxid) if self_wxid else 0,
                    "ts": row["create_time"],
                    "status": row["status"],
                    "upload_status": row["upload_status"],
                    "download_status": row["download_status"],
                    "server_seq": row["server_seq"],
                    "origin_source": row["origin_source"],
                    "source": row["source"],
                    "message_content": row["message_content"],
                    "compress_content": row["compress_content"],
                    "packed_info_data": row["packed_info_data"],
                }
            conn.close()
