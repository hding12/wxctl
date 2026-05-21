from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from wxctl.adapters.wechat_fs import find_db_storage_dir
from wxctl.config import AppConfig


class DecryptError(Exception):
    pass


def find_sqlcipher() -> str | None:
    brew_path = "/opt/homebrew/opt/sqlcipher/bin/sqlcipher"
    if Path(brew_path).is_file():
        return brew_path
    return shutil.which("sqlcipher")


def decrypt_database(sqlcipher_bin: str, src_path: Path, dst_path: Path, key_hex: str) -> tuple[bool, str]:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.exists():
        dst_path.unlink()

    sql_commands = f"""PRAGMA key = "x'{key_hex}'";
PRAGMA cipher_page_size = 4096;
ATTACH DATABASE '{dst_path}' AS plaintext KEY '';
SELECT sqlcipher_export('plaintext');
DETACH DATABASE plaintext;
"""

    try:
        result = subprocess.run(
            [sqlcipher_bin, str(src_path)],
            input=sql_commands,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or "Error" in result.stderr:
            return False, result.stderr.strip() or "sqlcipher failed"
        if not dst_path.is_file() or dst_path.stat().st_size == 0:
            return False, "output file is empty"
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:
        return False, str(exc)


def decrypt_all(
    config: AppConfig,
    key_file: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    key_path = (key_file or config.wechat.key_file).expanduser().resolve()
    if not key_path.is_file():
        raise DecryptError(f"Key file not found: {key_path}")

    sqlcipher_bin = find_sqlcipher()
    if not sqlcipher_bin:
        raise DecryptError("sqlcipher not found. Install it with: brew install sqlcipher")

    db_dir = find_db_storage_dir(config.wechat.xwechat_root)
    if db_dir is None:
        raise DecryptError(f"Could not find db_storage under {config.wechat.xwechat_root}")

    output_root = (output_dir or config.wechat.decrypted_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    data = json.loads(key_path.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not str(k).startswith("__")}

    passed = 0
    failed = 0
    skipped = 0
    failures: list[dict[str, str]] = []
    decrypted_files: list[str] = []

    for db_rel_path, key_hex in sorted(entries.items()):
        src = db_dir / db_rel_path
        dst = output_root / db_rel_path

        if not src.is_file():
            skipped += 1
            failures.append({"db": db_rel_path, "error": "source file not found"})
            continue

        success, detail = decrypt_database(sqlcipher_bin, src, dst, key_hex)
        if success:
            passed += 1
            decrypted_files.append(str(dst))
        else:
            failed += 1
            failures.append({"db": db_rel_path, "error": detail})

    return {
        "key_file": str(key_path),
        "db_storage_dir": str(db_dir),
        "output_dir": str(output_root),
        "sqlcipher": sqlcipher_bin,
        "requested": len(entries),
        "decrypted": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": failures[:20],
        "decrypted_files": decrypted_files,
    }
