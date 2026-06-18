# Synapse Core

<div align="center">

**Your AI's permanent brain. No cloud. No accounts. Just one file.**

*Every conversation, every mood, every project — remembered forever.*

</div>

---

## The Problem

AI agents are smart. They're also amnesiacs.

Every session starts blank. You tell Claude your name, your projects, your friends. It nods along. Then the session ends. Poof. Next time you open it, back to "Hi, I'm Claude, how can I help?"

I got sick of this. So I built Synapse Core.

## How It Was Built

### Day 1 (May 29) — "Claude keeps forgetting my name"
Every new session, Claude has no idea who I am. Name, projects, friends — gone. So I start throwing notes into markdown files. Manually. 14 files. MEMORY.md for the index, gaming.md for games, people.md for friends. It works. Barely.

### Week 1 — "Where did I put that thing?"
The markdown pile grows. Same fact in two places. Search means grepping file names. I forget which file has what. Claude reads the wrong one. Wrong answer, wasted tokens.

### June 1 — "Ok fine, I'll give the system rules"
I write a bootstrap procedure into CLAUDE.md. On every session, Claude auto-reads MEMORY.md, scans entity triggers, pulls the right context. It's better. But now I have two problems: the rules say "read markdown" AND "query the database." Two masters, both yelling. Claude freezes. I get silence instead of answers.

### June 3 — "What if I lose everything?"
I run disaster recovery drills: delete CLAUDE.md, corrupt quick_ref, nuke a new file. All three scenarios pass. Heartbeat timers deployed (10 rounds + 20 minute fallback). Rename everything to v4.0. I think I'm done. I am not done.

### June 14 — "Screw markdown. SQLite."
Three AM. Fed up. I rip out all 14 markdown files and replace them with one SQLite database + one Python CLI. 19 tables of schema. WAL mode. `memory_mood`, `memory_heartbeat`, `memory_startup` — no more "go read file X," just "tell me what you want and I'll give you the answer." 573 lines of Python. It flies. Markdown → SQLite in one night.

### June 15 — "AI agents loop themselves to death"
Claude starts calling search tools in cycles. 6 searches for the same thing. Token burn. So I build a rate limiter. SQLite-persistent. Survives restarts. Detects loops. Circuit breaker. Search once, answer once. Ship it as v5.3.

### June 18 — "This tumor has to go" + open source
Morning: I realize the old markdown rules still live in CLAUDE.md, silently fighting the new MCP commands. That's why Claude freezes mid-conversation. I surgically remove every dead rule. 35 tests go green.

Afternoon: I decide to open source it. Strip the encryption. Strip the license codes. Strip my personal paths. 37 tests, 35 MCP tools, zero broken references. Swap the license from MIT to GPL v3 — use it, love it, but if you close-source it, you publish your changes.

10:40 PM. GitHub push. Done.

> 19 versions. 37 tests. 35 MCP tools. 1.4 billion tokens processed. 99.2% cache hit rate. $12.45 total spend.
> One database file. Zero data loss ever.

**And it all started because Claude wouldn't remember my name.**

## Why Synapse Core?

> "Who was that friend I mentioned last week?" → remembered.
> "What's the deadline for that competition?" → answered.
> "What was I working on three days ago?" → found.

One SQLite file. Your entire digital memory. No cloud subscription. No API keys. No one else's server.

## What Makes It Different

**Hand-Rolled BM25 Search** — Zero dependencies. N-gram tokenizer. IDF scoring. Pure Python. Written late at night because "how hard can search be?" (Answer: pretty hard. But it works.)

**Social Graph Inference** — Your AI doesn't just store names. It discovers relationships. Two people mentioned in the same conversation? Same hometown? Same class? BFS graph diffusion maps connections you didn't explicitly tell it about.

**Dual-Engine Context Wake-Up** — Explicit entity triggers for things you name. BM25 semantic fallback for things you don't. Mention "that thing last week" and it surfaces the right memory. No keyword guessing.

**Actually Crash-Proof** — SQLite WAL mode. Timestamped hot backups. Git-like snapshots you can roll back to. Automatic P2 garbage collection. Heartbeat-based self-verification. I've run this for months. Zero data loss.

**Built for AI Agents, Not Humans** — This isn't a note app. It's an MCP server. Claude Code and other MCP-compatible agents read and write through 35 tools. The schema is designed for AI access patterns, not for pretty UIs.

**Rate Limiter That Saves Your Tokens** — AI agents love to search-loop. Synapse Core detects it and stops it before it burns through your context window. SQLite-persistent, survives restarts.

**Single File, Zero Config** — Copy `synapse_memory.db` and you've copied everything. Backups, snapshots, all portable. No Docker. No Redis. No .env files. Just Python and SQLite.

**35 MCP Tools, One Protocol** — Mood, daily journal, session logs, people, gaming, contests, interests, CSV import/export, mood trend analysis, entity triggers. Every tool is one MCP call away.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/zhen85988-chen/synapse-core.git
cd synapse-core

# 2. One dependency
pip install mcp

# 3. Register with Claude Code
claude mcp add synapse-core -- python synapse_memory_mcp.py

# 4. Restart Claude Code.
```

That's it. Your AI now has permanent memory. Go talk to it — it remembers.

## How It Works

```
You → Claude Code → MCP → Synapse Core → ~/.synapse-core/synapse_memory.db
                              ↑
                         35 memory_* tools
                         (read / write / search / backup)
```

One database file. `~/.synapse-core/synapse_memory.db`. Backups versioned in `memory_backup/`. Snapshots in `snapshots/`. Copy the file, you've copied your entire memory. Switch machines, it follows you.

## CLI (Standalone — No MCP Needed)

```bash
python synapse_memory.py startup                       # Full self-check
python synapse_memory.py mood "unstoppable"            # Set your mood
python synapse_memory.py daily event "Shipped to prod"
python synapse_memory.py bm25-search "when did I ship"
python synapse_memory.py heartbeat                     # Cleanup + backup + verify
```

## Project Structure

```
synapse-core/
├── synapse_memory.py          # Core engine (SQLite + argparse CLI, ~2,400 lines)
├── synapse_memory_mcp.py      # MCP server (35 tools, rate-limited, anti-loop)
├── schema.sql                 # Reference schema
├── test_memory.py             # 37 tests, pytest, isolated temp DBs
├── README.md                  # You're reading this
├── LICENSE.txt                # GPL v3
└── .mcp.json.example          # Drop-in MCP config
```

## Testing

```bash
pip install pytest
pytest test_memory.py -v
# 37 passed in 2s. Never touches your real data.
```

## License

**GNU General Public License v3.0.** Use it, modify it, ship it — but if you distribute it (SaaS counts), you publish your changes under GPL v3 too. Built in the open, stays in the open. See [LICENSE.txt](LICENSE.txt).

---

<div align="center">

*Built by an 18-year-old who just wanted his AI to remember his name.*

**[⭐ Star on GitHub](https://github.com/zhen85988-chen/synapse-core)** · **[🐛 Report a Bug](https://github.com/zhen85988-chen/synapse-core/issues)**

</div>
