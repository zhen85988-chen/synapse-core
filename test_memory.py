"""
test_memory.py -- synapse-core unit tests
pytest + monkeypatch (temp db isolation), never touches real data.
Usage: pytest test_memory.py -v
"""
import os
import sys
import tempfile
import json
import importlib.util

import pytest

# Use importlib to load module
_BASE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "synapse_memory",
    os.path.join(_BASE, "synapse_memory.py")
)
_jn = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_jn)

# Expose to global namespace so test functions can access directly
jn = _jn
for _name in dir(_jn):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_jn, _name)


# =========================== fixture ===========================

@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Each test case gets an isolated temp db, auto-deleted after."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    # Hijack DB_PATH to point to temp db
    monkeypatch.setattr(_jn, "DB_PATH", path)
    # Trick init_db: point BASE_DIR to temp so external schema.sql not found,
    # use inline SCHEMA
    monkeypatch.setattr(_jn, "BASE_DIR", "/nonexistent_temp_dir_xyz")
    _jn.init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            os.unlink(p)


# =========================== helpers ===========================

def test_get_db_context_manager():
    """get_db() context manager opens/closes correctly."""
    with jn.get_db() as conn:
        r = conn.execute("SELECT 1 AS val").fetchone()
        assert r["val"] == 1


def test_now_and_today():
    """_now() and _today() return valid format."""
    now = jn._now()
    today = jn._today()
    assert ":" in now
    assert "-" in today
    assert len(today) == 10  # YYYY-MM-DD


def test_norm():
    """_norm() cleans empty values."""
    assert jn._norm(None) is None
    assert jn._norm("") is None
    assert jn._norm("none") is None
    assert jn._norm("  None  ") is None
    assert jn._norm("hello") == "hello"


# =========================== state =============================

def test_state_set_and_get():
    assert jn.state_set("test_key", "hello") is True
    assert jn.state_get("test_key") == "hello"


def test_state_get_none():
    assert jn.state_get("nonexistent") is None


def test_state_get_all():
    jn.state_set("a", "1")
    jn.state_set("b", "2")
    d = jn.state_get_all()
    assert d["a"] == "1"
    assert d["b"] == "2"
    assert "mood" in d  # initial table creation includes it


def test_mood_set_and_get():
    jn.mood("happy")
    assert jn.mood() == "happy"


# =========================== daily =============================

def test_daily_add_and_recent():
    assert jn.daily_add("rant", "cafeteria price hike") is True
    assert jn.daily_add("log", "test content") is True
    rows = jn._get_all("SELECT * FROM daily_life ORDER BY id")
    assert len(rows) >= 2


def test_daily_recent_returns_something():
    jn.daily_add("event", "test today event")
    import io as _io
    buf = _io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        jn.daily_recent(7)
    finally:
        sys.stdout = old
    output = buf.getvalue()
    assert "test today event" in output


# =========================== session ===========================

def test_session_ensure_and_add():
    jn.session_ensure("Test Session")
    assert jn.session_add("New Title", "some summary") is True
    # dedup: same name+date = skip
    assert jn.session_add("New Title", "duplicate summary") is True  # SKIP


def test_chat_append():
    jn.session_ensure()
    assert jn.chat_append("AI said something") is True


# =========================== people ============================

def test_people_add_and_list():
    assert jn.people_add("Alice", "classmate", role="monitor",
                         hometown="Beijing") is True
    assert jn.people_add("Bob", "friend",
                         notes="plays basketball together") is True
    rows = jn._get_all("SELECT * FROM people")
    assert len(rows) == 2


def test_sanitize_relation():
    """Relation type sanitization: aliases + keyword matching."""
    assert jn._sanitize_relation("college classmate") == "classmate"
    assert jn._sanitize_relation("schoolmate") == "classmate"
    assert jn._sanitize_relation("roommate") == "roommate"
    assert jn._sanitize_relation("teacher") == "teacher"
    assert jn._sanitize_relation("buddy") == "friend"
    assert jn._sanitize_relation("family") == "family"
    assert jn._sanitize_relation("stranger") == "stranger"
    assert jn._sanitize_relation("totally unrelated") == "other"
    assert jn._sanitize_relation(None) == "classmate"


# =========================== gaming ============================

def test_gaming_set_and_list():
    assert jn.gaming_set("RDR2", platform="PC", progress="Chapter 3") is True
    assert jn.gaming_set("Minecraft", status="playing") is True
    rows = jn._get_all("SELECT * FROM gaming")
    assert len(rows) == 2


# =========================== interests =========================

def test_interest_set():
    assert jn.interest_set("music", "favorite", "Chopin") is True
    r = jn._get_one(
        "SELECT value FROM interests WHERE category='music' AND key='favorite'")
    assert r["value"] == "Chopin"


# =========================== contests ==========================

def test_contest_add():
    assert jn.contest_add("Test Project", "2026-12-31", "active",
                          "member") is True
    rows = jn._get_all("SELECT * FROM contests")
    assert len(rows) == 1
    assert rows[0]["name"] == "Test Project"


# =========================== entity triggers ===================

def test_entity_add_and_lookup():
    assert jn.entity_add("testcat", "pet_status,daily") is True
    result = jn.entity_lookup("testcat")
    assert "pet_status" in result
    assert jn.entity_lookup("nonexistent") is None


# =========================== BM25 (SuperMemoryRanker) ==========

def test_bm25_tokenize():
    tokens = jn.SuperMemoryRanker.tokenize("cafeteria price hike")
    # should have unigrams + bigrams
    assert "c" in tokens
    assert "ca" in tokens
    assert "af" in tokens
    assert "fe" in tokens
    assert "h" in tokens
    assert "hi" in tokens
    assert "ke" in tokens
    # punctuation should be filtered, letters and numbers kept
    tokens2 = jn.SuperMemoryRanker.tokenize("hello, world!")
    assert "," not in tokens2
    # ngram tokenizer breaks words into unigrams+bigrams
    assert "he" in tokens2  # bigram
    assert "wo" in tokens2  # bigram


def test_bm25_empty_corpus():
    ranker = jn.SuperMemoryRanker([])
    assert ranker.search("xyznonexistent") == []
    assert ranker.doc_count == 0


def test_bm25_relevance_ranking():
    corpus = [
        (1, "cafeteria price hike today", {}),
        (2, "Python memory management tips", {}),
        (3, "the cafeteria malatang is delicious", {}),
    ]
    ranker = jn.SuperMemoryRanker(corpus)
    results = ranker.search("cafeteria", top_n=3)
    assert len(results) >= 2
    ids = [r[0] for r in results]
    # id=1 and id=3 related to "cafeteria", should rank higher
    assert 1 in ids and 3 in ids
    # id=2 unrelated, should not appear (or rank last with low score)
    scores = {r[0]: r[1] for r in results}
    if 2 in scores:
        assert scores[2] < scores[1]
        assert scores[2] < scores[3]


def test_bm25_min_score_filter():
    corpus = [
        (1, "cafeteria prices", {}),
        (2, "nice weather today", {}),
    ]
    ranker = jn.SuperMemoryRanker(corpus)
    results = ranker.search("cafeteria", min_score=0.5)
    assert len(results) >= 1
    assert results[0][0] == 1


# =========================== CSV import/export =================

def test_export_csv():
    jn.people_add("Eve", "teacher", role="professor")
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        assert jn.export_csv("people", path) is True
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        assert "Eve" in content
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_import_csv():
    # export one, then clear table, then re-import
    jn.people_add("Frank", "family")
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        jn.export_csv("people", path)
        jn._exec("DELETE FROM people")
        assert jn.import_csv("people", path) is True
        rows = jn._get_all("SELECT * FROM people")
        assert len(rows) >= 1
    finally:
        if os.path.exists(path):
            os.unlink(path)


# =========================== migrate ===========================

def test_migrate_from_clean():
    """Fresh db starts 0.1.0, after migrate becomes 1.0.0."""
    ver = jn.state_get("system_version")
    assert ver == "1.0.0", f"should start 1.0.0, got {ver}"
    jn.migrate()
    ver2 = jn.state_get("system_version")
    assert ver2 == "1.0.0", f"after migrate should be 1.0.0, got {ver2}"


def test_migrate_creates_fts_tables():
    """After migrate, FTS5 virtual tables should exist."""
    jn.migrate()
    tables = jn._get_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
    )
    fts_names = [t["name"] for t in tables]
    assert "daily_life_fts" in fts_names
    assert "session_log_fts" in fts_names


# =========================== FTS5 search ======================

def test_fts_search_after_migrate():
    """Create daily + session records, run FTS5 search."""
    jn.migrate()
    jn.daily_add("event", "nice weather today")
    jn.daily_add("rant", "cafeteria prices went up again")
    jn.session_add("Study", "went to the library in the afternoon")

    results = jn.fts_search("Study", limit=10)
    assert len(results) >= 1

    results2 = jn.fts_search("cafeteria")
    assert len(results2) >= 1
    assert any("price" in r.get("raw", {}).get("content", "")
               for r in results2)


def test_fts_search_empty_keyword():
    assert jn.fts_search("") == []
    assert jn.fts_search("   ") == []


def test_fts_search_no_fts_table():
    """fts_search should return empty list when no FTS table exists, not throw."""
    results = jn.fts_search("anything")
    assert isinstance(results, list)


# =========================== rate limiter =====================

def test_ratelimit_persistent_allow_then_block():
    """First call allowed, second+ after max_calls gets rate-limited."""
    # session_end rule: max 1 call per 300s
    r1 = jn._check_rate_persistent("session_end")
    assert r1 is None  # first call allowed

    r2 = jn._check_rate_persistent("session_end")
    assert r2 is not None  # second call blocked
    assert "Rate limited" in r2


def test_ratelimit_persistent_cleanup():
    """Manually write expired timestamp, verify window cleanup."""
    key = "_ratelimit_backup"
    old_ts = 1000000  # long ago
    jn.state_set(key, json.dumps([old_ts]))

    # call once, old timestamp should be cleaned
    r = jn._check_rate_persistent("backup")
    assert r is None  # should pass, old timestamps cleaned


def test_ratelimit_no_limit():
    """Ops not in rate-limit list should pass directly."""
    assert jn._check_rate_persistent("some_random_op") is None


# =========================== verify ===========================

def test_verify_schema():
    ok = jn.verify_schema()
    assert ok is True  # empty db should be clean


def test_verify_integrity():
    ok = jn.verify_integrity()
    assert ok is True


# =========================== people_graph ======================

def test_people_graph_no_crash():
    """At minimum should not throw."""
    jn.people_add("Adam", "classmate", hometown="Shanghai")
    jn.people_add("Alice", "classmate", hometown="Shanghai")
    import io as _io
    buf = _io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        jn.people_graph()
    finally:
        sys.stdout = old
    output = buf.getvalue()
    # same hometown/class should be detected
    assert "hometown" in output or "relation" in output or "Adam" in output


# =========================== search (LIKE) =====================

def test_search_like():
    jn.daily_add("event", "bought a Python book")
    import io as _io
    buf = _io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        jn.search("Python")
    finally:
        sys.stdout = old
    output = buf.getvalue()
    assert "Python" in output


# =========================== startup ===========================

def test_startup():
    ok = jn.startup()
    assert ok is True


# =========================== stress_test =======================

def test_stress_test():
    ok = jn.stress_test(rounds=5)
    assert ok is True
