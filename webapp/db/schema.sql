-- D1 schema for the IELTS Listening practice web app.
--
-- Deliberately not fully normalized: test.json is already a validated document,
-- and splitting it into six tables buys nothing until there's per-question
-- analytics. See ../../CLAUDE.md and the publisher plan for context.

CREATE TABLE IF NOT EXISTS tests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,          -- 'test_016'
  title TEXT NOT NULL,
  target_band TEXT,
  context TEXT,
  part_topics TEXT NOT NULL,          -- JSON {"1":"...",...} for library cards
  duration_sec REAL NOT NULL,
  audio_key TEXT NOT NULL,            -- R2 key
  status TEXT NOT NULL DEFAULT 'published',
  generated_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_content (
  test_id INTEGER PRIMARY KEY REFERENCES tests(id),
  student_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_answers (
  test_id INTEGER PRIMARY KEY REFERENCES tests(id),
  answers_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_timeline (
  test_id INTEGER PRIMARY KEY REFERENCES tests(id),
  timeline_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_transcript (
  test_id INTEGER PRIMARY KEY REFERENCES tests(id),
  transcript_json TEXT NOT NULL
);
