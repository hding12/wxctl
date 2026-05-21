# 2026-05-21 wxctl Implementation Plan

## Objectives

Build a local CLI that can:

- enumerate available direct chats and groups
- incrementally ingest full encrypted chat interactions into a local warehouse
- dump all messages for one target or one group in structured JSONL
- degrade gracefully when `contact.db` is unavailable
- expose clear health and coverage signals for future automation

## Control Objectives

- Stability: repeated sync must be idempotent
- Observability: each sync run must capture counts, drift, and decode failures
- Controllability: user can refresh one target, one group, or all targets
- Recoverability: raw payload archive allows replay after decoder upgrades

## Milestones

### M1: Scaffold and Warehouse Baseline
- repo scaffold
- config loader
- doctor command
- schema creation
- source probing

Acceptance:
- `doctor` reports source DBs, self wxid, key file, warehouse path, zstd/sqlcipher availability

### M2: Target Discovery and Direct Dump
- target enumeration from `Name2Id`
- message scan from `message_*.db`
- normalized warehouse inserts
- `dump --target` JSONL output

Acceptance:
- one direct chat can be fully synced and dumped without `contact.db`

### M3: Group Support and Decoder Registry
- group target support
- sender resolution in group chats
- decoder plugins for text, image, voice, video, emoji, share cards, file shares, quote replies, system, voip

Acceptance:
- one group can be fully dumped with `sender_wxid`

### M4: Asset Resolution and Coverage Reports
- local asset path resolution for images and cached artifacts
- sync run metrics and failure samples
- coverage summary in `doctor` and `sync` output

Acceptance:
- image messages include attachment metadata and candidate local paths

### M5: Contact Enrichment and Runtime Automation
- optional `contact.db` enrichment
- aliases and target naming
- launchd/manual automation hooks

Acceptance:
- same export works with richer names when contact coverage is available

## Work Breakdown

1. Scaffold repo and docs
2. Implement source adapters
3. Implement warehouse schema and upserts
4. Implement doctor and targets
5. Implement sync loop and dump loop
6. Implement decoder registry
7. Implement asset resolver
8. Add tests and golden fixtures
9. Add packaging and operational docs

## Risks

- Missing `contact.db` key: mitigate via `Name2Id` fallback and aliases
- New message types: mitigate via raw archive and unknown decoder bucket
- Asset path mismatch: mitigate via heuristic resolver plus coverage report
- Upstream DB layout drift: mitigate via `doctor` probes and adapter isolation
