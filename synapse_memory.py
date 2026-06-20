"""
synapse-core — Personal memory engine with BM25 search, MCP server support.
A local-first, SQLite-backed memory system for AI agent contexts.

Features:
  1. SuperMemoryRanker — pure native BM25 semantic search, zero deps,
     N-Gram tokenizer + IDF scoring
  2. bm25_search() — full-db semantic search, natural language query
  3. smart_auto_context() — dual engine (entity triggers + BM25 semantic
     fallback), auto-associate context
  4. Inline SQL_SCHEMA — no external schema.sql dependency (external
     file still supported for customization)
  5. export_csv() / import_csv() — batch CSV import/export, auto-dedup
  6. session_end() — atomic session wrap-up with merged summaries
  7. heartbeat() — timestamp + cleanup + VACUUM + versioned backup
  8. people_graph() — relationship inference: shared hometown, events,
     notes mentions
  9. Backup — sqlite3.backup API hot backup, versioned with retention
  10. FTS5 full-text search — inverted index on daily_life and session_log
  11. Rate limiter — SQLite-persistent, multi-process safe
  12. Snapshot — Git-like versioning, interactive restore
  13. Mood trend analysis — emotional keyword resonance word cloud
  14. Memory consolidation — importance scoring (1-10), weekly/monthly summarization,
      low-score auto-expiry, high-score permanent retention, consolidated source GC
"""

import sqlite3
import json
import os
import sys
import shutil
import re
import math
import glob as _glob_mod
import argparse
import csv
from contextlib import contextmanager
from collections import Counter
from datetime import datetime

# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Prefer existing DB in script directory, fallback to ~/.synapse-core/
_LEGACY_DB = os.path.join(BASE_DIR, "synapse_memory.db")
_USER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".synapse-core")
if os.path.exists(_LEGACY_DB):
    DATA_DIR = BASE_DIR
else:
    DATA_DIR = _USER_DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "synapse_memory.db")
BACKUP_DIR = os.path.join(DATA_DIR, "memory_backup")
BACKUP_KEEP = 10
DAILY_LIFE_RETENTION_DAYS = 60
SESSION_LOG_KEEP_LIMIT = 15

# ── helpers ──────────────────────────────────────────────────────

@contextmanager
def get_db():
    """Context manager that ensures connection is properly closed on exceptions.
    Auto-initializes database on first use (lazy init)."""
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()

def _get_one(query, *params):
    with get_db() as conn:
        r = conn.execute(query, params).fetchone() if params else conn.execute(query).fetchone()
    return r

def _get_all(query, *params):
    with get_db() as conn:
        r = conn.execute(query, params).fetchall() if params else conn.execute(query).fetchall()
    return r

def _exec(query, *params):
    """Unified parameterized query. Supports both _exec(sql, a, b) and _exec(sql, (a, b))."""
    bindings = params[0] if len(params) == 1 and isinstance(params[0], (tuple, list)) else params
    with get_db() as conn:
        conn.execute(query, bindings)
        conn.commit()

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def _today():
    return datetime.now().strftime("%Y-%m-%d")

def _norm(val):
    if val is None: return None
    if isinstance(val, str) and val.strip().lower() in ('none', ''): return None
    return val

def _ok(msg="", silent=False):
    if not silent:
        tag = f" {msg}" if msg else ""
        print(f"[OK]{tag}")

def _err(msg, silent=False):
    if not silent:
        print(f"[ERR] {msg}")
    return False

def _is_first_run():
    """Check if first run: heartbeat_count is 0 and last_heartbeat is empty."""
    hc = state_get("heartbeat_count") or "0"
    lh = state_get("last_heartbeat") or ""
    return hc == "0" and lh == ""

# ── backup (versioned + retention) ────────────────────────────────

def _cleanup_old_backups(keep=BACKUP_KEEP, silent=False):
    """Keep last N backups, delete older files."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for prefix in ("synapse-core_",):
        pattern = os.path.join(BACKUP_DIR, f"{prefix}*")
        files = sorted(_glob_mod.glob(pattern), key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
                if not silent:
                    print(f"[CLEAN] Removed old backup: {os.path.basename(old)}")
            except OSError:
                pass

def backup_db(silent=False):
    """Hot backup using sqlite3 built-in backup API, timestamped filename."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_path = os.path.join(BACKUP_DIR, f"synapse-core_{ts}.db")
    src_conn = sqlite3.connect(DB_PATH)
    dst_conn = sqlite3.connect(dst_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    if not silent:
        _ok(f"Database hot backup done synapse-core_{ts}.db")

def backup_all(silent=False):
    """Backup synapse_memory.db (hot backup, timestamped), auto-clean old."""
    ok = True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    try:
        backup_db(silent=silent)
    except Exception as e:
        ok = _err(f"Backup db failed: {e}", silent=silent)
    _cleanup_old_backups(silent=silent)
    return ok

# ── verify ────────────────────────────────────────────────────────

def verify_schema(silent=False):
    """Check for garbage columns (table name sanitized, SQL injection proof)."""
    found = False
    with get_db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        garbage_cols = ['node_type', 'originSessionId']
        for t in tables:
            safe_name = "".join([c for c in t['name'] if c.isalnum() or c == '_'])
            if not safe_name:
                continue
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({safe_name})").fetchall()]
            for gc in garbage_cols:
                if gc in cols:
                    if not silent:
                        print(f"!! Garbage column: {t['name']}.{gc}")
                    found = True
    if not found and not silent:
        _ok("Database clean")
    return not found

def verify_integrity(silent=False):
    """Database integrity check."""
    with get_db() as conn:
        r = conn.execute("PRAGMA integrity_check").fetchone()
    ok = r[0] == "ok"
    if not silent:
        if ok:
            _ok("Integrity OK")
        else:
            _err(f"Integrity failed: {r[0]}")
    return ok
    return ok

def verify_write(filepath):
    """Verify file write succeeded: exists + non-empty."""
    if not os.path.exists(filepath):
        _err(f"File not found: {filepath}")
        return False
    if os.path.getsize(filepath) == 0:
        _err(f"File empty: {filepath}")
        return False
    return True

# ── state ─────────────────────────────────────────────────────────

def state_get(key):
    r = _get_one("SELECT value FROM state WHERE key=?", key)
    return r["value"] if r else None

def state_set(key, value):
    """Write state value, then read-back verify within same connection."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) VALUES(?,?,?)",
            (key, value, _now()))
        conn.commit()
        v_row = conn.execute(
            "SELECT value FROM state WHERE key=?", (key,)).fetchone()
    v = v_row["value"] if v_row else None
    if v != value:
        _err(f"state_set verify failed: {key} expected={value[:50]} actual={v}")
        return False
    return True

def state_get_all():
    rows = _get_all("SELECT key,value FROM state")
    return {r["key"]: r["value"] for r in rows}

# ── mood ──────────────────────────────────────────────────────────

def mood(new_mood=None):
    if new_mood:
        ok = state_set("mood", new_mood)
        if ok: _ok(f"Mood: {new_mood}")
        return ok
    return state_get("mood")

# ── quick_ref ─────────────────────────────────────────────────────

def quick_ref():
    rows = _get_all("""
        SELECT key, value FROM state
        WHERE key IN ('mood','last_heartbeat','heartbeat_count','today_plan',
                      'active_projects','pending_tasks','system_version','custom_status')
    """)
    d = {r["key"]: r["value"] for r in rows}
    ver = d.get('system_version', '?.?')
    hb = d.get('last_heartbeat', 'N/A')
    cnt = d.get('heartbeat_count', '0')
    mood_val = d.get('mood', '?')
    custom = d.get('custom_status', '?')
    plan = d.get('today_plan', '?')
    proj = d.get('active_projects', '?')
    tasks = d.get('pending_tasks', '?')
    print(f"""
  Quick Ref [v{ver}]
  [TIME] Last heartbeat: {hb}  [REFRESH] Count: {cnt}/10
  Mood: {mood_val}
  Status: {custom}
  Today: {plan}
  Projects: {proj}
  Tasks: {tasks}
""")

# ── export / import / search (see below) ─────────────────────────────

# ── smart_auto_context (see below) ─────────────────────────────────

# ── memory consolidation & decay ────────────────────────────────────

def _importance_label(score):
    """Human-readable importance tier."""
    if score >= 9: return "critical"
    if score >= 7: return "high"
    if score >= 5: return "medium"
    if score >= 3: return "low"
    return "trivial"

def consolidate_preview():
    """Return all unconsolidated daily_life and session_log records for AI review.
    Grouped by source table, ordered by date, with importance shown."""
    daily_rows = _get_all(
        "SELECT id, event_date, category, content, importance FROM daily_life "
        "WHERE consolidated_to IS NULL ORDER BY event_date DESC, id DESC")
    session_rows = _get_all(
        "SELECT id, session_date, title, summary, importance FROM session_log "
        "WHERE consolidated_to IS NULL ORDER BY session_date DESC, id DESC")

    if not daily_rows and not session_rows:
        print("(all records consolidated, nothing to preview)")
        return

    print("\n=== Consolidation Preview ===")
    print(f"Unconsolidated: {len(daily_rows)} daily + {len(session_rows)} session records\n")

    if daily_rows:
        print("-- daily_life --")
        for r in daily_rows:
            imp = r["importance"]
            label = _importance_label(imp)
            print(f"  [#{r['id']}] [{r['event_date']}] [{r['category']}] "
                  f"(imp={imp}/{label}) {r['content'][:120]}")
        print()

    if session_rows:
        print("-- session_log --")
        for r in session_rows:
            imp = r["importance"]
            label = _importance_label(imp)
            body = (r["summary"] or "")[:120]
            print(f"  [#{r['id']}] [{r['session_date']}] {r['title'] or '?'} "
                  f"(imp={imp}/{label}) {body}")
        print()

    # Suggest consolidation windows
    all_dates = set()
    for r in daily_rows:
        all_dates.add(r["event_date"])
    for r in session_rows:
        all_dates.add(r["session_date"])
    if all_dates:
        sorted_dates = sorted(all_dates)
        print(f"Date range: {sorted_dates[0]} ~ {sorted_dates[-1]} "
              f"({len(all_dates)} distinct dates)")
        print(f"Suggested summary_type: "
              f"{'monthly' if len(all_dates) > 7 else 'weekly'}")

def consolidate_commit(summary_type, period_start, period_end,
                       title, content, daily_ids=None, session_ids=None,
                       importance_overrides=None):
    """Commit a consolidation summary, linking source records.

    Args:
        summary_type: 'weekly', 'monthly', or 'custom'
        period_start, period_end: date range strings YYYY-MM-DD
        title: summary title
        content: summary content (AI-generated)
        daily_ids: list of daily_life IDs to link (or None = auto in period)
        session_ids: list of session_log IDs to link (or None = auto in period)
        importance_overrides: dict {id: new_score} to update source importance
    """
    if importance_overrides is None:
        importance_overrides = {}

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Auto-select unconsolidated IDs in period if not provided
        if daily_ids is None:
            d_rows = conn.execute(
                "SELECT id FROM daily_life "
                "WHERE consolidated_to IS NULL AND event_date BETWEEN ? AND ?",
                (period_start, period_end)
            ).fetchall()
            daily_ids = [r["id"] for r in d_rows]

        if session_ids is None:
            s_rows = conn.execute(
                "SELECT id FROM session_log "
                "WHERE consolidated_to IS NULL AND session_date BETWEEN ? AND ?",
                (period_start, period_end)
            ).fetchall()
            session_ids = [r["id"] for r in s_rows]

        if not daily_ids and not session_ids:
            conn.rollback()
            conn.close()
            print("[SKIP] No records found in period to consolidate")
            return True

        # Calculate source metadata
        source_count = len(daily_ids) + len(session_ids)

        total_imp = 0
        imp_count = 0
        for did in daily_ids:
            imp = importance_overrides.get(f"d_{did}") or importance_overrides.get(did)
            if imp is not None:
                conn.execute("UPDATE daily_life SET importance=? WHERE id=?",
                             (imp, did))
                total_imp += imp
            else:
                row = conn.execute(
                    "SELECT importance FROM daily_life WHERE id=?", (did,)
                ).fetchone()
                total_imp += row["importance"] if row else 5
            imp_count += 1

        for sid in session_ids:
            imp = importance_overrides.get(f"s_{sid}") or importance_overrides.get(sid)
            if imp is not None:
                conn.execute("UPDATE session_log SET importance=? WHERE id=?",
                             (imp, sid))
                total_imp += imp
            else:
                row = conn.execute(
                    "SELECT importance FROM session_log WHERE id=?", (sid,)
                ).fetchone()
                total_imp += row["importance"] if row else 5
            imp_count += 1

        importance_avg = round(total_imp / imp_count, 1) if imp_count > 0 else 5.0

        # Insert summary
        daily_json = json.dumps(daily_ids, ensure_ascii=False)
        session_json = json.dumps(session_ids, ensure_ascii=False)

        conn.execute(
            "INSERT INTO summaries(summary_type,period_start,period_end,"
            "title,content,source_count,importance_avg,daily_ids,session_ids) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (summary_type, period_start, period_end, title, content,
             source_count, importance_avg, daily_json, session_json))
        summary_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Mark sources as consolidated
        for did in daily_ids:
            conn.execute(
                "UPDATE daily_life SET consolidated_to=? WHERE id=?",
                (summary_id, did))
        for sid in session_ids:
            conn.execute(
                "UPDATE session_log SET consolidated_to=? WHERE id=?",
                (summary_id, sid))

        # Garbage-collect low-score consolidated records (importance <= 2)
        # that are older than 7 days — they were archived, now safe to delete
        gc_daily = conn.execute(
            "DELETE FROM daily_life "
            "WHERE consolidated_to IS NOT NULL AND importance <= 2 "
            "AND event_date < date('now', '-7 days')"
        ).rowcount
        gc_session = conn.execute(
            "DELETE FROM session_log "
            "WHERE consolidated_to IS NOT NULL AND importance <= 2 "
            "AND session_date < date('now', '-7 days')"
        ).rowcount

        # Update state
        n = _now()
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) "
            "VALUES('last_consolidation',?,?)", (n, n))
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) "
            "VALUES('system_version','1.1.0',?)", (n,))

        conn.commit()

        _ok(f"Consolidation committed: [{summary_type}] {title} "
            f"(summary_id={summary_id}, sources={source_count}, "
            f"imp_avg={importance_avg})")
        if gc_daily or gc_session:
            print(f"[GC] Cleaned {gc_daily} daily + {gc_session} session "
                  f"low-score consolidated records")
        return True

    except Exception as e:
        conn.rollback()
        _err(f"Consolidation commit failed, all rolled back: {e}")
        return False
    finally:
        conn.close()

def summaries_list(n=10):
    """List recent summaries."""
    rows = _get_all(
        "SELECT id, summary_type, period_start, period_end, title, "
        "source_count, importance_avg, created_at "
        "FROM summaries ORDER BY created_at DESC LIMIT ?", n)
    if not rows:
        print("(no summaries yet)")
        return
    for r in rows:
        print(f"[{r['summary_type']}] {r['period_start']} ~ {r['period_end']} "
              f"#{r['id']} {r['title']} "
              f"(sources={r['source_count']}, imp_avg={r['importance_avg']})")

def summarize_get(summary_id):
    """Get full content of a specific summary by ID."""
    r = _get_one("SELECT * FROM summaries WHERE id=?", summary_id)
    if not r:
        print(f"Summary #{summary_id} not found")
        return
    print(f"Title: {r['title']}")
    print(f"Type: {r['summary_type']} | Period: {r['period_start']} ~ {r['period_end']}")
    print(f"Sources: {r['source_count']} | Avg importance: {r['importance_avg']}")
    print(f"Created: {r['created_at']}")
    print()
    print(r['content'])
    print()
    if r['daily_ids']:
        try:
            dids = json.loads(r['daily_ids'])
            print(f"Daily IDs: {len(dids)} -> {dids}")
        except json.JSONDecodeError:
            pass
    if r['session_ids']:
        try:
            sids = json.loads(r['session_ids'])
            print(f"Session IDs: {len(sids)} -> {sids}")
        except json.JSONDecodeError:
            pass

def update_importance(table, row_id, new_score):
    """Update importance score for a single daily_life or session_log record.
    table: 'daily_life' or 'session_log'"""
    if table not in ("daily_life", "session_log"):
        _err(f"Invalid table: {table}")
        return False
    if not isinstance(new_score, int) or new_score < 1 or new_score > 10:
        _err(f"Importance must be 1-10, got {new_score}")
        return False
    _exec(f"UPDATE {table} SET importance=? WHERE id=?", new_score, row_id)
    _ok(f"{table}#{row_id} importance -> {new_score}")
    return True

# ── heartbeat (upgraded with consolidation-aware cleanup) ───────────

def heartbeat(silent=False):
    """Heartbeat: timestamp + cleanup + VACUUM + versioned backup.
    Cleanup respects importance scoring: high-score (>=7) permanent,
    medium (4-6) kept until consolidated then GCed, low (<=3) deleted on expiry.
    silent=True suppresses all stdout output (for scheduled/background use)."""
    n = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) VALUES('last_heartbeat',?,?)",
            (n, n))
        conn.execute("INSERT INTO heartbeat_log(heartbeat_at) VALUES(?)", (n,))
        # Tiered cleanup respecting importance tiers
        # Tier 1: low-score (<=3) daily_life — delete on expiry
        conn.execute(
            "DELETE FROM daily_life WHERE importance <= 3 "
            "AND event_date < date('now', ?)",
            (f'-{DAILY_LIFE_RETENTION_DAYS} days',))
        # Tier 2: medium-score (4-6) — delete only if consolidated, after retention
        conn.execute(
            "DELETE FROM daily_life WHERE importance BETWEEN 4 AND 6 "
            "AND consolidated_to IS NOT NULL "
            "AND event_date < date('now', ?)",
            (f'-{DAILY_LIFE_RETENTION_DAYS} days',))
        # Tier 3: high-score (>=7) — never auto-delete
        conn.execute("""
            DELETE FROM session_log
            WHERE importance <= 3
            AND id NOT IN (
                SELECT id FROM session_log ORDER BY session_date DESC, id DESC LIMIT ?
            )
        """, (SESSION_LOG_KEEP_LIMIT,))
        cur_ver = conn.execute(
            "SELECT value FROM state WHERE key='system_version'").fetchone()
        if cur_ver and cur_ver["value"] != "1.1.0":
            conn.execute(
                "UPDATE state SET value='1.1.0', updated_at=? WHERE key='system_version'",
                (n,))
        conn.commit()
    # VACUUM after DELETE to reclaim disk space
    _exec("VACUUM")
    # heartbeat counter
    cnt = int(state_get("heartbeat_count") or 0) + 1
    state_set("heartbeat_count", str(cnt))
    # versioned backup + auto-clean old
    backup_all(silent=silent)
    # verification
    ok_ = verify_schema(silent=silent) and verify_integrity(silent=silent)
    if not silent:
        if ok_:
            _ok(f"Heartbeat OK | count={cnt} | backup updated")
    return ok_

# ── startup (one-shot self-check) ─────────────────────────────────

def startup():
    """Full startup: migrate + quick_ref + verify + state + cross-check."""
    # 0. Run migration first to align schema with code
    migrate()
    issues = []
    first_run = _is_first_run()
    # 1. quick_ref
    quick_ref()
    # 2. verify
    if not verify_schema():
        issues.append("garbage column detection failed")
    # 3. all state
    all_state = state_get_all()
    # 4. Cross-check: system_version consistency
    db_ver = all_state.get("system_version", "")
    expected = "1.1.0"
    if db_ver != expected:
        if first_run:
            print(f"[OK] First run, version initialized to {expected} (DB={db_ver})")
            state_set("system_version", expected)
        else:
            issues.append(
                f"Version mismatch: DB={db_ver}, code={expected} (run migrate command)")
    # 5. Check heartbeat timestamp
    hb = all_state.get("last_heartbeat", "")
    if not hb and not first_run:
        issues.append("last_heartbeat is empty (abnormal for non-first run)")
    # 6. Check required keys
    required = ['mood', 'active_projects', 'heartbeat_count']
    for k in required:
        if k not in all_state:
            issues.append(f"state missing key: {k} (database may be corrupt)")
        elif not all_state[k]:
            if first_run:
                print(f"[OK] First run, skip empty check: {k}")
            else:
                issues.append(
                    f"state value empty: {k} (abnormal for non-first run)")
    if issues:
        for i in issues:
            _err(i)
        return False
    _ok("Startup self-check all passed")
    return True

# ── daily ─────────────────────────────────────────────────────────

def daily_add(category, content, importance=5):
    _exec(
        "INSERT INTO daily_life(event_date,category,content,importance) VALUES(?,?,?,?)",
        (_today(), category, content, importance))
    r = _get_one(
        "SELECT id FROM daily_life WHERE event_date=? AND category=? AND content=?",
        _today(), category, content)
    if r:
        _ok(f"daily written: [{category}] {content[:40]}... (importance={importance})")
        return True
    _err("daily write verification failed")
    return False

def daily_recent(days=14):
    rows = _get_all(
        "SELECT event_date,category,content FROM daily_life "
        "WHERE event_date >= date('now', ?) ORDER BY event_date DESC",
        f'-{days} days')
    for r in rows:
        print(f"[{r['event_date']}] [{r['category']}] {r['content']}")

# ── session ───────────────────────────────────────────────────────

def session_ensure(title="In Session"):
    """Ensure today's session exists, create empty shell if missing."""
    existing = _get_one("SELECT id FROM session_log WHERE session_date=?", _today())
    if existing:
        return True
    _exec(
        "INSERT INTO session_log(session_date,title,summary,mood_trace,decisions) "
        "VALUES(?,?,?,?,?)",
        (_today(), title, "", "", "[]"))
    _ok(f"session created: {_today()} {title}")
    return True

def chat_append(text):
    """Append chat summary to today's session in real-time, survive crash."""
    ts = _now()
    row = _get_one(
        "SELECT id FROM session_log WHERE session_date=? ORDER BY id DESC LIMIT 1",
        _today())
    if not row:
        _exec(
            "INSERT INTO session_log(session_date,title,summary,mood_trace,decisions) "
            "VALUES(?,?,?,?,?)",
            (_today(), "In Session", "", "", "[]"))
    _exec(
        "UPDATE session_log SET summary = COALESCE(summary,'') || ? || CHAR(10) "
        "WHERE id=(SELECT id FROM session_log WHERE session_date=? "
        "ORDER BY id DESC LIMIT 1)",
        (f"[{ts}] {text}", _today()))
    return True

def session_add(title, summary, mood_trace="", decisions=None, importance=5):
    """Add session record with dedup check (skip if same title+date exists)."""
    existing = _get_one(
        "SELECT id FROM session_log WHERE session_date=? AND title=?",
        _today(), title)
    if existing:
        print(f"[SKIP] session already exists: {title}")
        return True
    _exec(
        "INSERT INTO session_log(session_date,title,summary,mood_trace,decisions,importance) "
        "VALUES(?,?,?,?,?,?)",
        (_today(), title, summary, mood_trace,
         json.dumps(decisions or [], ensure_ascii=False), importance))
    r = _get_one(
        "SELECT id FROM session_log WHERE session_date=? AND title=?",
        _today(), title)
    if r:
        _ok(f"session written: {title} (importance={importance})")
        return True
    _err("session write verification failed")
    return False

def session_recent(n=15):
    rows = _get_all(
        "SELECT session_date,title,summary,mood_trace FROM session_log "
        "ORDER BY session_date DESC LIMIT ?", n)
    for r in reversed(rows):
        print(f"### {r['session_date']} {r['title']}")
        print(f"- {r['summary']}")
        if r['mood_trace']:
            print(f"- Mood: {r['mood_trace']}")
        print()

def session_end(title="Session", summary="", mood_trace="", reflection=""):
    """Atomic session wrap-up.
    All DB writes in single transaction -- rollback on any failure.
    Auto-merge temporary records from chat_append, no summary loss.
    reflection: inner monologue stored to state, recalled by startup next session.
    Backup (file-level op) runs after successful COMMIT."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        n = _now()
        t = _today()

        # 1. Find existing today session (prefer merging chat_append temp records)
        existing = conn.execute(
            "SELECT id, title, summary FROM session_log "
            "WHERE session_date=? ORDER BY id DESC LIMIT 1", (t,)
        ).fetchone()

        if existing:
            if existing["title"] == title:
                print(f"[SKIP] session already exists: {title}")
            else:
                old_summary = (existing["summary"] or "").strip()
                merged = old_summary
                if summary:
                    merged = (
                        f"{old_summary}\n[Wrap-up] {summary}" if old_summary
                        else summary)
                conn.execute(
                    "UPDATE session_log SET title=?, summary=?, mood_trace=? WHERE id=?",
                    (title, merged.strip(), mood_trace, existing["id"]))
                _ok(f"session merged: '{existing['title']}' -> '{title}' "
                    f"({len(old_summary)} chars kept)")
                if old_summary:
                    print(f"[MERGE] chat_append {len(old_summary)} chars merged")
        else:
            conn.execute(
                "INSERT INTO session_log(session_date,title,summary,mood_trace,decisions) "
                "VALUES(?,?,?,?,?)",
                (t, title, summary, mood_trace, "[]"))
            row = conn.execute(
                "SELECT id FROM session_log WHERE session_date=? AND title=?",
                (t, title)).fetchone()
            if not row:
                raise RuntimeError("session write verification failed")
            _ok(f"session written: {title}")

        # 2. heartbeat DB part (same connection)
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) "
            "VALUES('last_heartbeat',?,?)", (n, n))
        conn.execute("INSERT INTO heartbeat_log(heartbeat_at) VALUES(?)", (n,))
        conn.execute(
            "DELETE FROM daily_life WHERE event_date < date('now', ?)",
            (f'-{DAILY_LIFE_RETENTION_DAYS} days',))
        conn.execute("""
            DELETE FROM session_log
            WHERE id NOT IN (
                SELECT id FROM session_log ORDER BY session_date DESC, id DESC LIMIT ?
            )
        """, (SESSION_LOG_KEEP_LIMIT,))
        cur_ver = conn.execute(
            "SELECT value FROM state WHERE key='system_version'").fetchone()
        if cur_ver and cur_ver["value"] != "1.1.0":
            conn.execute(
                "UPDATE state SET value='1.1.0', updated_at=? WHERE key='system_version'",
                (n,))
        cnt = int((conn.execute(
            "SELECT value FROM state WHERE key='heartbeat_count'"
        ).fetchone() or {"value": "0"})["value"] or "0") + 1
        conn.execute(
            "INSERT OR REPLACE INTO state(key,value,updated_at) "
            "VALUES('heartbeat_count',?,?)", (str(cnt), n))

        # 3. verify (same-connection read to avoid dirty reads)
        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        garbage_cols = ['node_type', 'originSessionId']
        for tb in tables:
            safe = "".join([c for c in tb['name'] if c.isalnum() or c == '_'])
            if not safe:
                continue
            cols = [r["name"] for r in conn.execute(
                f"PRAGMA table_info({safe})").fetchall()]
            for gc in garbage_cols:
                if gc in cols:
                    raise RuntimeError(f"Garbage column: {tb['name']}.{gc}")
        integ = conn.execute("PRAGMA integrity_check").fetchone()
        if integ[0] != "ok":
            raise RuntimeError(f"Integrity failed: {integ[0]}")

        conn.commit()
        _ok(f"Session wrap-up complete | heartbeat count={cnt}")

    except Exception as e:
        conn.rollback()
        _err(f"Session wrap-up failed, all rolled back: {e}")
        return False
    finally:
        conn.close()

    # 4. Backup (outside transaction -- read committed data)
    backup_all()
    return True

# ── people ────────────────────────────────────────────────────────

_ALLOWED_RELATIONS = {
    'classmate', 'roommate', 'teacher', 'friend', 'family', 'stranger', 'other'
}

def _sanitize_relation(val):
    """Keyword-based matching for relation types.
    Supports both English and Chinese aliases for backward compatibility."""
    if val is None:
        return 'classmate'
    val = val.strip().lower()

    # 1. Exact alias match (English + Chinese aliases)
    _ALIAS = {
        # Chinese relation aliases for backward compatibility
        '同学': 'classmate', '同桌': 'classmate', '同班': 'classmate',
        '室友': 'roommate', '舍友': 'roommate', '同寝': 'roommate',
        '老师': 'teacher', '教师': 'teacher', '导师': 'teacher',
        '教授': 'teacher', '教练': 'teacher',
        '朋友': 'friend', '兄弟': 'friend', '哥们': 'friend',
        '闺蜜': 'friend', '死党': 'friend',
        '家人': 'family', '爸爸': 'family', '妈妈': 'family',
        '父亲': 'family', '母亲': 'family',
        '爷爷': 'family', '奶奶': 'family', '外公': 'family', '外婆': 'family',
        '哥': 'family', '姐': 'family', '弟': 'family', '妹': 'family',
        '叔': 'family', '姨': 'family', '舅': 'family', '姑': 'family',
        '陌生人': 'stranger', '网友': 'stranger',
        '其他': 'other',
    }
    if val in _ALIAS:
        return _ALIAS[val]
    if val in _ALLOWED_RELATIONS:
        return val

    # 2. Keyword substring match
    _KEYWORD_RULES = [
        (['classmate', 'schoolmate', 'coursemate',
          '同学', '同桌', '同班', '学长', '学姐', '学弟', '学妹'], 'classmate'),
        (['roommate', 'flatmate', 'dormmate',
          '室友', '舍友', '同寝', '宿友'], 'roommate'),
        (['teacher', 'professor', 'instructor', 'mentor', 'coach', 'tutor',
          '老师', '教师', '导师', '教练', '教授', '辅导员'], 'teacher'),
        (['friend', 'buddy', 'pal', 'mate', 'bestie', 'bro', 'sis',
          '朋友', '兄弟', '哥们', '闺蜜', '死党', '好友', '知己', '发小', '铁子'], 'friend'),
        (['family', 'parent', 'father', 'mother', 'dad', 'mom',
          'sister', 'brother', 'grandpa', 'grandma', 'uncle', 'aunt',
          'cousin', 'relative', 'kin',
          '家人', '亲戚', '父母', '爸爸', '妈妈', '父亲', '母亲',
          '爷爷', '奶奶', '外公', '外婆',
          '弟', '妹', '叔', '姨', '舅', '姑', '家'], 'family'),
        (['stranger', 'unknown',
          '陌生人', '网友', '路人', '不熟'], 'stranger'),
    ]
    for keywords, target in _KEYWORD_RULES:
        if any(kw in val for kw in keywords):
            print(f"[INFO] relation '{val}' matched keywords, mapped to '{target}'")
            return target

    # 3. Fallback
    print(f"[WARN] invalid relation '{val}', fallback to 'other'")
    return 'other'

def people_list():
    rows = _get_all(
        "SELECT name,relation,role,hometown,notes FROM people ORDER BY relation,name")
    for r in rows:
        print(f"{r['name']:8s} [{r['relation']:10s}] {r['role'] or ''}  {r['hometown'] or ''}")
        if r['notes']:
            print(f"         {r['notes'][:60]}...")

def people_add(name, relation, role=None, hometown=None, notes=None):
    name = _norm(name)
    relation = _sanitize_relation(relation)
    role = _norm(role)
    hometown = _norm(hometown)
    notes = _norm(notes)
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM people WHERE name=?", (name,)).fetchone()
        if existing:
            conn.execute("""UPDATE people SET
                relation=?, role=COALESCE(?,role), hometown=COALESCE(?,hometown),
                notes=CASE WHEN ? IS NOT NULL THEN ? ELSE notes END, updated_at=?
                WHERE name=?""",
                (relation, role, hometown, notes, notes, _now(), name))
        else:
            conn.execute(
                "INSERT INTO people(name,relation,role,hometown,notes) VALUES(?,?,?,?,?)",
                (name, relation, role, hometown, notes))
        conn.commit()
    _ok(f"people updated: {name}")
    return True

# ── search (cross-dimension full-text LIKE) ───────────────────────

def _escape_like(keyword):
    """Escape LIKE wildcards % and _ to prevent user input being treated as patterns."""
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _search_table(table, fields, keyword, limit=20):
    """LIKE search across multiple columns, return row list."""
    escaped = _escape_like(keyword)
    with get_db() as conn:
        clauses = " OR ".join(
            [f"{f} LIKE '%' || ? || '%' ESCAPE '\\'" for f in fields])
        params = [escaped] * len(fields)
        try:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {clauses} LIMIT ?",
                params + [limit]
            ).fetchall()
        except Exception:
            rows = []
    return rows

# ── SuperMemoryRanker (pure native BM25 semantic engine) ──────────

class SuperMemoryRanker:
    """Pure native BM25 memory retrieval engine.
    Zero deps, N-Gram (unigram+bigram) tokenizer, IDF+TF normalized scoring.
    Metadata pass-through: corpus_list = [(doc_id, "text", {"meta": ...}), ...]"""

    @staticmethod
    def tokenize(text):
        """Static N-Gram tokenizer. Filters punctuation, keeps alphanumeric."""
        text = (text or "").lower().strip()
        text = "".join(re.findall(r'[一-龥a-zA-Z0-9]+', text))
        chars = list(text)
        bigrams = [text[i:i+2] for i in range(len(text)-1)]
        return chars + bigrams

    def __init__(self, corpus_list, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = []
        self.doc_lengths = []
        self.doc_freqs = Counter()
        self.avg_doc_len = 0
        self.meta_map = {}

        if not corpus_list:
            self.doc_count = 0
            return

        for item in corpus_list:
            doc_id = item[0]
            text = item[1]
            meta = item[2] if len(item) > 2 else {}
            words = SuperMemoryRanker.tokenize(text)
            self.docs.append((doc_id, Counter(words)))
            self.doc_lengths.append(len(words))
            self.meta_map[doc_id] = meta
            for w in set(words):
                self.doc_freqs[w] += 1

        self.doc_count = len(corpus_list)
        self.avg_doc_len = (
            sum(self.doc_lengths) / self.doc_count if self.doc_count > 0 else 0)

    def search(self, query_str, top_n=3, min_score=0.0):
        """BM25 scoring + descending sort. min_score threshold filters weak relevance.
        Returns [(doc_id, score, meta_dict), ...]."""
        if self.doc_count == 0:
            return []

        query_words = SuperMemoryRanker.tokenize(query_str)

        scores = []
        for index, (doc_id, doc_words) in enumerate(self.docs):
            score = 0.0
            doc_len = self.doc_lengths[index]
            for word in query_words:
                if word not in doc_words:
                    continue
                df = self.doc_freqs[word]
                raw_idf = (self.doc_count - df + 0.5) / (df + 0.5)
                idf = math.log(max(raw_idf, 0.0) + 1.0)
                tf = doc_words[word]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * (doc_len / self.avg_doc_len))
                score += idf * (numerator / denominator)
            if score > min_score:
                scores.append((doc_id, score, self.meta_map.get(doc_id, {})))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]


def bm25_search(keyword, top_n=5):
    """Full-db BM25 semantic search -- natural language to most relevant memories.
    Return format grouped by table, sorted by BM25 score."""
    if not keyword or not keyword.strip():
        print("Usage: bm25-search <query>")
        return
    kw = keyword.strip()
    found_any = False

    # daily_life
    rows = _get_all(
        "SELECT id, content || ' [' || category || ']' AS text FROM daily_life")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- daily_life (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    # session_log
    rows = _get_all(
        "SELECT id, title || ' ' || COALESCE(summary,'') AS text FROM session_log")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- session_log (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    # people
    rows = _get_all(
        "SELECT id, name || ' ' || COALESCE(relation,'') || ' ' || "
        "COALESCE(role,'') || ' ' || COALESCE(hometown,'') || ' ' || "
        "COALESCE(notes,'') AS text FROM people")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- people (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    # gaming
    rows = _get_all(
        "SELECT game_name AS id, game_name || ' ' || COALESCE(platform,'') || ' ' || "
        "COALESCE(progress,'') || ' ' || COALESCE(highlights,'') AS text FROM gaming")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- gaming (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    # interests
    rows = _get_all(
        "SELECT category||'/'||key AS id, "
        "category || ' ' || key || ' ' || COALESCE(value,'') AS text "
        "FROM interests")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- interests (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    # contests
    rows = _get_all(
        "SELECT id, name || ' ' || COALESCE(role,'') || ' ' || "
        "COALESCE(status,'') || ' ' || COALESCE(deadline,'') AS text FROM contests")
    if rows:
        ranker = SuperMemoryRanker(
            [(r["id"], r["text"], {"raw_text": r["text"]}) for r in rows])
        hits = ranker.search(kw, top_n)
        if hits:
            found_any = True
            print(f"\n-- contests (BM25, {len(hits)} hits) --")
            for doc_id, score, meta in hits:
                print(f"  [score={score:.2f}] {meta.get('raw_text','')[:100]}")

    if not found_any:
        print(f"No results found for '{kw}'")


# ── implicit semantic context (dual-engine) ───────────────────────

def smart_auto_context(user_input: str) -> str:
    """Implicit semantic awakening + entity trigger dual-engine.
    Engine 1: Entity trigger exact match (instant).
    Engine 2: BM25 full-db semantic match (people/contests/gaming/daily/session),
              auto-associate user input with relevant memories.
    min_score=0.5 threshold filters weak relevance noise.

    Memory fuzzing: older (>7d) low-importance (<6) memories get their
    specific details fuzzed — dates become "前阵子", names blur, details
    soften. This mimics human memory decay. High-score memories stay sharp."""
    import random as _random
    from datetime import datetime as _dt

    if not user_input or not user_input.strip():
        return ""

    parts = ["[auto-context] Auto-associated long-term memory context:\n"]

    # Engine 1: entity trigger exact match
    triggers = _get_all("SELECT trigger_word, load_files FROM entity_triggers")
    matched_files = set()
    if triggers:
        for t in triggers:
            tw = t["trigger_word"]
            if tw and tw in user_input:
                for f in t["load_files"].split(","):
                    matched_files.add(f.strip())

    captured = set()
    for f in sorted(matched_files):
        if f in captured:
            continue
        captured.add(f)
        key = f.strip()
        if key in ("mood", "active_projects", "pending_tasks", "today_plan"):
            val = state_get(key)
            if val:
                parts.append(f"[{key}] {val}")
        elif key == "state":
            for k, v in state_get_all().items():
                parts.append(f"[{k}] {v}")
        elif key == "people":
            rows = _get_all(
                "SELECT name, relation, role, hometown, notes FROM people "
                "ORDER BY relation, name")
            if rows:
                parts.append("## People")
                for r in rows:
                    parts.append(
                        f"  {r['name']} [{r['relation']}] "
                        f"{r['role'] or ''} {r['hometown'] or ''}")
        elif key == "contests":
            rows = _get_all(
                "SELECT name, role, deadline, status FROM contests "
                "ORDER BY status, deadline")
            if rows:
                parts.append("## Contests")
                for r in rows:
                    parts.append(
                        f"  [{r['status']}] {r['name']} | "
                        f"deadline: {r['deadline']} | role: {r['role'] or 'member'}")

    # ── Memory fuzzing helper ──────────────────────────────────────
    def _fuzz_memory(text, event_date, importance):
        """Probabilistic fuzz: older + lower importance → more blur.
        Returns (fuzzed_text, was_fuzzed)."""
        if importance is None or importance >= 6:
            return text, False
        if not event_date:
            return text, False
        try:
            days_old = (_dt.now() - _dt.strptime(event_date, "%Y-%m-%d")).days
        except (ValueError, TypeError):
            return text, False
        if days_old <= 7:
            return text, False

        # Probability scales with age and inverse importance
        fuzz_prob = min(0.9, (days_old / 60) * (1 - importance / 10))
        if _random.random() > fuzz_prob:
            return text, False

        # Fuzz: replace specific details with vague ones
        fuzzed = text
        # Blur dates
        fuzzed = re.sub(r'\d{4}-\d{2}-\d{2}', '前阵子', fuzzed)
        fuzzed = re.sub(r'(周[一二三四五六日天])', '那天', fuzzed)
        fuzzed = re.sub(r'(上周|下周|这周|本周)', '前阵子', fuzzed)
        fuzzed = re.sub(r'(昨天|今天|明天)', '那天', fuzzed)
        # Add fuzz marker so AI knows this is a degraded memory
        if fuzzed != text:
            fuzzed = "[模糊记忆] " + fuzzed
        return fuzzed, fuzzed != text

    # Engine 2: BM25 full-db semantic fallback (with fuzzing)
    bm25_hits = []
    tables_config = [
        ("daily_life",
         "id, content || ' [' || category || ']' AS text, event_date, importance",
         "Daily", " ORDER BY id DESC LIMIT 200",
         True),   # has_fuzz_fields
        ("session_log",
         "id, title || ' ' || COALESCE(summary,'') AS text, session_date, importance",
         "Session", " ORDER BY id DESC LIMIT 100",
         True),
        ("people",
         "id, name || ' ' || COALESCE(relation,'') || ' ' || "
         "COALESCE(role,'') || ' ' || COALESCE(hometown,'') || ' ' || "
         "COALESCE(notes,'') AS text, NULL, NULL",
         "People", "",
         False),  # no fuzz for people
        ("gaming",
         "game_name AS id, game_name || ' ' || COALESCE(platform,'') || ' ' || "
         "COALESCE(progress,'') || ' ' || COALESCE(highlights,'') AS text, NULL, NULL",
         "Gaming", "",
         False),
        ("contests",
         "id, name || ' ' || COALESCE(role,'') || ' ' || "
         "COALESCE(status,'') || ' ' || COALESCE(deadline,'') AS text, NULL, NULL",
         "Contest", "",
         False),
    ]
    for config in tables_config:
        table, fields, label, order_limit = config[:4]
        has_fuzz = config[4] if len(config) > 4 else False
        rows = _get_all(f"SELECT {fields} FROM {table}{order_limit}")
        if rows:
            # Build corpus with fuzzing applied
            corpus = []
            for r in rows:
                raw_text = r["text"]
                if has_fuzz:
                    date_field = (r["event_date"] if "event_date" in r.keys()
                                  else r.get("session_date"))
                    imp = r.get("importance")
                    fuzzed_text, was_fuzzed = _fuzz_memory(raw_text, date_field, imp)
                    corpus.append((r["id"], fuzzed_text,
                                   {"label": label, "text": fuzzed_text,
                                    "fuzzed": was_fuzzed}))
                else:
                    corpus.append((r["id"], raw_text,
                                   {"label": label, "text": raw_text,
                                    "fuzzed": False}))
            ranker = SuperMemoryRanker(corpus)
            hits = ranker.search(user_input, top_n=3, min_score=0.5)
            for doc_id, score, meta in hits:
                bm25_hits.append(
                    (meta.get("label", label), score, meta.get("text", ""),
                     meta.get("fuzzed", False)))

    if bm25_hits:
        bm25_hits.sort(key=lambda x: x[1], reverse=True)
        shown = set()
        for label, score, text, was_fuzzed in bm25_hits:
            key = text[:80]
            if key in shown:
                continue
            shown.add(key)
            fuzz_tag = " [fuzzed]" if was_fuzzed else ""
            parts.append(f"[{label}] [score={score:.2f}]{fuzz_tag} {text[:150]}")

    if len(parts) == 1:
        return ""
    return "\n".join(parts)


# ── Graph diffusion algorithm (BFS 2nd-degree social inference) ───

def infer_social_network(target_person: str):
    """BFS-based graph diffusion algorithm (simplified SimRank).
    Build social graph from people table relations + shared events,
    compute 2nd-degree connections.
    Propagation: new_weight = curr_weight x edge_weight x 0.6 (decay factor)."""
    people_rows = _get_all("SELECT name, relation, role, hometown, notes FROM people")
    names = [r["name"] for r in people_rows]

    edges = []
    for i, n1 in enumerate(names):
        for j in range(i+1, len(names)):
            n2 = names[j]
            r1, r2 = people_rows[i]["relation"], people_rows[j]["relation"]
            weight = 0.0
            reasons = []
            if r1 == r2 and r1 in ("classmate", "roommate", "teacher", "friend"):
                weight = 1.0
                reasons.append(f"same {r1}")
            rows = _get_all(
                "SELECT id FROM session_log "
                "WHERE summary LIKE '%' || ? || '%' AND summary LIKE '%' || ? || '%' "
                "LIMIT 1",
                n1, n2)
            if rows:
                weight = max(weight, 0.7)
                reasons.append("shared events")
            rows = _get_all(
                "SELECT id FROM daily_life "
                "WHERE content LIKE '%' || ? || '%' AND content LIKE '%' || ? || '%' "
                "LIMIT 1",
                n1, n2)
            if rows:
                weight = max(weight, 0.6)
                reasons.append("shared daily")
            if weight > 0:
                edges.append((n1, n2, weight, reasons))

    if not edges:
        print("Insufficient graph data, need at least 2 people to infer.")
        return

    graph = {}
    for u, v, w, _ in edges:
        graph.setdefault(u, {})[v] = w
        graph.setdefault(v, {})[u] = w

    if target_person not in graph:
        print(f"\n'{target_person}' is socially isolated, no indirect connections found.")
        return

    visited = {target_person: 1.0}
    queue = [(target_person, 1.0, 0)]

    print(f"\nSocial network inference for '{target_person}' (BFS 2nd-degree):")
    print("-" * 55)
    has_conn = False

    while queue:
        curr, curr_w, curr_d = queue.pop(0)
        if curr_d >= 2:
            continue
        for neighbor, edge_w in graph.get(curr, {}).items():
            if neighbor == target_person:
                continue
            new_w = curr_w * edge_w * 0.6
            if neighbor not in visited or new_w > visited[neighbor]:
                visited[neighbor] = new_w
                queue.append((neighbor, new_w, curr_d + 1))
                if new_w > 0.2:
                    has_conn = True
                    deg = "1st" if curr_d == 0 else "2nd"
                    print(f"  [{deg}] {target_person} <-> {neighbor} (score: {new_w:.2f})")

    if not has_conn:
        print("  (no indirect connections found)")


# ── mood / snapshot / memory-anchor engines ─────────────────────

def analyze_mood_trend():
    """Mood thermometer & resonance word cloud: scan recent daily_life
    for emotional keywords, generate psychological portrait."""
    pos_words = [
        'great', 'happy', 'awesome', 'smooth', 'nice', 'win', 'excited',
        'cool', 'good', 'perfect', 'love', 'fantastic']
    neg_words = [
        'tired', 'crash', 'fail', 'anxious', 'stuck', 'annoyed',
        'terrible', 'awful', 'stress', 'pain', 'exhausted', 'hard']
    rows = _get_all("SELECT content FROM daily_life ORDER BY id DESC LIMIT 50")
    if not rows:
        print("[-] No daily data available, cannot analyze mood trends.")
        return
    total_pos, total_neg = 0, 0
    word_cloud = {}
    for r in rows:
        content = r['content'] or ""
        for w in pos_words:
            cnt = content.count(w)
            total_pos += cnt
            if cnt > 0:
                word_cloud[w] = word_cloud.get(w, 0) + cnt
        for w in neg_words:
            cnt = content.count(w)
            total_neg += cnt
            if cnt > 0:
                word_cloud[w] = word_cloud.get(w, 0) + cnt
    total = total_pos + total_neg
    ratio = total_pos / total if total > 0 else 0.5
    avg_mood = ratio
    print("\n[Mood trend analysis]")
    print("=" * 55)
    print(f"  Energy index: {avg_mood * 100:.1f}% (0~100)")
    status = ("Excellent" if avg_mood > 0.7
              else ("Balanced" if avg_mood > 0.4 else "Low energy"))
    print(f"  Profile: {status}")
    if word_cloud:
        top = sorted(word_cloud.items(), key=lambda x: x[1], reverse=True)[:5]
        cloud = " | ".join([f"{k}({v})" for k, v in top])
        print(f"  Top resonance words: {cloud}")
    print("-" * 55)


def create_git_snapshot(action_name="auto"):
    """Git-like zero-dep versioning: copy db to snapshots dir, keep max 5."""
    snap_dir = os.path.join(DATA_DIR, "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_file = os.path.join(snap_dir, f"snapshot_{ts}_{action_name}.db")
    shutil.copy2(DB_PATH, snap_file)
    all_snaps = sorted(
        [os.path.join(snap_dir, f) for f in os.listdir(snap_dir)
         if f.startswith("snapshot_")],
        key=os.path.getmtime)
    while len(all_snaps) > 5:
        try:
            os.remove(all_snaps.pop(0))
        except OSError:
            pass
    print(f"[SNAP] Snapshot created: snapshot_{ts}_{action_name}.db")


def restore_git_snapshot():
    """List and restore to a selected snapshot."""
    snap_dir = os.path.join(DATA_DIR, "snapshots")
    if not os.path.exists(snap_dir) or not os.listdir(snap_dir):
        print("[-] No historical snapshots found.")
        return
    all_snaps = sorted(
        [f for f in os.listdir(snap_dir) if f.startswith("snapshot_")],
        key=lambda x: os.path.getmtime(os.path.join(snap_dir, x)),
        reverse=True)
    print("\n[Snapshot version manager - available snapshots]:")
    for i, s in enumerate(all_snaps):
        print(f"  [{i}] {s}")
    try:
        choice = input(
            "\nEnter snapshot number to restore (Enter to cancel): ").strip()
        if not choice:
            return
        idx = int(choice)
        selected = os.path.join(snap_dir, all_snaps[idx])
        # safety backup before restore
        shutil.copy2(DB_PATH, DB_PATH + ".pre_restore.bak")
        shutil.copy2(selected, DB_PATH)
        print(f"[+] Restored to snapshot: {all_snaps[idx]}")
    except Exception as e:
        print(f"[-] Restore failed: {e}")


def search(keyword):
    """Cross-dimension full-text search (LIKE exact match).
    Supplements bm25_search for pattern-based queries."""
    if not keyword or not keyword.strip():
        print("Usage: search <keyword>")
        return
    kw = keyword.strip()
    found_any = False

    # daily_life
    rows = _search_table("daily_life", ["event_date", "category", "content"], kw)
    if rows:
        found_any = True
        print(f"\n-- daily_life ({len(rows)} hits) --")
        for r in rows:
            print(f"  [{r['event_date']}] [{r['category']}] {r['content'][:80]}")

    # session_log
    rows = _search_table("session_log", ["session_date", "title", "summary"], kw)
    if rows:
        found_any = True
        print(f"\n-- session_log ({len(rows)} hits) --")
        for r in rows:
            body = (r['summary'] or '')[:80]
            print(f"  [{r['session_date']}] {r['title']} | {body}")

    # state
    rows = _search_table("state", ["key", "value"], kw)
    if rows:
        found_any = True
        print(f"\n-- state ({len(rows)} hits) --")
        for r in rows:
            print(f"  {r['key']}: {(r['value'] or '')[:80]}")

    # people
    rows = _search_table(
        "people", ["name", "relation", "role", "hometown", "notes"], kw)
    if rows:
        found_any = True
        print(f"\n-- people ({len(rows)} hits) --")
        for r in rows:
            print(f"  {r['name']} [{r['relation']}] {r['role'] or ''} {r['hometown'] or ''}")

    # gaming
    rows = _search_table("gaming", ["game_name", "progress", "highlights"], kw)
    if rows:
        found_any = True
        print(f"\n-- gaming ({len(rows)} hits) --")
        for r in rows:
            print(f"  [{r['status']}] {r['game_name']} | {r['progress'] or ''}")

    # interests
    rows = _search_table("interests", ["category", "key", "value"], kw)
    if rows:
        found_any = True
        print(f"\n-- interests ({len(rows)} hits) --")
        for r in rows:
            print(f"  [{r['category']}] {r['key']}: {r['value'] or ''}")

    # contests
    rows = _search_table("contests", ["name", "deadline", "status"], kw)
    if rows:
        found_any = True
        print(f"\n-- contests ({len(rows)} hits) --")
        for r in rows:
            print(f"  [{r['status']}] {r['name']} | deadline: {r['deadline']}")

    # entity_triggers
    rows = _search_table("entity_triggers", ["trigger_word", "load_files"], kw)
    if rows:
        found_any = True
        print(f"\n-- entity_triggers ({len(rows)} hits) --")
        for r in rows:
            print(f"  {r['trigger_word']} -> {r['load_files']}")

    if not found_any:
        print(f"No results found for '{kw}'")

# ── people_graph (relationship inference) ─────────────────────────

def people_graph():
    """Infer social network: shared hometown, class, events, notes mentions.
    Note: shared events use LIKE '%name%' fuzzy match, false-positive risk
    (e.g. "Ann" matches "Annabelle"). Kept as inference aid."""
    people_rows = _get_all(
        "SELECT name, relation, role, hometown, notes FROM people")
    names = [r["name"] for r in people_rows]
    if len(names) < 2:
        print("No inferred relationships (need at least 2 people)")
        return

    found_any = False
    people_map = {r["name"]: r for r in people_rows}

    # 1. Shared hometown
    pairs = _get_all("""
        SELECT a.name n1, b.name n2, a.hometown
        FROM people a JOIN people b ON a.hometown = b.hometown AND a.name < b.name
        WHERE a.hometown IS NOT NULL AND a.hometown != ''
    """)
    if pairs:
        found_any = True
        print("\n-- Shared hometown --")
        for p in pairs:
            print(f"  {p['n1']} <-> {p['n2']}  hometown ({p['hometown']})")

    # 2. Same relation type
    pairs = _get_all("""
        SELECT a.name n1, b.name n2, a.relation
        FROM people a JOIN people b
        ON a.relation = b.relation AND a.name < b.name
        WHERE a.relation IN ('classmate','roommate','teacher','friend')
    """)
    if pairs:
        found_any = True
        print("\n-- Same relation type --")
        for p in pairs:
            print(f"  {p['n1']} <-> {p['n2']}  same {p['relation']}")

    # 3. Shared events -- scan session_log and daily_life
    print("\n-- Shared events --")
    event_hits = 0
    for i, n1 in enumerate(names):
        for n2 in names[i+1:]:
            # search session_log
            rows = _get_all(
                "SELECT session_date, summary FROM session_log "
                "WHERE summary LIKE '%' || ? || '%' "
                "AND summary LIKE '%' || ? || '%' LIMIT 3",
                n1, n2)
            for r in rows:
                event_hits += 1
                snippet = (r['summary'] or '')[:60]
                print(f"  {n1} <-> {n2}  co-occur in [{r['session_date']}] "
                      f"\"{snippet}...\"")
            # search daily_life
            rows = _get_all(
                "SELECT event_date, content FROM daily_life "
                "WHERE content LIKE '%' || ? || '%' "
                "AND content LIKE '%' || ? || '%' LIMIT 3",
                n1, n2)
            for r in rows:
                event_hits += 1
                snippet = (r['content'] or '')[:60]
                print(f"  {n1} <-> {n2}  co-occur in [{r['event_date']}] "
                      f"\"{snippet}...\"")
    if event_hits > 0:
        found_any = True
    else:
        print("  (no shared event records)")

    # 4. Notes mentions -- pre-check with "in" then word-boundary regex
    print("\n-- Notes mentions --")
    mention_hits = 0
    for p in people_rows:
        if not p["notes"]:
            continue
        for other in names:
            if other == p["name"]:
                continue
            notes = p["notes"] or ""
            # Fast substring pre-check
            if other not in notes:
                continue
            # Word-boundary regex to filter false positives
            if re.search(rf'(?<!\w){re.escape(other)}(?!\w)', notes):
                mention_hits += 1
                print(f"  {p['name']}'s notes mention {other}")
            elif len(other) >= 2:
                mention_hits += 1
                print(f"  {p['name']}'s notes mention {other} (fuzzy)")
    if mention_hits > 0:
        found_any = True
    else:
        print("  (no notes mentions)")

    if not found_any:
        print("No inferred relationships")

# ── entity ────────────────────────────────────────────────────────

def entity_lookup(word):
    r = _get_one("SELECT load_files FROM entity_triggers WHERE trigger_word=?", word)
    return r["load_files"] if r else None

def entity_add(word, files_str):
    _exec(
        "INSERT OR REPLACE INTO entity_triggers(trigger_word,load_files) VALUES(?,?)",
        word, files_str)
    _ok(f"entity added: {word}")
    return True

# ── gaming ────────────────────────────────────────────────────────

def gaming_set(game, platform=None, status=None, progress=None, highlights=None):
    game = _norm(game)
    platform = _norm(platform)
    status = _norm(status)
    progress = _norm(progress)
    highlights = _norm(highlights)
    if game is None:
        _err("gaming_set missing game name")
        return False
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM gaming WHERE game_name=?", (game,)).fetchone()
        hl_json = json.dumps(highlights, ensure_ascii=False) if highlights else None
        if existing:
            conn.execute("""UPDATE gaming SET
                platform=COALESCE(?,platform), status=COALESCE(?,status),
                progress=CASE WHEN ? IS NOT NULL THEN ? ELSE progress END,
                highlights=CASE WHEN ? IS NOT NULL THEN ? ELSE highlights END,
                updated_at=? WHERE game_name=?""",
                (platform, status, progress, progress, hl_json, hl_json,
                 _now(), game))
        else:
            conn.execute(
                "INSERT INTO gaming(game_name,platform,status,progress,highlights) "
                "VALUES(?,?,?,?,?)",
                (game, platform or '', status or 'playing', progress, hl_json))
        conn.commit()
    _ok(f"gaming updated: {game}")
    return True

def gaming_list():
    rows = _get_all("SELECT * FROM gaming ORDER BY status, game_name")
    for r in rows:
        print(f"[{r['status']}] {r['game_name']} @ {r['platform']}")
        if r['progress']:
            print(f"  {r['progress']}")

# ── interests ─────────────────────────────────────────────────────

def interest_set(category, key, value):
    _exec(
        "INSERT OR REPLACE INTO interests(category,key,value) VALUES(?,?,?)",
        category, key, value)
    r = _get_one(
        "SELECT value FROM interests WHERE category=? AND key=?", category, key)
    if r and r["value"] == value:
        _ok(f"interest updated: [{category}] {key}")
        return True
    _err("interest write verification failed")
    return False

# ── contests ──────────────────────────────────────────────────────

def contest_add(name, deadline, status="active", role=None,
                teammates=None, details=None):
    _exec(
        "INSERT INTO contests(name,role,deadline,status,teammates,details) "
        "VALUES(?,?,?,?,?,?)",
        (name, role, deadline, status,
         json.dumps(teammates, ensure_ascii=False) if teammates else None,
         json.dumps(details, ensure_ascii=False) if details else None))
    _ok(f"contest added: {name}")
    return True

def contest_list():
    rows = _get_all("SELECT * FROM contests ORDER BY status,deadline")
    for r in rows:
        print(f"[{r['status']}] {r['name']} | deadline: {r['deadline']} | "
              f"role: {r['role'] or 'member'}")

# ── init ──────────────────────────────────────────────────────────

# Inline CREATE TABLE SQL, no external schema.sql dependency.
SQL_SCHEMA = r"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO state VALUES ('mood', '', datetime('now','localtime'));
INSERT INTO state VALUES ('mood_detail', '', datetime('now','localtime'));
INSERT INTO state VALUES ('location', '', datetime('now','localtime'));
INSERT INTO state VALUES ('last_heartbeat', '', datetime('now','localtime'));
INSERT INTO state VALUES ('heartbeat_count', '0', datetime('now','localtime'));
INSERT INTO state VALUES ('today_plan', '', datetime('now','localtime'));
INSERT INTO state VALUES ('active_projects', '', datetime('now','localtime'));
INSERT INTO state VALUES ('pending_tasks', '', datetime('now','localtime'));
INSERT INTO state VALUES ('system_version', '1.1.0', datetime('now','localtime'));
INSERT INTO state VALUES ('last_consolidation', '', datetime('now','localtime'));

CREATE TABLE entity_triggers (
    trigger_word TEXT PRIMARY KEY,
    load_files   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE user_profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    age        INTEGER NOT NULL DEFAULT 18,
    name       TEXT,
    gender     TEXT,
    city       TEXT,
    school     TEXT,
    major      TEXT,
    bio        TEXT,
    devices    TEXT,
    dev_env    TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO user_profile (id) VALUES (1);

CREATE TABLE personality_traits (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    mood_spectrum TEXT,
    triggers    TEXT,
    joy_points  TEXT,
    aesthetics  TEXT,
    social_style TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO personality_traits (id) VALUES (1);

CREATE TABLE feedback_style (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    dislikes    TEXT,
    likes       TEXT,
    hard_rules  TEXT,
    dev_notes   TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO feedback_style (id) VALUES (1);

CREATE TABLE college_learning (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    school_info     TEXT,
    evening_study   TEXT,
    ic_major        TEXT,
    embedded_roadmap TEXT,
    contests        TEXT,
    labview_progress TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO college_learning (id) VALUES (1);

CREATE TABLE contests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    role        TEXT,
    deadline    TEXT,
    status      TEXT,
    teammates   TEXT,
    details     TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    relation    TEXT NOT NULL,
    role        TEXT,
    hometown    TEXT,
    notes       TEXT,
    tags        TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE gaming (
    game_name   TEXT PRIMARY KEY,
    platform    TEXT,
    status      TEXT,
    progress    TEXT,
    highlights  TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE interests (
    category    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (category, key)
);

CREATE TABLE daily_life (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date  TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'event',
    content     TEXT NOT NULL,
    importance  INTEGER NOT NULL DEFAULT 5,
    consolidated_to INTEGER DEFAULT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_daily_date ON daily_life(event_date);

CREATE TABLE session_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    title       TEXT,
    summary     TEXT,
    mood_trace  TEXT,
    decisions   TEXT,
    importance  INTEGER NOT NULL DEFAULT 5,
    consolidated_to INTEGER DEFAULT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_session_date ON session_log(session_date);

CREATE TABLE IF NOT EXISTS summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_type    TEXT NOT NULL,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_count    INTEGER NOT NULL DEFAULT 0,
    importance_avg  REAL NOT NULL DEFAULT 5.0,
    daily_ids       TEXT,
    session_ids     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_summaries_type ON summaries(summary_type);
CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_start, period_end);

CREATE TABLE heartbeat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    heartbeat_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    table_name  TEXT,
    detail      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE VIEW v_quick_ref AS
SELECT key, value FROM state
WHERE key IN ('mood','last_heartbeat','heartbeat_count','today_plan',
              'active_projects','pending_tasks','system_version');

CREATE VIEW v_active_contests AS
SELECT * FROM contests WHERE status != 'done' ORDER BY deadline;
"""

# ── FTS5 schema (created at init time for new installs) ─────────────

FTS_SCHEMA = r"""
    CREATE VIRTUAL TABLE IF NOT EXISTS daily_life_fts USING fts5(
        event_date, category, content, content=daily_life
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS session_log_fts USING fts5(
        session_date, title, summary, content=session_log
    );
    INSERT INTO daily_life_fts(daily_life_fts) VALUES('rebuild');
    INSERT INTO session_log_fts(session_log_fts) VALUES('rebuild');
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
"""

def init_db():
    """Initialize database from inline schema or external schema.sql.
    External schema.sql (if present in script directory) takes priority,
    allowing user customization. Falls back to built-in SQL_SCHEMA.

    FTS5 virtual tables are created here (not in migrate) so new
    installs get them immediately."""
    # Check if DB exists AND has tables (not an empty shell)
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='state'"
            ).fetchone()
            conn.close()
            if tables:
                return  # DB is properly initialized
        except Exception:
            pass  # DB corrupted or unreadable, re-init below
    schema_path = os.path.join(BASE_DIR, "schema.sql")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            if os.path.exists(schema_path):
                print("[INFO] External schema.sql detected, using external table defs")
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            else:
                print("[INFO] Using inline table defs")
                conn.executescript(SQL_SCHEMA)
            # Create FTS5 tables eagerly (not deferred to migrate)
            conn.executescript(FTS_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _ok("Database created")
    except Exception as e:
        _err(f"Database init failed: {e}")
        # Clean partial files (including WAL mode -wal and -shm residue)
        for suffix in ("", "-wal", "-shm"):
            p = DB_PATH + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

# ── migrate (versioned auto-upgrade) ──────────────────────────────

MIGRATIONS = [
    ("1.0.0", """
        -- FTS5 full-text search: daily_life
        CREATE VIRTUAL TABLE IF NOT EXISTS daily_life_fts USING fts5(
            event_date, category, content, content=daily_life
        );
        -- FTS5 full-text search: session_log
        CREATE VIRTUAL TABLE IF NOT EXISTS session_log_fts USING fts5(
            session_date, title, summary, content=session_log
        );
        -- Populate with existing data
        INSERT INTO daily_life_fts(daily_life_fts) VALUES('rebuild');
        INSERT INTO session_log_fts(session_log_fts) VALUES('rebuild');
        -- Trigger: daily_life -> FTS sync
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
        -- Trigger: session_log -> FTS sync
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
    """),
    ("1.1.0", """
        -- Memory consolidation & decay: importance scoring + summaries table
        -- (column additions handled idempotently in migrate())
        CREATE TABLE IF NOT EXISTS summaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_type    TEXT NOT NULL,
            period_start    TEXT NOT NULL,
            period_end      TEXT NOT NULL,
            title           TEXT NOT NULL,
            content         TEXT NOT NULL,
            source_count    INTEGER NOT NULL DEFAULT 0,
            importance_avg  REAL NOT NULL DEFAULT 5.0,
            daily_ids       TEXT,
            session_ids     TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_summaries_type ON summaries(summary_type);
        CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_start, period_end);

        -- Record metadata state key
        INSERT OR IGNORE INTO state(key,value,updated_at)
        VALUES ('last_consolidation','',datetime('now','localtime'));
    """),
]
# For future features, append new migration to MIGRATIONS list

def migrate():
    """Versioned auto-upgrade.
    Read current version from state table, execute unapplied migration SQL in order,
    update system_version after each success. Already-applied steps auto-skipped.
    Uses numeric version comparison (1.10.0 > 1.9.0) and column-existence checks
    for idempotent safety."""
    current = state_get("system_version") or "0.1.0"
    upgraded = False

    def _ver_num(v):
        """Extract numeric version tuple: '1.1.0' -> (1, 1, 0)"""
        try:
            return tuple(int(p) for p in v.split('.'))
        except Exception:
            return (0,)

    def _column_exists(table, column):
        """Check if a column already exists in a table."""
        with get_db() as conn:
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            return column in cols

    for target_ver, sql in MIGRATIONS:
        if _ver_num(current) < _ver_num(target_ver):
            print(f"[MIGRATE] {current} -> {target_ver}")
            try:
                # 1.1.0: idempotent column additions
                if target_ver == "1.1.0":
                    with get_db() as conn:
                        if not _column_exists("daily_life", "importance"):
                            conn.execute("ALTER TABLE daily_life ADD COLUMN importance INTEGER NOT NULL DEFAULT 5")
                        if not _column_exists("daily_life", "consolidated_to"):
                            conn.execute("ALTER TABLE daily_life ADD COLUMN consolidated_to INTEGER DEFAULT NULL")
                        if not _column_exists("session_log", "importance"):
                            conn.execute("ALTER TABLE session_log ADD COLUMN importance INTEGER NOT NULL DEFAULT 5")
                        if not _column_exists("session_log", "consolidated_to"):
                            conn.execute("ALTER TABLE session_log ADD COLUMN consolidated_to INTEGER DEFAULT NULL")
                        conn.executescript(sql)  # summaries + indexes + state
                        conn.commit()
                else:
                    with get_db() as conn:
                        conn.executescript(sql)
                        conn.commit()
                state_set("system_version", target_ver)
                current = target_ver
                upgraded = True
            except Exception as e:
                _err(f"Migration {target_ver} failed: {e} (rolled back)")
                return False
    if upgraded:
        _ok("Database migration complete")
    return True


def fts_search(keyword, limit=20):
    """FTS5 full-text search -- inverted index search on daily_life and session_log.
    10-100x faster than LIKE '%keyword%'. Tries FTS5 MATCH first, LIKE fallback for CJK.
    Returns: [{"table": "...", "rowid": ..., "snippet": "...", "raw": {...}}, ...]"""
    if not keyword or not keyword.strip():
        return []
    results = []
    safe_kw = keyword.strip().replace('"', '').replace("'", "")
    if not safe_kw:
        return []
    escaped = safe_kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with get_db() as conn:
        for fts_table, src_table, cols, label in [
            ("daily_life_fts", "daily_life",
             ["event_date", "category", "content"], "Daily"),
            ("session_log_fts", "session_log",
             ["session_date", "title", "summary"], "Session"),
        ]:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (fts_table,)
            ).fetchone()
            if not exists:
                continue
            # Try FTS5 MATCH first (works for English/alphanumeric)
            try:
                rows = conn.execute(
                    f"SELECT rowid, snippet({fts_table}, 0, '<mark>', '</mark>', "
                    f"'...', 40) AS snippet "
                    f"FROM {fts_table} WHERE {fts_table} MATCH ? "
                    f"ORDER BY rank LIMIT ?",
                    (safe_kw, limit)
                ).fetchall()
            except Exception:
                rows = []
            # FTS5 default tokenizer doesn't handle CJK -> LIKE fallback
            if not rows:
                like_clauses = " OR ".join(
                    [f"{c} LIKE '%' || ? || '%' ESCAPE '\\'" for c in cols])
                params = [escaped] * len(cols)
                rows = conn.execute(
                    f"SELECT rowid, NULL AS snippet FROM {src_table} "
                    f"WHERE {like_clauses} LIMIT ?",
                    params + [limit]
                ).fetchall()
            for r in rows:
                rid = r["rowid"] if "rowid" in r.keys() else (r[0] if r else None)
                src = conn.execute(
                    f"SELECT * FROM {src_table} WHERE rowid=?", (rid,)
                ).fetchone()
                results.append({
                    "table": label,
                    "rowid": rid,
                    "snippet": r["snippet"] or "",
                    "raw": dict(src) if src else {},
                })
    return results


# ── rate limiter persistence ──────────────────────────────────────

_RATELIMIT_DEFS = {
    "session_end":    {"window": 300, "max_calls": 1},
    "heartbeat":      {"window": 300, "max_calls": 1},
    "backup":         {"window": 300, "max_calls": 1},
    "session_add":    {"window": 120, "max_calls": 3},
    "session_ensure": {"window": 120, "max_calls": 2},
    "chat_append":    {"window": 60,  "max_calls": 10},
    # search tool anti-loop rate limit
    "memory_search":       {"window": 60, "max_calls": 3},
    "memory_bm25_search":  {"window": 60, "max_calls": 3},
    "memory_auto_context": {"window": 60, "max_calls": 2},
    "memory_people_graph": {"window": 60, "max_calls": 2},
    "memory_social_infer": {"window": 60, "max_calls": 2},
}


def _check_rate_persistent(op: str) -> str | None:
    """Persistent rate-limit check -- stores call timestamps in state table,
    multi-process/restart safe, auto-clean expired windows.
    Returns None = allow, str = rejection reason."""
    import time as _time
    limit = _RATELIMIT_DEFS.get(op)
    if limit is None:
        return None
    now = _time.time()
    window = limit["window"]
    max_calls = limit["max_calls"]
    key = f"_ratelimit_{op}"

    raw = state_get(key) or "[]"
    try:
        timestamps = json.loads(raw)
    except json.JSONDecodeError:
        timestamps = []

    # Clean outside window
    timestamps = [t for t in timestamps if now - t < window]

    if len(timestamps) >= max_calls:
        wait = int(window - (now - timestamps[0]) + 1)
        return (
            f"Rate limited: {op} called {len(timestamps)} times in {window}s "
            f"(limit {max_calls}), please wait {wait}s before retrying.\n"
            f"Rate limiter persisted to SQLite, shared across restarts/processes."
        )

    timestamps.append(now)
    state_set(key, json.dumps(timestamps))
    return None


# ── tool loop detection ───────────────────────────────────────────

_SEARCH_TOOLS = {
    "memory_search", "memory_bm25_search", "memory_auto_context",
    "memory_people_graph", "memory_social_infer",
}

_CALL_SEQUENCE_KEY = "_tool_call_sequence"
_LOOP_THRESHOLD = 5          # same tool called >= N consecutive times
_SEARCH_TOTAL_LIMIT = 6      # cumulative search limit per request


def _record_tool_call(tool_name: str):
    """Record tool call to persistent sequence (search tools only).
    Auto-insert time marker: if >60s since last call, insert request separator."""
    if tool_name not in _SEARCH_TOOLS:
        return
    import time as _time
    now = _time.time()
    raw = state_get(_CALL_SEQUENCE_KEY) or "[]"
    try:
        seq = json.loads(raw)
    except json.JSONDecodeError:
        seq = []
    # >60s since last call -> insert "___NEW_REQUEST___" separator
    if seq and seq[-1] == "___NO_PREV_TS___":
        pass  # edge case: first write after init
    else:
        last_ts_raw = state_get("_tool_call_last_ts")
        try:
            last_ts = float(last_ts_raw) if last_ts_raw else 0
        except (ValueError, TypeError):
            last_ts = 0
        if last_ts > 0 and now - last_ts > 60:
            seq.append("___NEW_REQUEST___")
    state_set("_tool_call_last_ts", str(now))
    seq.append(tool_name)
    # Keep last 30 entries, prevent unbounded growth
    if len(seq) > 30:
        seq = seq[-30:]
    state_set(_CALL_SEQUENCE_KEY, json.dumps(seq))


def _detect_tool_loop(tool_name: str) -> str | None:
    """Check if same tool called >= LOOP_THRESHOLD times consecutively
    in current request. Counts only after "___NEW_REQUEST___" separator."""
    raw = state_get(_CALL_SEQUENCE_KEY) or "[]"
    try:
        seq = json.loads(raw)
    except json.JSONDecodeError:
        return None
    # Count only current request calls (after last separator)
    current_request = seq
    for i in range(len(seq) - 1, -1, -1):
        if seq[i] == "___NEW_REQUEST___":
            current_request = seq[i+1:]
            break
    if len(current_request) < _LOOP_THRESHOLD:
        return None
    recent = current_request[-_LOOP_THRESHOLD:]
    if all(t == tool_name for t in recent):
        return json.dumps({
            "success": False,
            "error": "tool_loop_detected",
            "message": "Tool loop detected -- stop calling tools and answer the user."
        }, ensure_ascii=False)
    return None


def _check_search_circuit_breaker() -> str | None:
    """Circuit-break if cumulative search tool calls in current request
    exceed SEARCH_TOTAL_LIMIT."""
    raw = state_get(_CALL_SEQUENCE_KEY) or "[]"
    try:
        seq = json.loads(raw)
    except json.JSONDecodeError:
        return None
    # Count only current request calls
    current_request = seq
    for i in range(len(seq) - 1, -1, -1):
        if seq[i] == "___NEW_REQUEST___":
            current_request = seq[i+1:]
            break
    count = sum(1 for t in current_request if t in _SEARCH_TOOLS)
    if count > _SEARCH_TOTAL_LIMIT:
        return json.dumps({
            "success": False,
            "error": "memory_search_limit_reached",
            "message": "Enough memory has been retrieved. Answer the user now."
        }, ensure_ascii=False)
    return None


def _reset_tool_sequence():
    """Reset tool call sequence (call at start of each new user request)."""
    state_set(_CALL_SEQUENCE_KEY, "[]")


# ── auto-context (AI pre-gateway) ─────────────────────────────────

def auto_context(user_input: str) -> str:
    """Scan user input for trigger words, auto-fetch relevant background context.
    Returns assembled context text, prepend to user message in AI conversation."""
    if not user_input or not user_input.strip():
        return ""

    triggers = _get_all("SELECT trigger_word, load_files FROM entity_triggers")
    if not triggers:
        return ""

    matched_files = set()
    for t in triggers:
        tw = t["trigger_word"]
        if tw and tw in user_input:
            for f in t["load_files"].split(","):
                matched_files.add(f.strip())

    if not matched_files:
        return ""

    parts = [
        "[auto-context] Detected background context (from entity trigger match):\n"]
    captured = set()

    for f in sorted(matched_files):
        if f in captured:
            continue
        captured.add(f)
        key = f.strip()
        if key in ("mood", "last_heartbeat", "heartbeat_count", "today_plan",
                    "active_projects", "pending_tasks", "custom_status"):
            val = state_get(key)
            if val:
                parts.append(f"[{key}] {val}")
        elif key == "state":
            for k, v in state_get_all().items():
                parts.append(f"[{k}] {v}")
        elif key == "people":
            rows = _get_all(
                "SELECT name, relation, role, hometown, notes FROM people "
                "ORDER BY relation, name")
            if rows:
                parts.append("## People")
                for r in rows:
                    parts.append(
                        f"  {r['name']} [{r['relation']}] "
                        f"{r['role'] or ''} {r['hometown'] or ''}")
                    if r['notes']:
                        parts.append(f"    Notes: {r['notes'][:80]}")
        elif key == "gaming":
            rows = _get_all(
                "SELECT game_name, platform, status, progress FROM gaming "
                "ORDER BY status, game_name")
            if rows:
                parts.append("## Gaming")
                for r in rows:
                    parts.append(
                        f"  [{r['status']}] {r['game_name']} @ {r['platform']} | "
                        f"{r['progress'] or ''}")
        elif key == "interests":
            rows = _get_all(
                "SELECT category, key, value FROM interests ORDER BY category, key")
            if rows:
                parts.append("## Interests")
                for r in rows:
                    parts.append(f"  [{r['category']}] {r['key']}: {r['value'] or ''}")
        elif key == "contests":
            rows = _get_all(
                "SELECT name, role, deadline, status FROM contests "
                "ORDER BY status, deadline")
            if rows:
                parts.append("## Contests")
                for r in rows:
                    parts.append(
                        f"  [{r['status']}] {r['name']} | "
                        f"deadline: {r['deadline']} | role: {r['role'] or 'member'}")
        elif key == "session":
            rows = _get_all(
                "SELECT session_date, title, summary FROM session_log "
                "ORDER BY session_date DESC LIMIT 5")
            if rows:
                parts.append("## Recent Sessions")
                for r in rows:
                    body = (r['summary'] or '')[:100]
                    parts.append(f"  [{r['session_date']}] {r['title']}: {body}")
        elif key == "daily":
            rows = _get_all(
                "SELECT event_date, category, content FROM daily_life "
                "WHERE event_date >= date('now', '-14 days') "
                "ORDER BY event_date DESC LIMIT 10")
            if rows:
                parts.append("## Recent Daily")
                for r in rows:
                    parts.append(
                        f"  [{r['event_date']}] [{r['category']}] {r['content'][:80]}")
        elif key == "user_profile":
            r = _get_one("SELECT * FROM user_profile WHERE id=1")
            if r:
                parts.append("## User Profile")
                parts.append(f"  {dict(r)}")
        elif key == "personality":
            r = _get_one("SELECT * FROM personality_traits WHERE id=1")
            if r:
                parts.append("## Personality")
                parts.append(f"  {dict(r)}")
        elif key == "college":
            r = _get_one("SELECT * FROM college_learning WHERE id=1")
            if r:
                parts.append("## Learning Path")
                parts.append(f"  {dict(r)}")

    if len(parts) == 1:
        return ""
    return "\n".join(parts)


# ── CSV batch import/export ──────────────────────────────────────

_CSV_WHITELIST = {
    "people", "gaming", "interests", "contests", "entity_triggers",
    "daily_life", "session_log", "state"
}

def export_csv(table: str, out_path: str = None) -> bool:
    """Export table as CSV. out_path empty -> stdout."""
    table = table.strip().lower()
    if table not in _CSV_WHITELIST:
        _err(f"Table not allowed for export: {table} "
             f"(whitelist: {', '.join(sorted(_CSV_WHITELIST))})")
        return False

    rows = _get_all(f"SELECT * FROM {table}")
    if not rows:
        print(f"(Table {table} is empty)")
        return True

    if out_path is None:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow([v if v is not None else "" for v in r])
        return True

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow([v if v is not None else "" for v in r])
    _ok(f"Exported {len(rows)} rows to {out_path}")
    return True


def import_csv(table: str, csv_path: str) -> bool:
    """Transaction-safe CSV batch import.
    Auto-dedup (via PRIMARY KEY/UNIQUE constraints), UPDATE on conflict."""
    table = table.strip().lower()
    if table not in _CSV_WHITELIST:
        _err(f"Table not allowed for import: {table} "
             f"(whitelist: {', '.join(sorted(_CSV_WHITELIST))})")
        return False

    if not os.path.exists(csv_path):
        _err(f"File not found: {csv_path}")
        return False

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print("(CSV empty, no-op)")
        return True

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Column name safety filter -- alphanumeric+underscore only
        raw_cols = list(rows[0].keys())
        cols = [c for c in raw_cols if c.replace('_', '').isalnum()]
        if len(cols) != len(raw_cols):
            _err(f"CSV column names contain illegal chars, "
                 f"filtered: {set(raw_cols) - set(cols)}")
            conn.rollback()
            conn.close()
            return False
        col_list = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))

        table_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk_cols = [r["name"] for r in table_info if r["pk"] > 0]

        inserted = 0
        updated = 0
        for row in rows:
            vals = [row.get(c) or None for c in cols]

            if pk_cols and all(pk in cols for pk in pk_cols):
                sql = f"INSERT OR REPLACE INTO {table}({col_list}) VALUES({placeholders})"
            else:
                sql = f"INSERT INTO {table}({col_list}) VALUES({placeholders})"

            try:
                conn.execute(sql, vals)
                inserted += 1
            except sqlite3.IntegrityError:
                if pk_cols and all(pk in cols for pk in pk_cols):
                    set_clause = ", ".join(
                        [f"{c}=?" for c in cols if c not in pk_cols])
                    where_clause = " AND ".join(
                        [f"{c}=?" for c in pk_cols])
                    if set_clause:
                        update_sql = (
                            f"UPDATE {table} SET {set_clause} WHERE {where_clause}")
                        set_vals = [
                            row.get(c) or None for c in cols if c not in pk_cols]
                        where_vals = [row.get(c) or None for c in pk_cols]
                        conn.execute(update_sql, set_vals + where_vals)
                        updated += 1
                else:
                    updated += 1

        conn.commit()
        _ok(f"CSV import done: {inserted} inserted, {updated} updated")
    except Exception as e:
        conn.rollback()
        _err(f"Import failed, all rolled back: {e}")
        return False
    finally:
        conn.close()
    return True

def stress_test(rounds=20):
    """Stress test: N consecutive write+verify rounds."""
    print(f"  synapse-core stress test -- {rounds} rounds")
    errors = 0
    for i in range(rounds):
        # simulate mood write
        if not state_set("_stress_test", f"round_{i}"):
            errors += 1
        # simulate heartbeat
        n = _now()
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state(key,value,updated_at) "
                "VALUES('_stress_hb',?,?)", (n, n))
            conn.commit()
        # verification
        v = state_get("_stress_hb")
        if v != n:
            errors += 1
    # Clean up test data
    _exec("DELETE FROM state WHERE key IN ('_stress_test','_stress_hb')")
    if errors == 0:
        _ok(f"Stress test passed: {rounds} rounds 0 errors")
        return True
    else:
        _err(f"Stress test failed: {errors} errors")
        return False

# ── CLI (argparse) ────────────────────────────────────────────────

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="synapse_memory.py",
        description="synapse-core -- personal memory engine",
    )
    sub = parser.add_subparsers(dest="command", title="Commands")

    # No-arg commands
    sub.add_parser("quick", help="Show Quick Ref panel")
    sub.add_parser("heartbeat", help="Heartbeat: timestamp+count+clean+verify+backup")
    sub.add_parser("startup", help="Full startup self-check pipeline")
    sub.add_parser("state", help="List all state key-value pairs")
    sub.add_parser("people", help="List all people")
    sub.add_parser("gaming-list", help="List all game progress")
    sub.add_parser("contest-list", help="List all contests")
    sub.add_parser("verify", help="DB garbage column + integrity check")
    sub.add_parser("backup", help="Backup database (versioned)")
    sub.add_parser("init", help="Initialize database")
    sub.add_parser("migrate", help="Migration helper")
    sub.add_parser("people-graph", help="Relationship inference")
    sub.add_parser("summaries", help="List recent memory consolidation summaries")
    sub.add_parser("consolidate-preview", help="Preview unconsolidated records before AI summary")

    # Optional single-arg commands
    p = sub.add_parser("mood", help="Get or set mood")
    p.add_argument("mood_value", nargs="?", default=None,
                   help="New mood value (omit to show current)")

    p = sub.add_parser("daily-recent", help="View recent daily records")
    p.add_argument("days", nargs="?", type=int, default=14,
                   help="Days to look back (default 14)")

    p = sub.add_parser("session-recent", help="View recent session records")
    p.add_argument("n", nargs="?", type=int, default=15,
                   help="Number of entries (default 15)")

    p = sub.add_parser("stress", help="Continuous write stress test")
    p.add_argument("rounds", nargs="?", type=int, default=20,
                   help="Test rounds (default 20)")

    p = sub.add_parser("social-infer",
                       help="Graph diffusion: BFS 2nd-degree social inference")
    p.add_argument("person_name", help="Target person name")

    # Multi-arg commands
    p = sub.add_parser("session-end", help="Session wrap-up all-in-one")
    p.add_argument("title", nargs="?", default="Session",
                   help="Session title (default: Session)")
    p.add_argument("summary", nargs="*", default=None,
                   help="Session summary (multi-word auto-merged)")
    p.add_argument("--mood", default="", help="Mood trace (optional)")

    p = sub.add_parser("daily", help="Add daily record")
    p.add_argument("category", help="Category (e.g. event/rant)")
    p.add_argument("content", nargs="+", help="Content (multi-word auto-merged)")

    p = sub.add_parser("session", help="Manually add session record")
    p.add_argument("title", help="Session title")
    p.add_argument("summary", nargs="+",
                   help="Session summary (multi-word auto-merged)")

    p = sub.add_parser("people-add", help="Add/update person")
    p.add_argument("name", help="Name")
    p.add_argument("relation", help="Relation")
    p.add_argument("role", nargs="?", default=None, help="Role")
    p.add_argument("hometown", nargs="?", default=None, help="Hometown")
    p.add_argument("notes", nargs="?", default=None, help="Notes")

    sub.add_parser("mood-trend", help="Mood trend analysis & resonance word cloud")
    sub.add_parser("snapshot-list", help="View and rollback Git-like DB snapshots")

    p = sub.add_parser("entity", help="Look up entity trigger word")
    p.add_argument("word", help="Trigger word")

    p = sub.add_parser("search", help="Cross-dimension full-text search (LIKE)")
    p.add_argument("keyword", help="Search keyword")

    p = sub.add_parser("bm25-search", help="BM25 semantic search")
    p.add_argument("keyword", nargs="+", help="Natural language query keywords")

    p = sub.add_parser("entity-add", help="Add entity trigger word")
    p.add_argument("word", help="Trigger word")
    p.add_argument("files_str", help="Associated file list")

    p = sub.add_parser("gaming-set", help="Set/update game progress")
    p.add_argument("game", help="Game name")
    p.add_argument("platform", nargs="?", default=None, help="Platform")
    p.add_argument("status", nargs="?", default=None, help="Status")
    p.add_argument("progress", nargs="?", default=None, help="Progress")
    p.add_argument("highlights", nargs="?", default=None, help="Highlights")

    p = sub.add_parser("interest-set", help="Set interest keyword")
    p.add_argument("category", help="Category")
    p.add_argument("key", help="Key")
    p.add_argument("value", nargs="+", help="Value (multi-word auto-merged)")

    p = sub.add_parser("contest-add", help="Add contest")
    p.add_argument("name", help="Contest name")
    p.add_argument("deadline", help="Deadline")
    p.add_argument("status", nargs="?", default="active",
                   help="Status (default: active)")
    p.add_argument("role", nargs="?", default=None, help="Role")

    p = sub.add_parser("state-set", help="Set state key-value pair")
    p.add_argument("key", help="Key name")
    p.add_argument("value", help="Value")

    p = sub.add_parser("session-ensure", help="Ensure today session exists")
    p.add_argument("title", nargs="?", default="In Session",
                   help="Session title (default: In Session)")

    p = sub.add_parser("chat-append", help="Append chat summary to today session")
    p.add_argument("text", nargs="+", help="Chat summary text")

    p = sub.add_parser("auto-context",
                       help="AI pre-gateway: scan input for triggers, auto-fetch context")
    p.add_argument("user_input", nargs="+",
                   help="User message about to send to AI")

    p = sub.add_parser("export-csv", help="Export table as CSV file")
    p.add_argument("table", help="Table name (people/gaming/interests/contests/...)")
    p.add_argument("out_path", nargs="?", default=None,
                   help="Output file path (default stdout)")

    p = sub.add_parser("import-csv", help="Import CSV file data into table")
    p.add_argument("table", help="Table name (matching export-csv)")
    p.add_argument("csv_path", help="CSV file path")

    # Consolidation commands
    p = sub.add_parser("summarize-get", help="Get full content of a summary by ID")
    p.add_argument("summary_id", type=int, help="Summary ID to fetch")

    p = sub.add_parser("consolidate-commit", help="Commit AI-generated consolidation summary")
    p.add_argument("summary_type", help="weekly/monthly/custom")
    p.add_argument("period_start", help="YYYY-MM-DD start")
    p.add_argument("period_end", help="YYYY-MM-DD end")
    p.add_argument("title", help="Summary title")
    p.add_argument("content", nargs="+", help="Summary content (AI-generated)")
    p.add_argument("--daily-ids", default=None,
                   help="Comma-separated daily_life IDs (omit=auto)")
    p.add_argument("--session-ids", default=None,
                   help="Comma-separated session_log IDs (omit=auto)")

    p = sub.add_parser("update-importance", help="Update importance score for a record")
    p.add_argument("table", help="daily_life or session_log")
    p.add_argument("row_id", type=int, help="Row ID")
    p.add_argument("score", type=int, help="New importance (1-10)")

    return parser

def main():
    init_db()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        print("synapse-core -- personal memory engine")
        print("Usage: python synapse_memory.py <command> [args...]")
        print()
        quick_ref()
        return

    cmd = args.command

    # No-arg commands
    if cmd == "quick":
        quick_ref()
    elif cmd == "heartbeat":
        heartbeat()
    elif cmd == "startup":
        startup()
    elif cmd == "state":
        for k, v in state_get_all().items():
            print(f"{k}: {v}")
    elif cmd == "people":
        people_list()
    elif cmd == "gaming-list":
        gaming_list()
    elif cmd == "contest-list":
        contest_list()
    elif cmd == "verify":
        verify_schema()
        verify_integrity()
    elif cmd == "backup":
        backup_all()
    elif cmd == "summaries":
        summaries_list()
    elif cmd == "consolidate-preview":
        consolidate_preview()
    elif cmd == "init":
        init_db()
    elif cmd == "migrate":
        print("migrate: use 'migrate' command from previous versions")
    elif cmd == "session-ensure":
        session_ensure(args.title)
    elif cmd == "chat-append":
        chat_append(' '.join(args.text))

    # Optional single-arg commands
    elif cmd == "mood":
        if args.mood_value is not None:
            mood(args.mood_value)
        else:
            print(mood())
    elif cmd == "daily-recent":
        daily_recent(args.days)
    elif cmd == "session-recent":
        session_recent(args.n)
    elif cmd == "stress":
        stress_test(args.rounds)

    # Multi-arg commands
    elif cmd == "session-end":
        mood_val = getattr(args, 'mood', None)
        session_end(args.title,
                     ' '.join(args.summary) if args.summary else "",
                     mood_val or "")
    elif cmd == "daily":
        daily_add(args.category, ' '.join(args.content))
    elif cmd == "session":
        session_add(args.title, ' '.join(args.summary))
    elif cmd == "people-add":
        people_add(args.name, args.relation, args.role, args.hometown, args.notes)
    elif cmd == "entity":
        print(entity_lookup(args.word))
    elif cmd == "search":
        search(args.keyword)
    elif cmd == "bm25-search":
        bm25_search(' '.join(args.keyword))
    elif cmd == "people-graph":
        people_graph()
    elif cmd == "auto-context":
        result = auto_context(' '.join(args.user_input))
        if result:
            print(result)
        else:
            print("(no trigger words matched)")
    elif cmd == "entity-add":
        entity_add(args.word, args.files_str)
    elif cmd == "gaming-set":
        gaming_set(args.game, args.platform, args.status,
                   args.progress, args.highlights)
    elif cmd == "interest-set":
        interest_set(args.category, args.key, ' '.join(args.value))
    elif cmd == "contest-add":
        contest_add(args.name, args.deadline, args.status, args.role)
    elif cmd == "state-set":
        state_set(args.key, args.value)
    elif cmd == "social-infer":
        infer_social_network(args.person_name)
    elif cmd == "mood-trend":
        analyze_mood_trend()
    elif cmd == "snapshot-list":
        restore_git_snapshot()
    elif cmd == "export-csv":
        export_csv(args.table, args.out_path)
    elif cmd == "import-csv":
        import_csv(args.table, args.csv_path)
    elif cmd == "summarize-get":
        summarize_get(args.summary_id)
    elif cmd == "consolidate-commit":
        dids = ([int(x.strip()) for x in args.daily_ids.split(",") if x.strip()]
                if getattr(args, 'daily_ids', None) else None)
        sids = ([int(x.strip()) for x in args.session_ids.split(",") if x.strip()]
                if getattr(args, 'session_ids', None) else None)
        consolidate_commit(args.summary_type, args.period_start, args.period_end,
                           args.title, ' '.join(args.content),
                           daily_ids=dids, session_ids=sids)
    elif cmd == "update-importance":
        update_importance(args.table, args.row_id, args.score)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
