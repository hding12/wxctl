from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

import yaml


@dataclass(slots=True)
class WeChatConfig:
    xwechat_root: Path
    key_file: Path
    decrypted_root: Path


@dataclass(slots=True)
class RuntimeConfig:
    app_support_root: Path
    warehouse_db: Path
    raw_root: Path
    export_root: Path
    log_root: Path
    state_root: Path


@dataclass(slots=True)
class AppConfig:
    root: Path
    wechat: WeChatConfig
    runtime: RuntimeConfig


DEFAULT_CONFIG_ENV = "WXCTL_CONFIG"
DEFAULT_CONFIG_RELATIVE = Path("configs/app.yaml")


def _expand(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expanduser(str(value))).resolve()


def load_config(config_path: str | None = None) -> AppConfig:
    root = Path(__file__).resolve().parents[2]
    path = Path(config_path or os.environ.get(DEFAULT_CONFIG_ENV, root / DEFAULT_CONFIG_RELATIVE))
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    runtime = RuntimeConfig(
        app_support_root=_expand(data["runtime"]["app_support_root"]),
        warehouse_db=_expand(data["runtime"]["warehouse_db"]),
        raw_root=_expand(data["runtime"]["raw_root"]),
        export_root=_expand(data["runtime"]["export_root"]),
        log_root=_expand(data["runtime"]["log_root"]),
        state_root=_expand(data["runtime"]["state_root"]),
    )
    key_default = runtime.state_root / "wechat_keys.json"
    decrypted_default = runtime.app_support_root / "decrypted"
    wechat_data = data["wechat"]
    wechat = WeChatConfig(
        xwechat_root=_expand(wechat_data["xwechat_root"]),
        key_file=_expand(wechat_data.get("key_file", key_default)),
        decrypted_root=_expand(wechat_data.get("decrypted_root", decrypted_default)),
    )
    return AppConfig(root=root, wechat=wechat, runtime=runtime)
