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

## The Story

I'm an 18-year-old embedded systems student at a vocational college in Wuhan. I use Claude Code during evening self-study sessions. The student council patrols the classrooms and bans phones — but laptops are fine. So I sit there, Claude Code open in the terminal, looking like I'm debugging C code while actually chatting about life, projects, and random bullshit.

Problem was: every time I closed the laptop, Claude forgot everything. I had to reintroduce myself every single night. Name. Major. That I'm learning ESP32. That my grandpa is recovering from a stroke. That I have a competition deadline coming up. That I rage-quit League of Legends again.

So I wrote Synapse Core. Not because I wanted to build a memory system. Because I was annoyed.

Started as a bunch of markdown files. Grew into a Python script. Then a SQLite database. Then BM25 semantic search (wrote it from scratch — no numpy, no dependencies, just me and the N-gram math at 2 AM). Added relationship graph inference. Added 35 MCP tools. Five major rewrites later, here we are.

**This is the system that runs my life.** It tracks my mood, my embedded projects, my 555 timer chip competition, my game progress, my friends, my daily rants about the student council. It works. It hasn't lost a byte of my data. And now it's yours.

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

*Built in a Wuhan dorm room by an 18-year-old who just wanted his AI to remember his name.*

**[⭐ Star on GitHub](https://github.com/zhen85988-chen/synapse-core)** · **[🐛 Report a Bug](https://github.com/zhen85988-chen/synapse-core/issues)**

</div>
