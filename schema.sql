-- synapse-core database schema
-- Single SQLite database replaces markdown files
-- Designed to be garbage-injection-proof: no freeform frontmatter, no untyped fields

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- CORE STATE (quick ref panel + current context)
-- ============================================================

CREATE TABLE state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Seed with defaults
INSERT INTO state VALUES ('mood', '', datetime('now','localtime'));
INSERT INTO state VALUES ('mood_detail', '', datetime('now','localtime'));
INSERT INTO state VALUES ('location', '', datetime('now','localtime'));
INSERT INTO state VALUES ('last_heartbeat', '', datetime('now','localtime'));
INSERT INTO state VALUES ('heartbeat_count', '0', datetime('now','localtime'));
INSERT INTO state VALUES ('today_plan', '', datetime('now','localtime'));
INSERT INTO state VALUES ('active_projects', '', datetime('now','localtime'));
INSERT INTO state VALUES ('pending_tasks', '', datetime('now','localtime'));
INSERT INTO state VALUES ('system_version', '1.0.0', datetime('now','localtime'));

-- ============================================================
-- ENTITY TRIGGERS (trigger word -> context files mapping)
-- ============================================================

CREATE TABLE entity_triggers (
    trigger_word TEXT PRIMARY KEY,
    load_files   TEXT NOT NULL,   -- comma-separated table names
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- USER PROFILE (singleton row)
-- ============================================================

CREATE TABLE user_profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    age        INTEGER NOT NULL DEFAULT 18,
    name       TEXT,
    gender     TEXT,
    city       TEXT,
    school     TEXT,
    major      TEXT,
    bio        TEXT,
    devices    TEXT,  -- JSON array
    dev_env    TEXT,  -- JSON object: python, platformio, frameworks
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO user_profile (id) VALUES (1);

-- ============================================================
-- PERSONALITY TRAITS (singleton row)
-- ============================================================

CREATE TABLE personality_traits (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    mood_spectrum TEXT,   -- JSON: emotional spectrum
    triggers    TEXT,     -- JSON: what triggers anger/annoyance
    joy_points  TEXT,     -- JSON: what brings joy
    aesthetics  TEXT,     -- JSON: aesthetic preferences
    social_style TEXT,    -- text description
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO personality_traits (id) VALUES (1);

-- ============================================================
-- FEEDBACK STYLE (singleton row)
-- ============================================================

CREATE TABLE feedback_style (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    dislikes    TEXT,  -- JSON array
    likes       TEXT,  -- JSON array
    hard_rules  TEXT,  -- JSON array of string rules
    dev_notes   TEXT,  -- freeform dev experience notes
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO feedback_style (id) VALUES (1);

-- ============================================================
-- COLLEGE & LEARNING (singleton row)
-- ============================================================

CREATE TABLE college_learning (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    school_info     TEXT,  -- JSON: name, management style, problems
    evening_study   TEXT,  -- JSON: forced self-study, inspection routine
    ic_major        TEXT,  -- JSON: curriculum, course frequency
    embedded_roadmap TEXT, -- JSON: learning roadmap
    contests        TEXT,  -- JSON: contest tracking details
    labview_progress TEXT, -- JSON: completed modules, next steps
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO college_learning (id) VALUES (1);

-- ============================================================
-- CONTEST TRACKING
-- ============================================================

CREATE TABLE contests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    role        TEXT,
    deadline    TEXT,
    status      TEXT,
    teammates   TEXT,  -- JSON
    details     TEXT,  -- JSON
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- PEOPLE
-- ============================================================

CREATE TABLE people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    relation    TEXT NOT NULL,   -- family/friend/classmate/roommate
    role        TEXT,            -- role/title
    hometown    TEXT,
    notes       TEXT,            -- freeform notes about this person
    tags        TEXT,            -- JSON array
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- GAMING
-- ============================================================

CREATE TABLE gaming (
    game_name   TEXT PRIMARY KEY,
    platform    TEXT,       -- Steam/Epic/etc
    status      TEXT,       -- playing/want to play/dropped
    progress    TEXT,       -- freeform
    highlights  TEXT,       -- JSON array of dated highlights
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- INTERESTS
-- ============================================================

CREATE TABLE interests (
    category    TEXT NOT NULL,   -- e.g. music/movies/hobbies/other
    key         TEXT NOT NULL,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (category, key)
);

-- ============================================================
-- DAILY LIFE LOG (P2 with 60-day auto-clean)
-- ============================================================

CREATE TABLE daily_life (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date  TEXT NOT NULL,   -- YYYY-MM-DD
    category    TEXT NOT NULL DEFAULT 'event',  -- event/rant/note
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_daily_date ON daily_life(event_date);

-- ============================================================
-- SESSION LOG (P2 keep last 15)
-- ============================================================

CREATE TABLE session_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,   -- YYYY-MM-DD
    title       TEXT,
    summary     TEXT,
    mood_trace  TEXT,             -- emotional arc during session
    decisions   TEXT,             -- JSON array of key decisions
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_session_date ON session_log(session_date);

-- ============================================================
-- HEARTBEAT LOG
-- ============================================================

CREATE TABLE heartbeat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    heartbeat_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- SYSTEM AUDIT LOG (for debugging)
-- ============================================================

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    table_name  TEXT,
    detail      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- VIEWS for quick startup
-- ============================================================

CREATE VIEW v_quick_ref AS
SELECT key, value FROM state
WHERE key IN ('mood','last_heartbeat','heartbeat_count','today_plan',
              'active_projects','pending_tasks','system_version');

CREATE VIEW v_active_contests AS
SELECT * FROM contests WHERE status != 'done' ORDER BY deadline;

-- ============================================================
-- FTS5 FULL-TEXT SEARCH
-- ============================================================

-- Virtual tables backed by daily_life and session_log content
CREATE VIRTUAL TABLE IF NOT EXISTS daily_life_fts USING fts5(
    event_date, category, content, content=daily_life
);

CREATE VIRTUAL TABLE IF NOT EXISTS session_log_fts USING fts5(
    session_date, title, summary, content=session_log
);

-- Populate with existing data
INSERT INTO daily_life_fts(daily_life_fts) VALUES('rebuild');
INSERT INTO session_log_fts(session_log_fts) VALUES('rebuild');

-- Triggers: keep FTS index in sync with source tables
CREATE TRIGGER IF NOT EXISTS daily_life_ai AFTER INSERT ON daily_life BEGIN
    INSERT INTO daily_life_fts(rowid, event_date, category, content)
    VALUES (new.rowid, new.event_date, new.category, new.content);
END;

CREATE TRIGGER IF NOT EXISTS daily_life_ad AFTER DELETE ON daily_life BEGIN
    INSERT INTO daily_life_fts(daily_life_fts, rowid, event_date, category, content)
    VALUES('delete', old.rowid, old.event_date, old.category, old.content);
END;

CREATE TRIGGER IF NOT EXISTS daily_life_au AFTER UPDATE ON daily_life BEGIN
    INSERT INTO daily_life_fts(daily_life_fts, rowid, event_date, category, content)
    VALUES('delete', old.rowid, old.event_date, old.category, old.content);
    INSERT INTO daily_life_fts(rowid, event_date, category, content)
    VALUES (new.rowid, new.event_date, new.category, new.content);
END;

CREATE TRIGGER IF NOT EXISTS session_log_ai AFTER INSERT ON session_log BEGIN
    INSERT INTO session_log_fts(rowid, session_date, title, summary)
    VALUES (new.rowid, new.session_date, new.title, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS session_log_ad AFTER DELETE ON session_log BEGIN
    INSERT INTO session_log_fts(session_log_fts, rowid, session_date, title, summary)
    VALUES('delete', old.rowid, old.session_date, old.title, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS session_log_au AFTER UPDATE ON session_log BEGIN
    INSERT INTO session_log_fts(session_log_fts, rowid, session_date, title, summary)
    VALUES('delete', old.rowid, old.session_date, old.title, old.summary);
    INSERT INTO session_log_fts(rowid, session_date, title, summary)
    VALUES (new.rowid, new.session_date, new.title, new.summary);
END;

-- ============================================================
-- SCHEMA VALIDATION
-- ============================================================

-- No trigger needed for schema protection -- the schema itself IS the protection.
-- No node_type column exists, no originSessionId column exists.
-- Any injection attempt targeting those fields fails at SQL level.
