# synapse-core

Persistent memory engine for AI agents. A local-first, SQLite-backed system that gives Claude Code and other MCP-compatible AI agents long-term memory.

Data stays on your machine. No cloud. No accounts. Just a SQLite database.

## Features

- **BM25 Semantic Search** -- pure native implementation, zero dependencies, N-Gram tokenizer + IDF scoring
- **FTS5 Full-Text Search** -- inverted index on daily_life and session_log, 10-100x faster than LIKE
- **Graph Relationship Inference** -- auto-discover second-degree social connections via BFS graph diffusion
- **Implicit Semantic Awakening** -- dual-engine (entity triggers + BM25 semantic fallback), auto-associates context
- **30+ MCP Tools** -- mood, daily, session, people, gaming, contests, interests -- full coverage
- **SQLite WAL Mode** -- hot backup, versioned snapshots, transactional safety
- **CSV Import/Export** -- edit in spreadsheet apps and batch import
- **Rate Limiter** -- SQLite-persistent, multi-process/restart safe
- **Git-like Snapshots** -- interactive snapshot creation and rollback
- **Mood Trend Analysis** -- emotional keyword resonance word cloud

## Architecture

```
synapse-core/
├── synapse_memory.py          # Core engine (SQLite + argparse CLI)
├── synapse-core_mcp.py      # MCP Server wrapper (FastMCP)
├── schema.sql            # Database schema (optional, inline fallback)
├── test_memory.py        # Test suite (37+ tests, pytest)
├── README.md             # This file
├── LICENSE.txt           # MIT License
└── .mcp.json.example     # MCP configuration example
```

Data is stored in `~/.synapse-core/synapse_memory.db` (or in the script directory if an existing database is found there).

## Requirements

- Python 3.10+
- `pip install mcp` (for MCP server)
- `pip install pytest` (for running tests only)

## Quick Start

### CLI Usage

```bash
# Initialize the database
python synapse_memory.py init

# Check status
python synapse_memory.py quick

# Set your mood
python synapse_memory.py mood happy

# Add a daily record
python synapse_memory.py daily event "Started a new project"

# Full startup self-check
python synapse_memory.py startup

# Run a heartbeat (cleanup + backup + verify)
python synapse_memory.py heartbeat

# Search
python synapse_memory.py search "project"
python synapse_memory.py bm25-search "what was I working on yesterday"
```

### MCP Server (Claude Code / AI Agent)

```bash
# Install MCP dependency
pip install mcp

# Register with Claude Code
claude mcp add synapse-core -- python synapse-core_mcp.py

# Or add to your .mcp.json manually (see .mcp.json.example)
```

Restart Claude Code to load all 30+ `memory_*` tools.

### Available MCP Tools

**Read tools:**
- `memory_quick_ref` -- Quick status panel
- `memory_state_get` / `memory_state_get_all` -- Read state values
- `memory_mood_get` -- Get current mood
- `memory_daily_recent` -- Recent daily records
- `memory_session_recent` -- Recent session records
- `memory_people_list` -- List all people
- `memory_gaming_list` -- List game progress
- `memory_contest_list` -- List contests
- `memory_verify` -- Database integrity check
- `memory_startup` -- Full self-check
- `memory_entity_lookup` -- Look up entity trigger word
- `memory_mood_trend` -- Mood trend analysis
- `memory_snapshot_list` -- View/rollback snapshots

**Write tools:**
- `memory_state_set` -- Set state key-value
- `memory_mood_set` -- Set mood
- `memory_daily_add` -- Add daily record
- `memory_session_ensure` -- Ensure today's session exists
- `memory_session_add` -- Add session record
- `memory_session_end` -- Wrap up session + heartbeat + backup
- `memory_chat_append` -- Append to today's session
- `memory_people_add` -- Add/update person
- `memory_entity_add` -- Register entity trigger
- `memory_gaming_set` -- Update game progress
- `memory_interest_set` -- Set interest
- `memory_contest_add` -- Add contest
- `memory_heartbeat` -- Heartbeat + backup
- `memory_backup` -- Hot backup database

**Search tools:**
- `memory_search` -- Full-text search (LIKE)
- `memory_bm25_search` -- BM25 semantic search
- `memory_people_graph` -- Relationship inference
- `memory_social_infer` -- Social network BFS inference
- `memory_auto_context` -- Auto-associate context from user input

**Data tools:**
- `memory_export_csv` -- Export table to CSV
- `memory_import_csv` -- Import CSV into table

## Configuration

Database location is automatic:
1. If `synapse_memory.db` exists in the script directory, it is used (legacy mode).
2. Otherwise, `~/.synapse-core/synapse_memory.db` is used.

Backups are stored in `<data_dir>/memory_backup/` with versioned filenames.

Snapshots are stored in `<data_dir>/snapshots/`.

## Testing

```bash
pip install pytest
pytest test_memory.py -v
```

All tests use temporary databases in isolation -- your real data is never touched.

## License

GNU General Public License v3.0 -- see [LICENSE.txt](LICENSE.txt)
