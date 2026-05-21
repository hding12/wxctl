from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from wxctl.config import AppConfig


class CaptureKeyError(Exception):
    pass


def find_lldb_python_path() -> str | None:
    try:
        result = subprocess.run(["lldb", "-P"], capture_output=True, text=True)
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except FileNotFoundError:
        pass
    fallback = "/Library/Developer/CommandLineTools/Library/PrivateFrameworks/LLDB.framework/Versions/A/Resources/Python"
    return fallback if Path(fallback).is_dir() else None


def find_capture_python() -> str:
    candidates = [
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return sys.executable


def capture_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor" / "find_key_lldb.py"


def run_capture_key(
    config: AppConfig,
    python_bin: str | None = None,
    key_file: Path | None = None,
) -> int:
    lldb_python = find_lldb_python_path()
    if not lldb_python:
        raise CaptureKeyError("Could not locate LLDB Python runtime. Install Xcode Command Line Tools.")

    script = capture_script_path()
    if not script.is_file():
        raise CaptureKeyError(f"Capture script not found: {script}")

    effective_key_file = (key_file or config.wechat.key_file).expanduser().resolve()
    effective_key_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["WXCTL_XWECHAT_ROOT"] = str(config.wechat.xwechat_root)
    env["WXCTL_KEY_FILE"] = str(effective_key_file)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{lldb_python}:{existing}" if existing else lldb_python

    command = [python_bin or find_capture_python(), str(script)]
    result = subprocess.run(command, env=env)
    return int(result.returncode)
