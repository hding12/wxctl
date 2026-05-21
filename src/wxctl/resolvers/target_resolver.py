from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


# Actual contact.db schema (confirmed from decrypt output):
#   username, remark, nick_name
# No alias or avatar columns in the contact table.
_CONTACT_COLUMNS = ["username", "remark", "nick_name"]
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
            "nick_name": None,
            "remark": None,
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

    _SEARCHABLE = frozenset({"nick_name", "remark", "username"})

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

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
