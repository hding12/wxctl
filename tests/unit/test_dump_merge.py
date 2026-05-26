from __future__ import annotations

import json
from pathlib import Path
import sqlite3
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
        root=temp_runtime.app_support_root,
        wechat=WeChatConfig(
            xwechat_root=temp_runtime.app_support_root / "xwechat",
            key_file=temp_runtime.state_root / "wechat_keys.json",
            decrypted_root=temp_runtime.app_support_root / "decrypted",
        ),
        runtime=temp_runtime,
    )


@pytest.fixture
def seeded_contact_db(app_config):
    contact_dir = app_config.wechat.decrypted_root / "contact"
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
    conn.execute("CREATE TABLE chat_room (id INTEGER PRIMARY KEY, username TEXT, owner TEXT, ext_buffer BLOB)")
    conn.execute(
        """
        CREATE TABLE chat_room_info_detail (
            room_id_ INTEGER,
            username_ TEXT,
            announcement_ TEXT,
            announcement_editor_ TEXT,
            announcement_publish_time_ INTEGER,
            chat_room_status_ INTEGER,
            xml_announcement_ TEXT,
            ext_buffer_ BLOB
        )
        """
    )
    conn.execute("CREATE TABLE chatroom_member (room_id INTEGER, member_id INTEGER)")
    conn.execute(
        """
        INSERT INTO contact(username, alias, remark, nick_name, verify_flag, description, big_head_url, small_head_url, head_img_md5)
        VALUES
          ('wxid_foo', 'alias_foo', 'Remark Foo', 'Nick Foo', 0, 'desc foo', 'https://big/foo', 'https://small/foo', 'md5foo'),
          ('wxid_sender', 'alias_sender', '', 'Nick Sender', 24, 'sender desc', 'https://big/sender', 'https://small/sender', 'md5sender'),
          ('123@chatroom', '', '', 'Project Group', 0, 'group desc', '', '', 'groupmd5')
        """
    )
    conn.execute("INSERT INTO chat_room(id, username, owner, ext_buffer) VALUES (1, '123@chatroom', 'wxid_owner', X'00')")
    conn.execute(
        """
        INSERT INTO chat_room_info_detail(
            room_id_, username_, announcement_, announcement_editor_, announcement_publish_time_, chat_room_status_, xml_announcement_, ext_buffer_
        ) VALUES (1, '123@chatroom', 'Ship it', 'wxid_owner', 1700000200, 131072, '', X'00')
        """
    )
    conn.executemany(
        "INSERT INTO chatroom_member(room_id, member_id) VALUES (1, ?)",
        [(1,), (2,), (3,)],
    )
    conn.commit()
    conn.close()
    return db_path


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


@pytest.fixture
def seeded_group_warehouse(app_config):
    warehouse = Warehouse(app_config.runtime)
    sync_run_id = warehouse.start_sync_run("test_dump_group")
    warehouse.upsert_message(
        sync_run_id,
        payload={
            "source_db": "message_0.db",
            "target_id": "123@chatroom",
            "conversation_hash": "group_hash",
            "local_id": 1,
            "server_id": 300,
            "raw_type": 1,
            "ts": 1700000200,
            "sender_wxid": "wxid_sender",
            "is_self": 0,
            "message_content": "hello group",
            "packed_info_data": None,
        },
        decoded={"kind": "text", "text": "hello group", "decoded": {"text": "hello group"}},
        assets=[],
    )
    warehouse.commit()
    return warehouse


def test_dump_merge_preserves_old_orphan_record(tmp_path, app_config, seeded_contact_db, seeded_warehouse):
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


def test_dump_merge_overwrites_matching_records(tmp_path, app_config, seeded_contact_db, seeded_warehouse):
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


def test_dump_merge_idempotent(app_config, seeded_contact_db, seeded_warehouse):
    records1 = dump_target(app_config, target="wxid_foo")
    records2 = dump_target(app_config, target="wxid_foo")
    assert records1 == records2


def test_dump_merge_handles_empty_old_file(tmp_path, app_config, seeded_contact_db, seeded_warehouse):
    old_path = tmp_path / "empty.jsonl"
    old_path.write_text("", encoding="utf-8")

    records = dump_target(app_config, target="wxid_foo", input_path=str(old_path))
    assert len(records) == 2
    assert [r["local_id"] for r in records] == [1, 2]


def test_dump_includes_direct_target_and_sender_contact_info(app_config, seeded_contact_db, seeded_warehouse):
    records = dump_target(app_config, target="wxid_foo")
    assert len(records) == 2
    first = records[0]
    assert first["target_info"]["username"] == "wxid_foo"
    assert first["target_info"]["display_name"] == "Remark Foo"
    assert first["target_info"]["alias"] == "alias_foo"
    assert first["target_info"]["big_head_url"] == "https://big/foo"
    assert first["sender_info"]["wxid"] == "wxid_sender"
    assert first["sender_info"]["display_name"] == "Nick Sender"
    assert first["sender_info"]["alias"] == "alias_sender"
    assert first["sender_info"]["verify_flag"] == 24


def test_dump_includes_group_contact_metadata(app_config, seeded_contact_db, seeded_group_warehouse):
    records = dump_target(app_config, target="123@chatroom")
    assert len(records) == 1
    first = records[0]
    assert first["target_info"]["username"] == "123@chatroom"
    assert first["target_info"]["display_name"] == "Project Group"
    assert first["target_info"]["owner"] == "wxid_owner"
    assert first["target_info"]["announcement"] == "Ship it"
    assert first["target_info"]["announcement_publish_time"] == 1700000200
    assert first["target_info"]["chat_room_status"] == 131072
    assert first["target_info"]["member_count"] == 3
