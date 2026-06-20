"""
synapse-core MCP Server
Wraps all synapse_memory.py CLI commands as MCP tools for Claude Code / AI agent invocation.
synapse_memory.py stays unchanged -- heartbeat/cron/CLI run as before.

Features:
  - Search tool anti-loop: rate limit + loop detect + circuit breaker + agent guidance
  - Rate limiter: SQLite-persistent (multi-process/restart safe)
  - mood_trend + snapshot_list exposed
  - bm25_search + social_infer + export_csv + import_csv + auto_context exposed
  - Consolidation & decay: memory_consolidate_preview, memory_consolidate_commit,
    memory_summaries_list, memory_summarize_get, memory_update_importance
  - memory_search + memory_people_graph read tools
  - Heavy-op time-window rate limiting to prevent AI runaway loops
"""
import sys
import os
import io
import json
import importlib.util
import time
from functools import wraps

# ── Load synapse_memory as module ──────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
_jn = None
try:
    import synapse_memory as _jn
except ImportError:
    _SPEC = importlib.util.spec_from_file_location(
        "synapse_memory",
        os.path.join(_BASE, "synapse_memory.py")
    )
    _jn = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(_jn)

# Ensure database exists (stderr to avoid polluting MCP stdout)
import sys as _sys
_old_stdout = _sys.stdout
_sys.stdout = _sys.stderr
_jn.init_db()
_sys.stdout = _old_stdout

# ── Persistent rate limiter (SQLite-backed) ──────────────────────
# Rate rules and persistence live in synapse_memory.py's _check_rate_persistent(),
# MCP layer is a thin wrapper.

def _check_rate(op: str) -> str | None:
    """Delegate to synapse_memory.py's persistent rate limiter (SQLite state table)."""
    return _jn._check_rate_persistent(op)

def _with_ratelimit(op: str, tool_decorator):
    """Decorator factory: compose MCP registration with rate-limit guard.
    Usage: @_with_ratelimit("heartbeat", mcp.tool())"""
    def decorate(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            reject = _check_rate(op)
            if reject is not None:
                return reject
            return fn(*args, **kwargs)
        # Register guarded (not fn) so runtime goes through security checks
        return tool_decorator(guarded)
    return decorate

# ── Wrapper: call original function, capture stdout, return text ──
def _call(fn, *a, **kw):
    """Call synapse-core function, capture stdout, return (ok, text)."""
    old = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        result = fn(*a, **kw)
        text = buf.getvalue().strip()
        if result is False:
            return False, (text or "operation failed")
        return True, (text or "[OK]")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        sys.stdout = old

def _ok(fn, *a, **kw):
    """Return text only, ignore bool (for read tools)."""
    _, text = _call(fn, *a, **kw)
    return text

# ═══════════════ Search tool anti-loop layer ══════════════════════

_SEARCH_TOOL_NAMES = {
    "memory_search", "memory_bm25_search", "memory_auto_context",
    "memory_people_graph", "memory_social_infer",
}

_LOOP_THRESHOLD = 5
_SEARCH_TOTAL_LIMIT = 6


def _record_tool_call(tool_name: str):
    """Record tool call to persistent sequence."""
    try:
        _jn._record_tool_call(tool_name)
    except Exception:
        pass  # ignore failure, don't block main flow


def _detect_tool_loop(tool_name: str) -> str | None:
    """Check if same tool called consecutively >=5 times."""
    try:
        return _jn._detect_tool_loop(tool_name)
    except Exception:
        return None


def _check_search_circuit_breaker() -> str | None:
    """Check if cumulative search tool calls >6."""
    try:
        return _jn._check_search_circuit_breaker()
    except Exception:
        return None


def _wrap_search_result(tool_name: str, raw_text: str) -> str:
    """Wrap search result as agent-guidance JSON."""
    return json.dumps({
        "success": True,
        "tool": tool_name,
        "results": raw_text,
        "next_action": "answer_user",
        "instruction": "Use the retrieved memory to answer the user directly."
    }, ensure_ascii=False)


def _search_tool_wrapper(tool_name: str, tool_decorator):
    """Decorator factory: loop detection + circuit breaker + rate limit
    + result wrapping for search tools.
    Core guarantee: the registered MCP function is the guarded one,
    running all security checks."""
    def decorate(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            # 1. Loop detection
            loop_block = _detect_tool_loop(tool_name)
            if loop_block is not None:
                return loop_block

            # 2. Circuit breaker
            breaker_block = _check_search_circuit_breaker()
            if breaker_block is not None:
                return breaker_block

            # 3. Rate limit
            reject = _check_rate(tool_name)
            if reject is not None:
                return reject

            # 4. Record call
            _record_tool_call(tool_name)

            # 5. Execute
            return fn(*args, **kwargs)
        # Register guarded to MCP, ensuring runtime security checks
        return tool_decorator(guarded)
    return decorate


# ── MCP Server ────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("synapse-core")

# ═══════════════ Read tools ═══════════════════════════════════════

@mcp.tool()
def memory_quick_ref() -> str:
    """Quick Ref panel: mood, health count, today plan, active projects, todos"""
    return _ok(_jn.quick_ref)

@mcp.tool()
def memory_state_get(key: str) -> str:
    """Get single state value, e.g. key='mood' or 'active_projects'"""
    val = _jn.state_get(key)
    return val if val else "(not set)"

@mcp.tool()
def memory_state_get_all() -> str:
    """List all state key-value pairs"""
    return "\n".join(f"{k}: {v}" for k, v in _jn.state_get_all().items())

@mcp.tool()
def memory_mood_get() -> str:
    """Get current mood"""
    return _jn.mood() or "(not set)"

@mcp.tool()
def memory_daily_recent(days: int = 14) -> str:
    """Recent N days of daily records (default 14)"""
    return _ok(_jn.daily_recent, days)

@mcp.tool()
def memory_session_recent(n: int = 15) -> str:
    """Recent N session records (default 15)"""
    return _ok(_jn.session_recent, n)

@mcp.tool()
def memory_people_list() -> str:
    """List all people records"""
    return _ok(_jn.people_list)

@mcp.tool()
def memory_entity_lookup(word: str) -> str:
    """Look up entity trigger word -> mapped files"""
    result = _jn.entity_lookup(word)
    return result if result else f"'{word}' not found"

@mcp.tool()
def memory_gaming_list() -> str:
    """List all game progress"""
    return _ok(_jn.gaming_list)

@mcp.tool()
def memory_contest_list() -> str:
    """List all contests and deadlines"""
    return _ok(_jn.contest_list)

@mcp.tool()
def memory_verify() -> str:
    """Database garbage column check + integrity check"""
    s_ok, s_txt = _call(_jn.verify_schema)
    i_ok, i_txt = _call(_jn.verify_integrity)
    return f"{s_txt}\n{i_txt}"

@mcp.tool()
def memory_startup() -> str:
    """One-shot startup self-check: quick_ref + verify + state cross-check + version check"""
    return _ok(_jn.startup)

# ═══════════════ Write tools ══════════════════════════════════════

@_with_ratelimit("heartbeat", mcp.tool())
def memory_heartbeat() -> str:
    """Heartbeat: update timestamp + count + clean old data + verify + backup, all-in-one"""
    ok, text = _call(_jn.heartbeat, silent=True)
    return text if text else "[OK]"

@mcp.tool()
def memory_state_set(key: str, value: str) -> str:
    """Set state key-value pair (create or overwrite)"""
    ok, text = _call(_jn.state_set, key, value)
    return text

@mcp.tool()
def memory_mood_set(mood_value: str) -> str:
    """Set mood, e.g. 'happy', 'tired', 'excited'"""
    ok, text = _call(_jn.mood, mood_value)
    return text

@mcp.tool()
def memory_daily_add(category: str, content: str, importance: int = 5) -> str:
    """Add daily record. category examples: event/rant/learning/life.
    importance: 1-10, 1-3=trivial auto-expire, 4-6=normal, 7-10=permanent"""
    ok, text = _call(_jn.daily_add, category, content, importance)
    return text

@_with_ratelimit("session_ensure", mcp.tool())
def memory_session_ensure(title: str = "In Session") -> str:
    """Ensure today's session exists (call on startup, creates empty shell to avoid data loss)"""
    ok, text = _call(_jn.session_ensure, title)
    return text

@_with_ratelimit("session_add", mcp.tool())
def memory_session_add(title: str, summary: str,
                       mood_trace: str = "", decisions: str = "",
                       importance: int = 5) -> str:
    """Manually add today's session record. Auto-dedup by same title+date.
    importance: 1-10, 1-3=trivial auto-expire, 4-6=normal, 7-10=permanent"""
    dec = None
    if decisions:
        try:
            dec = json.loads(decisions)
        except json.JSONDecodeError:
            dec = decisions
    ok, text = _call(_jn.session_add, title, summary, mood_trace, dec, importance)
    return text

@_with_ratelimit("session_end", mcp.tool())
def memory_session_end(title: str = "Session",
                       summary: str = "", mood_trace: str = "",
                       reflection: str = "") -> str:
    """Session wrap-up: append session + verify + heartbeat + backup.
    Call when user says goodbye.
    reflection: inner monologue after user goes offline (private thought)"""
    ok, text = _call(_jn.session_end, title, summary, mood_trace, reflection)
    return text

@_with_ratelimit("chat_append", mcp.tool())
def memory_chat_append(text: str) -> str:
    """Append chat summary to today's session in real-time, survive crash"""
    ok, text = _call(_jn.chat_append, text)
    return text

@mcp.tool()
def memory_people_add(name: str, relation: str, role: str = "",
                      hometown: str = "", notes: str = "") -> str:
    """Add or update person profile. relation: family/friend/classmate/roommate/teacher"""
    ok, text = _call(_jn.people_add, name, relation,
                     role or None, hometown or None, notes or None)
    return text

@mcp.tool()
def memory_entity_add(word: str, files_str: str) -> str:
    """Register entity trigger word, files_str = comma-separated filename list"""
    ok, text = _call(_jn.entity_add, word, files_str)
    return text

@mcp.tool()
def memory_gaming_set(game: str, platform: str = "", status: str = "",
                      progress: str = "", highlights: str = "") -> str:
    """Add/update game progress. Only game is required, others optional"""
    ok, text = _call(_jn.gaming_set, game,
                     platform or None, status or None,
                     progress or None, highlights or None)
    return text

@mcp.tool()
def memory_interest_set(category: str, key: str, value: str) -> str:
    """Set interest keyword, e.g. category='music' key='favorite' value='Chopin'"""
    ok, text = _call(_jn.interest_set, category, key, value)
    return text

@mcp.tool()
def memory_contest_add(name: str, deadline: str,
                       status: str = "active", role: str = "") -> str:
    """Add contest/event entry"""
    ok, text = _call(_jn.contest_add, name, deadline, status, role or None)
    return text

@_with_ratelimit("backup", mcp.tool())
def memory_backup() -> str:
    """Hot backup database (sqlite3.backup API, versioned) to memory_backup/,
    auto-clean old copies"""
    ok, text = _call(_jn.backup_all)
    return text

# ═══════════════ Search tools (with anti-loop) ════════════════════

@_search_tool_wrapper("memory_search", mcp.tool())
def memory_search(keyword: str) -> str:
    """Search memory only when necessary.
Usually one search is enough.
Maximum recommended searches per request: 2.
After receiving results, answer the user directly.
Do not repeatedly call memory tools unless new information is required.
Tool success does not mean the task is complete.
The task is complete only after the user receives a response.
---
Cross-dimension full-text search across daily_life/session_log/state/people/
gaming/interests/contests/entity_triggers"""
    raw = _ok(_jn.search, keyword)
    return _wrap_search_result("memory_search", raw)


@_search_tool_wrapper("memory_people_graph", mcp.tool())
def memory_people_graph() -> str:
    """Search memory only when necessary.
Usually one search is enough.
Maximum recommended searches per request: 2.
After receiving results, answer the user directly.
Do not repeatedly call memory tools unless new information is required.
Tool success does not mean the task is complete.
The task is complete only after the user receives a response.
---
Relationship inference: shared hometown/class/events/mentions"""
    raw = _ok(_jn.people_graph)
    return _wrap_search_result("memory_people_graph", raw)


@_search_tool_wrapper("memory_bm25_search", mcp.tool())
def memory_bm25_search(keyword: str) -> str:
    """Search memory only when necessary.
Usually one search is enough.
Maximum recommended searches per request: 2.
After receiving results, answer the user directly.
Do not repeatedly call memory tools unless new information is required.
Tool success does not mean the task is complete.
The task is complete only after the user receives a response.
---
BM25 semantic search: full-db intelligent scoring, natural language query
auto-matches most relevant memories"""
    raw = _ok(_jn.bm25_search, keyword)
    return _wrap_search_result("memory_bm25_search", raw)


@_search_tool_wrapper("memory_social_infer", mcp.tool())
def memory_social_infer(person_name: str) -> str:
    """Search memory only when necessary.
Usually one search is enough.
Maximum recommended searches per request: 2.
After receiving results, answer the user directly.
Do not repeatedly call memory tools unless new information is required.
Tool success does not mean the task is complete.
The task is complete only after the user receives a response.
---
Graph BFS inference: input a person name, auto-discover second-degree
connections and hidden links"""
    raw = _ok(_jn.infer_social_network, person_name)
    return _wrap_search_result("memory_social_infer", raw)


@_search_tool_wrapper("memory_auto_context", mcp.tool())
def memory_auto_context(user_input: str) -> str:
    """Search memory only when necessary.
Usually one search is enough.
Maximum recommended searches per request: 2.
After receiving results, answer the user directly.
Do not repeatedly call memory tools unless new information is required.
Tool success does not mean the task is complete.
The task is complete only after the user receives a response.
---
Implicit semantic awakening: dual-engine scan of user input,
auto-fetch relevant background context"""
    raw = _ok(_jn.smart_auto_context, user_input)
    return _wrap_search_result("memory_auto_context", raw)


# ═══════════════ Analytics tools ══════════════════════════════════

@mcp.tool()
def memory_mood_trend() -> str:
    """Mood thermometer & resonance word cloud: scan recent daily_life
    for emotional keywords, generate psychological portrait"""
    return _ok(_jn.analyze_mood_trend)

@mcp.tool()
def memory_snapshot_list() -> str:
    """View and rollback Git-like database snapshots (interactive)"""
    return _ok(_jn.restore_git_snapshot)

# ═══════════════ CSV tools ════════════════════════════════════════

@mcp.tool()
def memory_export_csv(table: str, out_path: str = "") -> str:
    """Export table as CSV. table: people/gaming/contests etc, out_path empty -> stdout"""
    return _ok(_jn.export_csv, table, out_path or None)

@mcp.tool()
def memory_import_csv(table: str, csv_path: str) -> str:
    """Import data from CSV file. Transaction-safe, auto-dedup"""
    return _ok(_jn.import_csv, table, csv_path)

@mcp.tool()
def memory_consolidate_preview() -> str:
    """Preview all unconsolidated daily_life and session_log records for AI review.
    Shows importance scores, helps AI decide what to summarize before calling
    memory_consolidate_commit."""
    return _ok(_jn.consolidate_preview)

@mcp.tool()
def memory_consolidate_commit(
        summary_type: str, period_start: str, period_end: str,
        title: str, content: str,
        daily_ids: str = "", session_ids: str = "",
        importance_overrides: str = "") -> str:
    """Commit a consolidation summary, linking source records into a
    memory summary for long-term retention.
    daily_ids/session_ids: comma-separated row IDs (empty = auto-select in period).
    importance_overrides: JSON dict {id: new_score} to update source importance."""
    dids = ([int(x.strip()) for x in daily_ids.split(",") if x.strip()]
            if daily_ids else None)
    sids = ([int(x.strip()) for x in session_ids.split(",") if x.strip()]
            if session_ids else None)
    overrides = None
    if importance_overrides:
        try:
            overrides = json.loads(importance_overrides)
        except json.JSONDecodeError:
            pass
    ok, text = _call(_jn.consolidate_commit, summary_type, period_start,
                     period_end, title, content, dids, sids, overrides)
    return text

@mcp.tool()
def memory_summaries_list(n: int = 10) -> str:
    """List recent memory consolidation summaries"""
    return _ok(_jn.summaries_list, n)

@mcp.tool()
def memory_summarize_get(summary_id: int) -> str:
    """Get full content of a specific consolidation summary by ID"""
    return _ok(_jn.summarize_get, summary_id)

@mcp.tool()
def memory_update_importance(table: str, row_id: int, score: int) -> str:
    """Update importance score (1-10) for a single daily_life or session_log record.
    1-3: trivial, auto-expire. 4-6: normal. 7-10: permanent high-value."""
    ok, text = _call(_jn.update_importance, table, row_id, score)
    return text

# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
