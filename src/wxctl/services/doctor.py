from __future__ import annotations

import shutil

from wxctl.adapters.sqlite_source import SourceRepository
from wxctl.adapters.wechat_fs import find_db_storage_dir, resolve_self_wxid
from wxctl.config import AppConfig
from wxctl.services.capture_key import capture_script_path, find_capture_python, find_lldb_python_path


def run_doctor(config: AppConfig) -> dict:
    source = SourceRepository(config.wechat.decrypted_root)
    message_dbs = source.message_dbs()
    key_file = config.wechat.key_file
    self_wxid = resolve_self_wxid(config.wechat.xwechat_root)
    db_storage_dir = find_db_storage_dir(config.wechat.xwechat_root)
    return {
        "capture_script_exists": capture_script_path().exists(),
        "capture_python": find_capture_python(),
        "lldb_python": find_lldb_python_path(),
        "db_storage_dir": str(db_storage_dir) if db_storage_dir else None,
        "decrypted_root_exists": config.wechat.decrypted_root.exists(),
        "message_db_count": len(message_dbs),
        "message_dbs": [str(path) for path in message_dbs],
        "key_file_exists": key_file.exists(),
        "key_file": str(key_file),
        "self_wxid": self_wxid,
        "warehouse_db": str(config.runtime.warehouse_db),
        "xwechat_root": str(config.wechat.xwechat_root),
        "sqlcipher": shutil.which("sqlcipher"),
        "zstd": shutil.which("zstd"),
    }
