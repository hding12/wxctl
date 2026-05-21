from __future__ import annotations

from dataclasses import asdict
from typing import Any

from wxctl.adapters.sqlite_source import SourceRepository
from wxctl.adapters.wechat_fs import resolve_self_wxid
from wxctl.config import AppConfig
from wxctl.decoders.registry import DecodeContext, decode_message
from wxctl.resolvers.sender_resolver import SenderResolver
from wxctl.store.engine import Warehouse


class SyncError(Exception):
    pass


def sync_targets(config: AppConfig, targets: list[str], full_resync: bool = False) -> dict:
    source = SourceRepository(config.wechat.decrypted_root)
    warehouse = Warehouse(config.runtime)
    sender_resolver = SenderResolver(config.wechat.decrypted_root)
    self_wxid = resolve_self_wxid(config.wechat.xwechat_root)
    available = {item.target_id: item for item in source.list_targets()}
    unknown = [target for target in targets if target not in available]
    if unknown:
        raise SyncError(f"Unknown targets: {', '.join(unknown)}")

    sync_run_id = warehouse.start_sync_run(scope=",".join(targets))
    inserted = 0
    updated = 0
    skipped = 0
    failures = 0
    failure_samples: list[dict[str, Any]] = []
    total_processed = 0
    by_kind: dict[str, int] = {}
    results: dict[str, dict[str, Any]] = {}

    for target in targets:
        summary = available[target]
        warehouse.upsert_conversation(asdict(summary))
        context = DecodeContext(
            conversation_hash=summary.conversation_hash,
            xwechat_root=config.wechat.xwechat_root,
            self_wxid=self_wxid or "",
        )
        target_processed = 0
        target_failures = 0

        for payload in source.iter_messages(target, self_wxid):
            total_processed += 1
            target_processed += 1
            try:
                result = decode_message(
                    payload["raw_type"],
                    payload.get("message_content"),
                    payload.get("packed_info_data"),
                    context,
                )
                # Resolve sender enrichment
                sender_wxid = payload.get("sender_wxid")
                sender_info = sender_resolver.resolve(sender_wxid) if sender_wxid else None
                payload_path, was_inserted = warehouse.upsert_message(
                    sync_run_id=sync_run_id,
                    payload=payload,
                    decoded={"kind": result.kind, "text": result.text, "decoded": result.decoded},
                    assets=result.assets,
                    sender_info=sender_info,
                )
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1

                by_kind[result.kind] = by_kind.get(result.kind, 0) + 1
            except Exception as exc:
                failures += 1
                target_failures += 1
                if len(failure_samples) < 10:
                    failure_samples.append({
                        "target_id": target,
                        "local_id": payload.get("local_id"),
                        "raw_type": payload.get("raw_type"),
                        "error": str(exc)[:200],
                    })

        warehouse.commit()
        results[target] = {
            "processed": target_processed,
            "failures": target_failures,
        }

    # Coverage: compare with source totals
    coverage: dict[str, Any] = {}
    for target in targets:
        summary = available.get(target)
        if summary:
            source_total = summary.total_count
            warehouse_total = warehouse.conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE target_id = ?", (target,)
            ).fetchone()["cnt"]
            coverage[target] = {
                "source_total": source_total,
                "warehouse_total": warehouse_total,
                "coverage_pct": round(warehouse_total / source_total * 100, 1) if source_total else 100.0,
            }

    warehouse.finish_sync_run(
        sync_run_id=sync_run_id,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        failures=failures,
        failure_samples=failure_samples,
        notes={
            "targets": targets,
            "total_processed": total_processed,
            "by_kind": by_kind,
        },
    )
    return {
        "sync_run_id": sync_run_id,
        "targets": targets,
        "inserted_messages": inserted,
        "updated_messages": updated,
        "skipped_messages": skipped,
        "decode_failures": failures,
        "failure_samples": failure_samples[:5],
        "total_processed": total_processed,
        "by_kind": by_kind,
        "coverage": coverage,
    }
