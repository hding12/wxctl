# wxctl

`wxctl` is a local CLI for extracting, normalizing, and exporting encrypted desktop chat data for downstream agent automation.

It is designed as a control loop rather than a one-shot script:

- `doctor`: inspect upstream state and report readiness
- `capture-key`: attach to the desktop client process and collect SQLCipher keys
- `decrypt`: decrypt local application databases into plaintext SQLite
- `targets`: enumerate direct chats and group chats that can be synced
- `sync`: incrementally ingest raw messages from decrypted local databases into a local warehouse
- `dump`: emit full structured interaction records for one user or one group in agent-friendly JSONL

## Architecture

wxctl follows a two-loop cybernetic architecture (see `docs/adr/0001-local-cybernetic-architecture.md`):

1. **sync loop**: touches upstream state (decrypted local SQLite DBs), normalizes and decodes messages into a local warehouse
2. **dump loop**: serves stable JSONL from the warehouse, never reads upstream data directly

Raw payloads are archived to disk alongside decoded structures, preserving replayability after decoder upgrades.

```
decrypted/  ──sync──>  warehouse/  ──dump──>  JSONL stdout
                          raw/          (replay archive)
```

## Runtime Model

`wxctl` is self-contained at the code level. It still depends on local macOS system components:

- the target desktop messaging client running locally
- LLDB Python runtime from Xcode Command Line Tools
- `sqlcipher` for database decryption
- `zstd` for compressed message payloads

## Design Goals

- Non-interactive CLI for agent use
- Full-message export for one user or one group
- Structured storage in local SQLite plus raw payload archive
- Graceful degradation when `contact.db` is unavailable
- Incremental sync with observability and replayability

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
brew install sqlcipher zstd
```

### Capture SQLCipher keys

This is the only step that still depends on the host security state. On current macOS/client combinations, first capture generally requires:

- the target client running and logged in
- system `Terminal.app`
- SIP temporarily disabled

Run:

```bash
PYTHONPATH=src python3 -m wxctl.cli capture-key
PYTHONPATH=src python3 -m wxctl.cli capture-key --keys /path/to/keys.json
```

Keys are saved to the configured runtime state directory by default.

### Decrypt local databases

```bash
PYTHONPATH=src python3 -m wxctl.cli decrypt
PYTHONPATH=src python3 -m wxctl.cli decrypt --keys /path/to/keys.json
```

Decrypted databases are written to `~/Library/Application Support/wxctl/decrypted` by default.

### Run doctor (check upstream state)

```bash
PYTHONPATH=src python3 -m wxctl.cli doctor --json
```

Sample output:
```json
{
  "capture_script_exists": true,
  "key_file_exists": true,
  "message_db_count": 3,
  "self_wxid": "wxid_xxx",
  "zstd": "/usr/local/bin/zstd",
  "sqlcipher": "/usr/local/bin/sqlcipher"
}
```

### List available targets

```bash
PYTHONPATH=src python3 -m wxctl.cli targets
PYTHONPATH=src python3 -m wxctl.cli targets --format jsonl
```

### Sync messages for one target

```bash
PYTHONPATH=src python3 -m wxctl.cli sync --target wxid_xxx
```

Sync output includes accurate insert/update counts, failure samples, and coverage:

```json
{
  "sync_run_id": 1,
  "targets": ["wxid_xxx"],
  "inserted_messages": 142,
  "updated_messages": 0,
  "skipped_messages": 0,
  "decode_failures": 0,
  "failure_samples": [],
  "total_processed": 142,
  "by_kind": {"text": 89, "image": 23, "system": 15, "share_card": 10, ...},
  "coverage": {
    "wxid_xxx": {
      "source_total": 142,
      "warehouse_total": 142,
      "coverage_pct": 100.0
    }
  }
}
```

### Sync is idempotent

Running the same `sync` again updates existing messages (no duplicates):

```json
{
  "inserted_messages": 0,
  "updated_messages": 142,
  ...
}
```

### Dump messages as JSONL

```bash
PYTHONPATH=src python3 -m wxctl.cli dump --target wxid_xxx --stdout --limit 10
PYTHONPATH=src python3 -m wxctl.cli dump --group wxid_group@chatroom --stdout
```

Sample JSONL record:

```json
{
  "target_id": "wxid_xxx",
  "kind": "text",
  "text": "hello",
  "sender_wxid": "wxid_sender",
  "is_self": false,
  "ts": 1700000000,
  "decoded": {"text": "hello"},
  "assets": [],
  "raw": {"payload_path": ".../raw/.../42.json", "packed_info_hex": null}
}
```

## Decoder Architecture

Decoders live under `src/wxctl/decoders/` and are organized by message type:

```
decoders/
├── base.py       # Shared: DecodeContext, DecodeResult, XML helpers, zstd decompress
├── registry.py   # Dispatcher: raw_type -> decoder module
├── text.py       # raw_type 1
├── image.py      # raw_type 3
├── voice.py      # raw_type 34
├── video.py      # raw_type 43
├── emoji.py      # raw_type 47
├── voip.py       # raw_type 50
├── system.py     # raw_type 10000 (revoke, group notifications)
└── appmsg.py     # AppMsg XML (share_card, file_share, quote_reply, mini_program, location, etc.)
```

The `appmsg.py` decoder handles multiple subtypes via the `<appmsg><type>N</type>` field:

| appmsg type | kind | Description |
|---|---|---|
| 1 | share_card | URL/link card |
| 5 | share_card | Share card (articles) |
| 6 | file_share | File share |
| 33 | mini_program | Mini program card |
| 36 | location | Location share |
| 57 | quote_reply | Quoted reply |
| 63 | transfer | Money transfer |
| 10000000 | payment | Payment notification |

### Adding a new decoder

1. Create a new file in `decoders/` with a `decode()` function matching the signature
2. Register the raw_type in `decoders/registry.py`
3. Add golden XML fixtures in `tests/golden/`
4. Add test cases in `tests/unit/test_decoders.py`
5. Run tests

## Development

### Running tests

```bash
PYTHONPATH=src python3 -m pytest tests/ -v
```

Run specific test categories:

```bash
# Unit tests only (fast)
PYTHONPATH=src python3 -m pytest tests/unit/ -v

# Integration tests (warehouse lifecycle)
PYTHONPATH=src python3 -m pytest tests/integration/ -v
```

### Running smoke tests

```bash
python3 /tmp/test_decoders.py
```

### Test structure

```
tests/
├── unit/
│   ├── conftest.py          # Shared fixtures (decode_ctx, load_golden)
│   ├── test_decoders.py     # 37+ unit tests for all decoder types
│   └── test_registry.py     # Original decoder test
├── integration/
│   └── test_sync_loop.py    # 8 warehouse lifecycle tests
└── golden/
    ├── README.md
    ├── image_msg.xml
    ├── voice_msg.xml
    ├── video_msg.xml
    ├── emoji_msg.xml
    ├── voip_msg.xml
    ├── share_card_msg.xml
    ├── file_share_msg.xml
    ├── quote_reply_msg.xml
    ├── mini_program_msg.xml
    ├── location_msg.xml
    └── system_revoke_msg.xml
```

### Style

- Type annotations everywhere (Python 3.10+)
- `from __future__ import annotations` at the top of every module
- No external heavy dependencies beyond PyYAML
- Test coverage expected for new decoders

## Current Message Type Support

| Kind | raw_type | Decoder File | Status |
|---|---|---|---|
| text | 1 | text.py | Stable |
| image | 3 | image.py | Stable (metadata + candidate paths) |
| voice | 34 | voice.py | Stable |
| video | 43 | video.py | Stable |
| emoji | 47 | emoji.py | Stable |
| voip | 50 | voip.py | Stable |
| system | 10000 | system.py | Stable |
| share_card | appmsg type 1/5 | appmsg.py | Stable |
| file_share | appmsg type 6 | appmsg.py | Stable |
| quote_reply | appmsg type 57 | appmsg.py | Stable |
| mini_program | appmsg type 33 | appmsg.py | Stable |
| location | appmsg type 36 | appmsg.py | Stable |
| transfer | appmsg type 63 | appmsg.py | Stable |
| payment | appmsg type 10000000 | appmsg.py | Stable |
| appmsg | other types | appmsg.py | Catch-all |
| unknown | unregistered | registry.py | Fallback |

## Known Limitations

### Image/Media Decoding
- Image messages resolve metadata plus likely local attachment paths from `packed_info_data`.
- wxctl does **not** yet decode proprietary `.dat` image payloads into viewable PNG/JPG.
- Voice `.silk` and encrypted video files are not decoded.
- Asset resolution is heuristic (hex candidate matching in attach directories).

### contact.db Availability
- **Without contact.db**: sync and dump still work. All sender fields use raw wxid values. Target display names fall back to the target_id.
- **With contact.db**: sender display_name, alias, avatar, and target group info are enriched automatically.
- The `resolvers/target_resolver.py` and `resolvers/sender_resolver.py` handle graceful degradation — they check for contact.db at startup and work with or without it.

### Sync Scope
- `sync` currently processes all messages from the source database for a target. There is no incremental-ts optimization yet — each sync re-processes all messages and relies on upsert idempotency.
- `sync --full` flag is reserved but not yet optimized for truncate-and-reimport.

### No Active Watch
- wxctl does not run as a daemon. It is designed for cron/launchd-driven periodic syncs.
- Event-driven sync (watch decrypted DB file changes) is not implemented.

### Raw Archive Growth
- Raw payloads accumulate indefinitely under `~/Library/Application Support/wxctl/raw/`.
- No automatic archival/compaction is implemented yet.

## Data Layout

Runtime state lives outside the repo under:

```text
~/Library/Application Support/wxctl/
├── raw/           # Per-message raw payload archives (JSON, base64-encoded)
├── warehouse/     # wxctl.sqlite3 — structured message + asset tables
├── exports/       # JSONL dump output directory
├── logs/          # Runtime logs
└── state/         # Runtime state files
```

## CLI Reference

```
wxctl doctor [--json]
wxctl targets [--kind direct|group] [--format table|json|jsonl]
wxctl sync --target <id> [--target <id> ...]
wxctl sync --group <id> [--group <id> ...]
wxctl dump --target <id> [--stdout] [--limit N] [--refresh]
wxctl dump --group <id> [--stdout] [--limit N] [--refresh]
```
