from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from wxctl.adapters.sqlite_source import SourceRepository
from wxctl.config import load_config
from wxctl.services.capture_key import CaptureKeyError, run_capture_key
from wxctl.services.decrypt import DecryptError, decrypt_all
from wxctl.services.doctor import run_doctor
from wxctl.services.dump import dump_target, write_jsonl
from wxctl.services.sync import SyncError, sync_targets


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _target_payload(target) -> dict:
    return asdict(target)


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = run_doctor(config)
    if args.json:
        _print_json(report)
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    return 0


def cmd_capture_key(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    try:
        return run_capture_key(
            config,
            python_bin=args.python,
            key_file=None if args.keys is None else Path(args.keys).expanduser().resolve(),
        )
    except CaptureKeyError as exc:
        raise SystemExit(str(exc)) from exc


def cmd_decrypt(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    try:
        result = decrypt_all(
            config,
            key_file=None if args.keys is None else Path(args.keys).expanduser().resolve(),
            output_dir=None if args.output is None else Path(args.output).expanduser().resolve(),
        )
    except DecryptError as exc:
        raise SystemExit(str(exc)) from exc
    _print_json(result)
    return 0


def cmd_targets(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = SourceRepository(config.wechat.decrypted_root)
    targets = repo.list_targets(kind=args.kind)
    if args.format == "json":
        _print_json([_target_payload(target) for target in targets])
        return 0
    if args.format == "jsonl":
        for target in targets:
            print(json.dumps(_target_payload(target), ensure_ascii=False))
        return 0
    print(f"{'kind':<8} {'messages':>10} {'text':>10}  target_id")
    print("-" * 80)
    for target in targets:
        print(f"{target.kind:<8} {target.total_count:>10} {target.text_count:>10}  {target.target_id}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    targets = []
    if args.target:
        targets.extend(args.target)
    if args.group:
        targets.extend(args.group)
    if not targets:
        raise SystemExit("sync requires at least one --target or --group")
    try:
        result = sync_targets(config, targets)
    except SyncError as exc:
        raise SystemExit(str(exc)) from exc
    _print_json(result)
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    target = args.target or args.group
    if not target:
        raise SystemExit("dump requires --target or --group")
    records = dump_target(config, target=target, refresh=args.refresh, limit=args.limit)
    if args.stdout:
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        return 0
    path = write_jsonl(records, args.output)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wxctl", description="WeChat interaction control CLI")
    parser.add_argument("--config", default=None, help="Path to app.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Inspect upstream state")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    capture = sub.add_parser("capture-key", help="Capture WeChat SQLCipher keys via LLDB")
    capture.add_argument("--python", default=None, help="Python binary used to run the vendored LLDB capture script")
    capture.add_argument("--keys", default=None, help="Override output key file path")
    capture.set_defaults(func=cmd_capture_key)

    decrypt = sub.add_parser("decrypt", help="Decrypt WeChat databases with the captured keys")
    decrypt.add_argument("--keys", default=None, help="Override key file path")
    decrypt.add_argument("--output", default=None, help="Override decrypted output directory")
    decrypt.set_defaults(func=cmd_decrypt)

    targets = sub.add_parser("targets", help="List available direct chats and groups")
    targets.add_argument("--kind", choices=["direct", "group"], default=None)
    targets.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    targets.set_defaults(func=cmd_targets)

    sync = sub.add_parser("sync", help="Sync target messages into the warehouse")
    sync.add_argument("--target", action="append", default=[])
    sync.add_argument("--group", action="append", default=[])
    sync.set_defaults(func=cmd_sync)

    dump = sub.add_parser("dump", help="Dump warehouse messages for one target or group")
    dump.add_argument("--target", default=None)
    dump.add_argument("--group", default=None)
    dump.add_argument("--refresh", action="store_true")
    dump.add_argument("--stdout", action="store_true")
    dump.add_argument("--output", default=None)
    dump.add_argument("--limit", type=int, default=None)
    dump.set_defaults(func=cmd_dump)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
