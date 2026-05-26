from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from wxctl.config import AppConfig, RuntimeConfig, WeChatConfig
from wxctl.services.dump import dump_target
from wxctl.store.engine import Warehouse


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
def app_config(temp_runtime) -> AppConfig:
    return AppConfig(
        root=Path("/tmp"),
        wechat=WeChatConfig(
            xwechat_root=Path("/tmp/xwechat"),
            key_file=Path("/tmp/runtime/state/wechat_keys.json"),
            decrypted_root=Path("/tmp/decrypted"),
        ),
        runtime=temp_runtime,
    )


@pytest.fixture
def seeded_warehouse(app_config):
    warehouse = Warehouse(app_config.runtime)
    sync_run_id = warehouse.start_sync_run("test_dump_merge")

    warehouse.upsert_message(
        sync_run_id,
        payload={
            "source_db": "message_0.db",
            "target_id": "wxid_foo",
            "conversation_hash": "hash_abc",
            "local_id": 1,
            "server_id": 100,
            "raw_type": 1,
            "ts": 1700000000,
            "sender_wxid": "wxid_sender",
            "is_self": 0,
            "message_content": "updated text",
            "packed_info_data": None,
        },
        decoded={"kind": "text", "text": "updated text", "decoded": {"text": "updated text"}},
        assets=[],
    )
    warehouse.upsert_message(
        sync_run_id,
        payload={
            "source_db": "message_0.db",
            "target_id": "wxid_foo",
            "conversation_hash": "hash_abc",
            "local_id": 2,
            "server_id": 200,
            "raw_type": 1,
            "ts": 1700000100,
            "sender_wxid": "wxid_sender",
            "is_self": 1,
            "message_content": "second text",
            "packed_info_data": None,
        },
        decoded={"kind": "text", "text": "second text", "decoded": {"text": "second text"}},
        assets=[],
    )
    warehouse.commit()
    return warehouse


def test_dump_merge_preserves_old_orphan_record(tmp_path, app_config, seeded_warehouse):
    old_path = tmp_path / "old.jsonl"
    old_path.write_text(
        json.dumps({"target_id": "wxid_foo", "source_db": "message_9.db", "local_id": 99, "kind": "text"}) + "\n",
        encoding="utf-8",
    )

    records = dump_target(app_config, target="wxid_foo", input_path=str(old_path))
    local_ids = [r["local_id"] for r in records]
    assert 99 in local_ids
    assert 1 in local_ids
    assert 2 in local_ids


def test_dump_merge_overwrites_matching_records(tmp_path, app_config, seeded_warehouse):
    old_path = tmp_path / "old.jsonl"
    old_path.write_text(
        json.dumps(
            {
                "target_id": "wxid_foo",
                "source_db": "message_0.db",
                "local_id": 1,
                "kind": "text",
                "text": "old text",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    records = dump_target(app_config, target="wxid_foo", input_path=str(old_path))
    match = [r for r in records if r["local_id"] == 1 and r["source_db"] == "message_0.db"]
    assert len(match) == 1
    assert match[0]["text"] == "updated text"


def test_dump_merge_idempotent(app_config, seeded_warehouse):
    records1 = dump_target(app_config, target="wxid_foo")
    records2 = dump_target(app_config, target="wxid_foo")
    assert records1 == records2


def test_dump_merge_handles_empty_old_file(tmp_path, app_config, seeded_warehouse):
    old_path = tmp_path / "empty.jsonl"
    old_path.write_text("", encoding="utf-8")

    records = dump_target(app_config, target="wxid_foo", input_path=str(old_path))
    assert len(records) == 2
    assert [r["local_id"] for r in records] == [1, 2]
