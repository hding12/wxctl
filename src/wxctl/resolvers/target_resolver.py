from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


# Actual contact.db schema (confirmed from decrypt output) includes richer
# contact fields than the initial minimal implementation exposed.
_CONTACT_COLUMNS = [
    "username",
    "alias",
    "remark",
    "nick_name",
    "verify_flag",
    "description",
    "big_head_url",
    "small_head_url",
    "head_img_md5",
]
_CONTACT_SELECT = ", ".join(_CONTACT_COLUMNS)


class ContactDB:
    """Wrapper for contact.db that handles graceful degradation when unavailable.

    The actual contact.db lives at ``<decrypted_root>/contact/contact.db``
    (sibling of ``message/``), and its schema uses ``nick_name`` (with underscore)
    as the display-name field — not ``nickname``.

    All access is best-effort.  If the db is missing, unreadable, or lacks the
    expected schema, the class degrades cleanly to returning minimal fallback
    records.
    """

    def __init__(self, decrypted_root: Path) -> None:
        self._conn: sqlite3.Connection | None = None
        self._cache: dict[str, dict[str, Any]] = {}
        self._columns: list[str] = list(_CONTACT_COLUMNS)
        self._group_meta_cache: dict[str, dict[str, Any]] = {}
        self._init(decrypted_root)

    def _init(self, decrypted_root: Path) -> None:
        contact_db = decrypted_root / "contact" / "contact.db"
        if not contact_db.exists():
            return
        try:
            conn = sqlite3.connect(str(contact_db))
            conn.row_factory = sqlite3.Row
            self._conn = conn
            self._detect_schema()
            self._preload()
        except Exception:
            self._conn = None

    def _detect_schema(self) -> None:
        """Detect available columns from the contact table at runtime."""
        if self._conn is None:
            return
        try:
            cols = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(contact)")
            }
            available = [c for c in _CONTACT_COLUMNS if c in cols]
            if available:
                self._columns = available
        except Exception:
            pass

    def _preload(self) -> None:
        if self._conn is None:
            return
        try:
            select = ", ".join(self._columns)
            rows = self._conn.execute(
                f"SELECT {select} FROM contact ORDER BY username"
            ).fetchall()
            for row in rows:
                self._cache[row["username"]] = dict(row)
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self._conn is not None

    def lookup(self, wxid: str) -> dict[str, Any] | None:
        return self._cache.get(wxid)

    def lookup_with_fallback(self, wxid: str) -> dict[str, Any]:
        cached = self.lookup(wxid)
        if cached:
            return cached
        return {
            "username": wxid,
            "alias": None,
            "nick_name": None,
            "remark": None,
            "verify_flag": None,
            "description": None,
            "big_head_url": None,
            "small_head_url": None,
            "head_img_md5": None,
        }

    def display_name_for(self, contact: dict[str, Any] | None, fallback: str | None) -> str | None:
        if contact is None:
            return fallback
        return (
            contact.get("remark")
            or contact.get("nick_name")
            or contact.get("alias")
            or contact.get("username")
            or fallback
        )

    def normalize_contact(self, wxid: str | None) -> dict[str, Any]:
        if wxid is None:
            return {
                "username": None,
                "display_name": None,
                "nick_name": None,
                "remark": None,
                "alias": None,
                "verify_flag": None,
                "description": None,
                "big_head_url": None,
                "small_head_url": None,
                "head_img_md5": None,
            }
        contact = self.lookup_with_fallback(wxid)
        return {
            "username": wxid,
            "display_name": self.display_name_for(contact, wxid),
            "nick_name": contact.get("nick_name"),
            "remark": contact.get("remark"),
            "alias": contact.get("alias"),
            "verify_flag": contact.get("verify_flag"),
            "description": contact.get("description"),
            "big_head_url": contact.get("big_head_url"),
            "small_head_url": contact.get("small_head_url"),
            "head_img_md5": contact.get("head_img_md5"),
        }

    def lookup_group(self, group_id: str) -> dict[str, Any] | None:
        """Resolve group chat info from contact.db."""
        if self._conn is None:
            return None
        try:
            select = ", ".join(self._columns)
            row = self._conn.execute(
                f"SELECT {select} FROM contact WHERE username = ?",
                (group_id,),
            ).fetchone()
            if row:
                return dict(row)
        except Exception:
            pass
        return None

    def lookup_group_meta(self, group_id: str) -> dict[str, Any] | None:
        if self._conn is None:
            return None
        cached = self._group_meta_cache.get(group_id)
        if cached is not None:
            return cached
        try:
            room = self._conn.execute(
                "SELECT owner FROM chat_room WHERE username = ?",
                (group_id,),
            ).fetchone()
            detail = self._conn.execute(
                """
                SELECT announcement_, announcement_editor_, announcement_publish_time_, chat_room_status_
                FROM chat_room_info_detail
                WHERE username_ = ?
                """,
                (group_id,),
            ).fetchone()
            member_count_row = self._conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM chatroom_member
                WHERE room_id = (SELECT id FROM chat_room WHERE username = ?)
                """,
                (group_id,),
            ).fetchone()
            meta = {
                "owner": room["owner"] if room else None,
                "announcement": detail["announcement_"] if detail else None,
                "announcement_editor": detail["announcement_editor_"] if detail else None,
                "announcement_publish_time": detail["announcement_publish_time_"] if detail else None,
                "chat_room_status": detail["chat_room_status_"] if detail else None,
                "member_count": int(member_count_row["cnt"]) if member_count_row else 0,
            }
            self._group_meta_cache[group_id] = meta
            return meta
        except Exception:
            return None

    def build_target_info(self, target_id: str) -> dict[str, Any]:
        base = self.normalize_contact(target_id)
        info = {
            "username": target_id,
            "display_name": base["display_name"],
            "nick_name": base["nick_name"],
            "remark": base["remark"],
            "alias": base["alias"],
            "verify_flag": base["verify_flag"],
            "description": base["description"],
            "big_head_url": base["big_head_url"],
            "small_head_url": base["small_head_url"],
            "head_img_md5": base["head_img_md5"],
        }
        if target_id.endswith("@chatroom"):
            group_meta = self.lookup_group_meta(target_id) or {}
            info.update(
                {
                    "owner": group_meta.get("owner"),
                    "announcement": group_meta.get("announcement"),
                    "announcement_editor": group_meta.get("announcement_editor"),
                    "announcement_publish_time": group_meta.get("announcement_publish_time"),
                    "chat_room_status": group_meta.get("chat_room_status"),
                    "member_count": group_meta.get("member_count"),
                }
            )
        return info

    _SEARCHABLE = frozenset({"alias", "nick_name", "remark", "username"})

    def _search_where_clause(self) -> tuple[str, list[str]]:
        """Build WHERE clause and placeholders from detected columns."""
        search_cols = [c for c in self._columns if c in self._SEARCHABLE]
        clauses = " OR ".join(f"{c} LIKE ?" for c in search_cols)
        placeholders = ["%{query}%"] * len(search_cols)
        return f"WHERE {clauses}", placeholders

    def search_target(self, query: str) -> list[dict[str, Any]]:
        """Search contacts by available string columns (derived from schema)."""
        if self._conn is None:
            return []
        try:
            where_clause, ph = self._search_where_clause()
            if not where_clause:
                return []
            select = ", ".join(self._columns)
            params = [p.replace("{query}", query) for p in ph]
            rows = self._conn.execute(
                f"SELECT {select} FROM contact {where_clause} LIMIT 20",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def resolve_alias(self, alias: str) -> list[dict[str, Any]]:
        """Resolve one alias to one or more exact-match contacts."""
        if self._conn is None or "alias" not in self._columns:
            return []
        try:
            select = ", ".join(self._columns)
            rows = self._conn.execute(
                f"SELECT {select} FROM contact WHERE alias = ? ORDER BY username",
                (alias,),
            ).fetchall()
            return [self.normalize_contact(row["username"]) for row in rows]
        except Exception:
            return []

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
