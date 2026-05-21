"""Integration tests for the sync and dump loop.

Tests run against a temporary SQLite warehouse with synthetic
source data, verifying the end-to-end message pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import sqlite3
import tempfile

from wxctl.config import AppConfig, RuntimeConfig, WeChatConfig
from wxctl.store.engine import Warehouse
from wxctl.decoders.registry import decode_message, DecodeContext

import pytest


@pytest.fixture
def temp_runtime() -> RuntimeConfig:
    tmpdir = Path(tempfile.mkdtemp(prefix="wxctl_test_"))
    return RuntimeConfig(
        app_support_root=tmpdir,
        warehouse_db=tmpdir / "warehouse/wxctl.sqlite3",
        raw_root=tmpdir / "raw",
        export_root=tmpdir / "exports",
        log_root=tmpdir / "logs",
        state_root=tmpdir / "state",
    )


@pytest.fixture
def warehouse(temp_runtime) -> Warehouse:
    return Warehouse(temp_runtime)


@pytest.fixture
def decode_ctx() -> DecodeContext:
    return DecodeContext(
        conversation_hash="abc123def456abc123def456abc123de",
        xwechat_root=Path("/tmp"),
        self_wxid="wxid_self",
    )


def test_warehouse_initialization(temp_runtime):
    """Verify warehouse creates schema and directories."""
    warehouse = Warehouse(temp_runtime)
    tables = warehouse.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row["name"] for row in tables}
    assert "messages" in table_names
    assert "conversations" in table_names
    assert "sync_runs" in table_names
    assert "assets" in table_names


def test_sync_run_lifecycle(warehouse):
    """Verify sync run create and finish."""
    run_id = warehouse.start_sync_run("test_scope")
    assert run_id >= 1
    warehouse.finish_sync_run(
        run_id, inserted=10, updated=2, skipped=0, failures=1,
        failure_samples=[{"msg": "test failure"}],
        notes={},
    )
    rows = warehouse.conn.execute(
        "SELECT * FROM sync_runs WHERE id = ?", (run_id,)
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["inserted_messages"] == 10
    assert row["updated_messages"] == 2
    assert row["decode_failures"] == 1


def test_message_upsert_idempotent(warehouse, decode_ctx):
    """Verify repeated upsert doesn't create duplicates."""
    sync_run_id = warehouse.start_sync_run("test_idempotent")
    payload = {
        "source_db": "message_1.db",
        "target_id": "wxid_test123",
        "conversation_hash": "abc",
        "local_id": 42,
        "server_id": 999,
        "raw_type": 1,
        "ts": 1700000000,
        "sender_wxid": "wxid_sender",
        "is_self": 0,
        "message_content": "hello",
        "packed_info": None,
    }
    decoded = {"kind": "text", "text": "hello", "decoded": {"text": "hello"}}

    # First upsert
    path1, was_inserted1 = warehouse.upsert_message(sync_run_id, payload, decoded, [])
    assert was_inserted1 is True

    # Second upsert (same message)
    path2, was_inserted2 = warehouse.upsert_message(sync_run_id, payload, decoded, [])
    assert was_inserted2 is False

    count = warehouse.conn.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE target_id = ? AND local_id = ?",
        ("wxid_test123", 42),
    ).fetchone()["cnt"]
    assert count == 1


def test_message_round_trip(warehouse, decode_ctx):
    """Verify a message can be upserted and fetched back."""
    sync_run_id = warehouse.start_sync_run("test_roundtrip")
    payload = {
        "source_db": "message_1.db",
        "target_id": "wxid_test456",
        "conversation_hash": "def",
        "local_id": 1,
        "server_id": 1000,
        "raw_type": 1,
        "ts": 1700000100,
        "sender_wxid": "wxid_sender",
        "is_self": 1,
        "message_content": "round trip test",
        "packed_info_data": None,
    }
    decoded = {"kind": "text", "text": "round trip test", "decoded": {"text": "round trip test"}}

    path, _ = warehouse.upsert_message(sync_run_id, payload, decoded, [])
    warehouse.commit()

    rows = warehouse.fetch_messages("wxid_test456")
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "text"
    assert row["text"] == "round trip test"
    assert row["is_self"] == 1


def test_asset_storage(warehouse, decode_ctx):
    """Verify assets are stored and retrievable alongside messages."""
    sync_run_id = warehouse.start_sync_run("test_assets")
    payload = {
        "source_db": "message_1.db",
        "target_id": "wxid_asset_test",
        "conversation_hash": "asset_hash",
        "local_id": 1,
        "server_id": 2000,
        "raw_type": 3,
        "ts": 1700000200,
        "sender_wxid": "wxid_sender",
        "is_self": 0,
        "message_content": b"<img md5='abc123'/>",
        "packed_info_data": b'{"Md5": "abc123"}',
    }
    decoded = {"kind": "image", "text": None, "decoded": {}}
    assets = [
        {"kind": "image_candidate", "local_path": "/tmp/test.jpg", "meta": "test"},
    ]

    path, _ = warehouse.upsert_message(sync_run_id, payload, decoded, assets)
    warehouse.commit()

    fetched_assets = warehouse.fetch_assets("message_1.db", "wxid_asset_test", 1)
    assert len(fetched_assets) == 1
    assert fetched_assets[0]["kind"] == "image_candidate"


def test_raw_payload_archive(warehouse, decode_ctx):
    """Verify raw payloads are written to disk."""
    sync_run_id = warehouse.start_sync_run("test_raw")
    payload = {
        "source_db": "message_1.db",
        "target_id": "wxid_raw_test",
        "conversation_hash": "raw_hash",
        "local_id": 1,
        "server_id": 3000,
        "raw_type": 1,
        "ts": 1700000300,
        "sender_wxid": "wxid_sender",
        "is_self": 0,
        "message_content": "raw content archive test",
        "packed_info_data": None,
    }
    decoded = {"kind": "text", "text": "raw content archive test", "decoded": {"text": "raw content archive test"}}

    payload_path, _ = warehouse.upsert_message(sync_run_id, payload, decoded, [])
    assert Path(payload_path).exists()
    raw_data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    assert raw_data["message_content_text"] == "raw content archive test"


def test_coverage_summary(warehouse):
    """Verify coverage summary aggregates by kind."""
    sync_run_id = warehouse.start_sync_run("test_coverage")

    # Insert messages of different kinds
    kinds_data = [
        (1, "text", "hello"),
        (1, "text", "world"),
        (3, "image", None),
        (10000, "system", "recalled"),
    ]
    for raw_type, kind, text in kinds_data:
        payload = {
            "source_db": "message_1.db",
            "target_id": "wxid_coverage",
            "conversation_hash": "cov_hash",
            "local_id": hash(text or kind) % 100000,
            "server_id": 0,
            "raw_type": raw_type,
            "ts": 1700000400,
            "sender_wxid": "wxid_sender",
            "is_self": 0,
            "message_content": text,
            "packed_info_data": None,
        }
        decoded = {"kind": kind, "text": text, "decoded": {}}
        warehouse.upsert_message(sync_run_id, payload, decoded, [])
    warehouse.commit()

    coverage = warehouse.get_coverage_summary()
    assert coverage["total"] == 4
    assert coverage["by_kind"]["text"] == 2
    assert coverage["by_kind"]["image"] == 1
    assert coverage["by_kind"]["system"] == 1
    assert coverage["unknown_count"] == 0


def test_conversation_upsert(warehouse):
    """Verify conversation metadata upsert."""
    warehouse.upsert_conversation({
        "target_id": "wxid_conv",
        "kind": "direct",
        "conversation_hash": "conv_hash",
        "first_ts": 1700000000,
        "last_ts": 1700001000,
        "total_count": 50,
        "text_count": 30,
    })
    warehouse.commit()

    row = warehouse.conn.execute(
        "SELECT * FROM conversations WHERE target_id = ?", ("wxid_conv",)
    ).fetchone()
    assert row["kind"] == "direct"
    assert row["total_count"] == 50
