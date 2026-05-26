from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from wxctl.resolvers.target_resolver import ContactDB


def _build_contact_db(base: Path) -> Path:
    contact_dir = base / "contact"
    contact_dir.mkdir(parents=True, exist_ok=True)
    db_path = contact_dir / "contact.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE contact (
            id INTEGER PRIMARY KEY,
            username TEXT,
            alias TEXT,
            remark TEXT,
            nick_name TEXT,
            verify_flag INTEGER,
            description TEXT,
            big_head_url TEXT,
            small_head_url TEXT,
            head_img_md5 TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO contact(username, alias, remark, nick_name, verify_flag, description, big_head_url, small_head_url, head_img_md5)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("wxid_a", "_470279647", "。", "。", 0, "", "https://big/a", "https://small/a", "md5a"),
            ("wxid_b", "_470279647", "", "备用", 0, "", "https://big/b", "https://small/b", "md5b"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_resolve_alias_returns_all_exact_matches():
    tmpdir = Path(tempfile.mkdtemp(prefix="wxctl_contactdb_"))
    _build_contact_db(tmpdir)
    contacts = ContactDB(tmpdir)
    rows = contacts.resolve_alias("_470279647")
    assert len(rows) == 2
    assert rows[0]["username"] == "wxid_a"
    assert rows[0]["display_name"] == "。"
    assert rows[1]["username"] == "wxid_b"
    assert rows[1]["display_name"] == "备用"
    contacts.close()

