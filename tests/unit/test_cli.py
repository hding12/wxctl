from __future__ import annotations

import argparse
import json
from pathlib import Path

from wxctl.adapters.sqlite_source import TargetSummary
from wxctl.cli import build_parser, cmd_capture_key, cmd_preview, cmd_targets
from wxctl.config import AppConfig, RuntimeConfig, WeChatConfig


def _dummy_config() -> AppConfig:
    return AppConfig(
        root=Path("/tmp/wxctl"),
        wechat=WeChatConfig(
            xwechat_root=Path("/tmp/xwechat"),
            key_file=Path("/tmp/runtime/state/wechat_keys.json"),
            decrypted_root=Path("/tmp/decrypted"),
        ),
        runtime=RuntimeConfig(
            app_support_root=Path("/tmp/runtime"),
            warehouse_db=Path("/tmp/runtime/wxctl.sqlite3"),
            raw_root=Path("/tmp/runtime/raw"),
            export_root=Path("/tmp/runtime/exports"),
            log_root=Path("/tmp/runtime/logs"),
            state_root=Path("/tmp/runtime/state"),
        ),
    )


def test_cmd_targets_json_formats_with_slots_dataclass(monkeypatch, capsys):
    sample = [
        TargetSummary(
            target_id="robby9090",
            kind="direct",
            conversation_hash="abc123",
            total_count=42,
            text_count=30,
            first_ts=1700000000,
            last_ts=1700001234,
        )
    ]

    class FakeRepo:
        def __init__(self, decrypted_root: Path) -> None:
            self.decrypted_root = decrypted_root

        def list_targets(self, kind: str | None = None):
            return sample

    monkeypatch.setattr("wxctl.cli.load_config", lambda _: _dummy_config())
    monkeypatch.setattr("wxctl.cli.SourceRepository", FakeRepo)

    json_args = argparse.Namespace(config=None, kind=None, format="json")
    assert cmd_targets(json_args) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == [
        {
            "target_id": "robby9090",
            "kind": "direct",
            "conversation_hash": "abc123",
            "total_count": 42,
            "text_count": 30,
            "first_ts": 1700000000,
            "last_ts": 1700001234,
        }
    ]

    jsonl_args = argparse.Namespace(config=None, kind=None, format="jsonl")
    assert cmd_targets(jsonl_args) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["target_id"] == "robby9090"


def test_cmd_capture_key_accepts_key_override(monkeypatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr("wxctl.cli.load_config", lambda _: _dummy_config())

    def fake_run_capture_key(config, python_bin=None, key_file=None):
        seen["python_bin"] = python_bin
        seen["key_file"] = key_file
        return 0

    monkeypatch.setattr("wxctl.cli.run_capture_key", fake_run_capture_key)

    args = argparse.Namespace(
        config=None,
        python="/usr/bin/python3",
        keys="/tmp/custom/wechat_keys.json",
    )
    assert cmd_capture_key(args) == 0
    assert seen["python_bin"] == "/usr/bin/python3"
    assert seen["key_file"] == Path("/tmp/custom/wechat_keys.json").resolve()


def test_cmd_preview_json(monkeypatch, capsys):
    monkeypatch.setattr("wxctl.cli.load_config", lambda _: _dummy_config())
    monkeypatch.setattr(
        "wxctl.cli.preview_targets",
        lambda config, kind, limit, snippets_per_target, refresh: [
            {
                "target_id": "wxid_candidate",
                "kind": kind,
                "total_count": 20,
                "text_count": 10,
                "first_ts": 1700000000,
                "first_datetime": "2023-11-14 22:13:20",
                "last_ts": 1700001000,
                "last_datetime": "2023-11-14 22:30:00",
                "snippets": [
                    {
                        "datetime": "2023-11-14 22:30:00",
                        "is_self": False,
                        "sender_wxid": "wxid_sender",
                        "kind": "text",
                        "summary": "最近消息",
                    }
                ],
            }
        ],
    )

    args = argparse.Namespace(
        config=None,
        kind="group",
        limit=5,
        snippets=2,
        refresh=False,
        format="json",
    )
    assert cmd_preview(args) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed[0]["target_id"] == "wxid_candidate"
    assert parsed[0]["kind"] == "group"
    assert parsed[0]["snippets"][0]["summary"] == "最近消息"


def test_build_parser_accepts_dump_input():
    parser = build_parser()
    args = parser.parse_args(
        [
            "dump",
            "--target",
            "wxid_xxx",
            "--input",
            "archive-old.jsonl",
            "--output",
            "archive-new.jsonl",
        ]
    )
    assert args.target == "wxid_xxx"
    assert args.input == "archive-old.jsonl"
    assert args.output == "archive-new.jsonl"
