CREATE TABLE IF NOT EXISTS conversations (
  target_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  conversation_hash TEXT NOT NULL,
  first_ts INTEGER,
  last_ts INTEGER,
  total_count INTEGER NOT NULL DEFAULT 0,
  text_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  scope TEXT NOT NULL,
  inserted_messages INTEGER NOT NULL DEFAULT 0,
  updated_messages INTEGER NOT NULL DEFAULT 0,
  decode_failures INTEGER NOT NULL DEFAULT 0,
  notes_json TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  source_db TEXT NOT NULL,
  target_id TEXT NOT NULL,
  conversation_hash TEXT NOT NULL,
  local_id INTEGER NOT NULL,
  server_id INTEGER,
  ts INTEGER NOT NULL,
  datetime TEXT NOT NULL,
  sender_wxid TEXT,
  is_self INTEGER NOT NULL DEFAULT 0,
  raw_type INTEGER NOT NULL,
  kind TEXT NOT NULL,
  text TEXT,
  decoded_json TEXT NOT NULL,
  sender_info_json TEXT,
  packed_info_hex TEXT,
  raw_payload_path TEXT,
  sync_run_id INTEGER,
  PRIMARY KEY (source_db, target_id, local_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_target_ts ON messages(target_id, ts, local_id);

CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_db TEXT NOT NULL,
  target_id TEXT NOT NULL,
  local_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  local_path TEXT,
  meta_json TEXT NOT NULL,
  UNIQUE (source_db, target_id, local_id, kind, local_path)
);
