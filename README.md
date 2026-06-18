# Synapse Core

<div align="center">

**Your AI's permanent brain. No cloud. No accounts. Just one file.**

*Every conversation, every mood, every project — remembered forever.*

</div>

---

## Why Synapse Core?

AI agents are smart, but they're amnesiacs. Every new session starts blank. You repeat your name, your context, your life.

Synapse Core fixes that. It's a **local-first, SQLite-powered memory engine** that plugs into Claude Code and any MCP-compatible AI agent. Your data never leaves your machine.

> "Who was that friend I mentioned last week?" → remembered.
> "What's the deadline for that contest?" → answered.
> "How was I feeling yesterday?" → tracked.

## What Makes It Different

- **Zero Dependencies, Real Search** — BM25 semantic ranking, pure Python, no numpy, no transformers, no bullshit. N-gram tokenizer + IDF scoring from scratch. Just works.
- **Relationship Graph** — Mention two people in the same conversation? Synapse Core maps their connection via BFS diffusion. Your social world, auto-mapped.
- **Dual-Engine Context Awakening** — Entity triggers catch explicit references. BM25 semantic fallback catches the rest. You talk about "that thing last week" and it finds it.
- **Crash-Proof** — SQLite WAL mode. Versioned hot backups. Git-like snapshots with interactive rollback. P2 garbage collection with configurable retention. Your data stays safe.
- **AI-Friendly Architecture** — Not a user-facing app. Not a note-taking tool. Built from the ground up for AI agents to read and write through the MCP protocol.
- **Rate Limiter That Actually Works** — SQLite-persistent, multi-process safe. Prevents AI from burning through your tokens in a search loop.
- **Single File, Simple Stack** — One Python file does it all. SQLite under the hood. No Docker, no Redis, no config hell.
- **35 MCP Tools** — Mood tracking, daily journaling, session logs, people database, game tracker, contest deadlines, interests, CSV import/export, mood trend analysis.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/zhen85988-chen/synapse-core.git
cd synapse-core

# 2. Install MCP SDK (one dep)
pip install mcp

# 3. Register with Claude Code
claude mcp add synapse-core -- python synapse_memory_mcp.py

# 4. Restart Claude Code — done.
```

Now Claude remembers everything. Forever.

## How It Works

```
You → Claude Code → MCP → Synapse Core → ~/.synapse-core/synapse_memory.db
                              ↑
                         35 memory_* tools
                         (read / write / search / backup)
```

Your data lives at `~/.synapse-core/synapse_memory.db`. A single SQLite file. Backups are timestamped and versioned in `memory_backup/`. Snapshots in `snapshots/`. Everything is portable — copy the file, you've copied your entire memory.

## CLI (No MCP Needed)

```bash
python synapse_memory.py startup           # Full self-check
python synapse_memory.py mood "focused"    # Set your mood
python synapse_memory.py daily event "Shipped synapse-core to GitHub"
python synapse_memory.py bm25-search "what did I launch today"
python synapse_memory.py heartbeat         # Cleanup + backup + verify
```

## Project Structure

```
synapse-core/
├── synapse_memory.py          # Core engine (SQLite + argparse CLI)
├── synapse_memory_mcp.py      # MCP server (35 tools, FastMCP)
├── schema.sql                 # Reference schema (optional)
├── test_memory.py             # 37 tests, pytest, isolated temp DBs
├── README.md                  # You are here
├── LICENSE.txt                # GPL v3
└── .mcp.json.example          # Drop-in MCP config
```

## Testing

```bash
pip install pytest
pytest test_memory.py -v
# 37 passed in 2s. All tests use temp databases — your real data is untouched.
```

## License

**GNU General Public License v3.0.** Free to use, modify, and share — but if you distribute it (including SaaS deployments), you must release your changes under GPL v3 too. See [LICENSE.txt](LICENSE.txt).

---

<div align="center">

*Built by someone who got tired of AI forgetting who he is.*

**[⭐ Star on GitHub](https://github.com/zhen85988-chen/synapse-core)**

</div>
