from __future__ import annotations

from pathlib import Path

from wxctl.config import load_config


def test_load_config_derives_internal_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "app.yaml"
    config_file.write_text(
        """
wechat:
  xwechat_root: ~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files
runtime:
  app_support_root: /tmp/wxctl
  warehouse_db: /tmp/wxctl/warehouse/wxctl.sqlite3
  raw_root: /tmp/wxctl/raw
  export_root: /tmp/wxctl/exports
  log_root: /tmp/wxctl/logs
  state_root: /tmp/wxctl/state
""".strip(),
        encoding="utf-8",
    )

    config = load_config(str(config_file))
    assert config.wechat.decrypted_root == Path("/tmp/wxctl/decrypted").resolve()
    assert config.wechat.key_file == Path("/tmp/wxctl/state/wechat_keys.json").resolve()
