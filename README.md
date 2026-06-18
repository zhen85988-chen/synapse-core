# Synapse Core

<div align="center">

```

**Your AI's permanent brain. No cloud. No accounts. Just one file.**

</div>

---

## The Problem

AI agents are smart. They're also amnesiacs.

Every session starts blank. You tell Claude your name, your projects, your friends. It nods along. Then the session ends. Poof. Next time you open it, back to "Hi, I'm Claude, how can I help?"

**I got sick of this.** So I built Synapse Core.

## The Origin Story

I'm 18. I live in Claude Code. Every night, same ritual: open a new session, reintroduce myself. Name. Projects. Friends. Deadlines. What I was building yesterday. Every. Single. Time. Like Groundhog Day but with more yaml.

**Week 1:** Started dumping everything into markdown files. 14 of them. MEMORY.md, gaming.md, people.md, quick_ref.md. Manual labor. Typed entries by hand. Forgot which file had what. Same fact in two places, neither one was right. Grep became my most-used command. Claude read the wrong file and gave me confidently wrong answers.

**Week 2:** Wrote a bootstrap procedure into CLAUDE.md. On every session, Claude auto-scanned MEMORY.md, pulled entity triggers, loaded context. Better. But now the rules said "read markdown" AND "query the database." Two masters pulling in opposite directions. Claude froze mid-conversation. I got silence instead of answers. For days.

**Week 3:** 3 AM. Done. Ripped out all 14 markdown files. Replaced the entire system with one SQLite database + one Python CLI. 19 tables. WAL mode. `memory_mood`, `memory_heartbeat`, `memory_startup` — no more "go read file X," just "tell me what you need and I'll give you the answer." 573 lines of Python. It screamed. Markdown → SQLite in one night.

**Week 4:** Built a BM25 semantic search engine from scratch. Zero dependencies. N-gram tokenizer. IDF scoring. Pure Python, no numpy, no transformers, no bullshit. Then a social graph with BFS diffusion — mention two people together and it auto-discovers the relationship. Then a rate limiter to stop AI agents from burning tokens in infinite search loops. Then a crash-proof backup system with Git-like snapshots.

**Yesterday:** Found the hidden tumor. The old markdown rules were still alive in CLAUDE.md, silently fighting the MCP commands. That's why Claude kept freezing. I surgically removed every dead line. 37 tests went green. Then I stripped the encryption, the license codes, the personal paths. Swapped MIT for GPL v3. **Open sourced it.**

```
markdown → Python → SQLite → BM25 → rate limiter → open source
   ↑          ↑        ↑       ↑         ↑             ↑
  naive     messy    fast   smart    stable        free forever
```

> 21 days. 19 versions. 37 tests. 35 MCP tools.
> Peak cache hit rate 99.5%. More usage means smarter, faster, cheaper.
> One SQLite file. All data local. Zero data loss. Ever.

**And it all started because Claude wouldn't remember my name.**

## Why People Star This Repo

Because AI without memory is half an AI.

Because every Claude user has felt that punch-in-the-gut when a great conversation vanishes.

Because "just use markdown files" is what everyone tries first — and what everyone eventually outgrows.

Because a single SQLite file that gives your AI permanent memory is objectively cool.

Because it's built by someone who actually uses it. Every day. Not a startup. Not a demo. A real tool for a real problem.

Because **one star = one AI that finally remembers who you are.**

## What Makes Synapse Core Different

**Hand-Rolled BM25 That Gets Faster With Scale** — Zero dependencies. Pure Python search engine. N-gram tokenizer, IDF scoring, all from scratch. The more context you feed it, the higher your cache hit rate climbs. 98-99.5% in production. More tokens in = more cache hits = cheaper per request. Free performance upgrade just by using it.

**Social Graph That Sees What You Don't** — Store names, and Synapse Core auto-discovers relationships. Same hometown? Same class? Mentioned together three times? BFS graph diffusion maps connections you never told it about. Your AI starts understanding your world like a friend would.

**Dual-Engine Memory Awakening** — Entity triggers catch explicit references. BM25 semantic fallback catches everything else. Say "that thing I was working on last week" and it surfaces the right memory. No keywords. No guessing. No "I think you mean..." — just the right answer.

**Nuclear-Grade Data Safety** — SQLite WAL mode. All data stays on your machine. Timestamped hot backups. Git-like snapshots with one-command rollback. Automatic garbage collection. Heartbeat self-verification every 20 minutes. Ran for months, zero bytes lost. Your data never touches a cloud, an API, or anyone else's server.

**Built for AI Agents, Not Humans** — Not a note app. Not a knowledge base. A memory server. 35 MCP tools purpose-built for AI read/write access patterns. Your agent doesn't browse files — it queries memory like a brain.

**Anti-Loop Rate Limiter** — AI agents love to search-loop. 6 calls, same query, token burn. Synapse Core detects it and circuit-breaks. SQLite-persistent, survives restarts. Search once, answer once, save your budget.

**One Command Install** — `pip install mcp`. Done. No Docker. No Redis. No .env files. Copy `synapse_memory.db` and you've copied your entire digital memory. Switch machines in seconds.

**35 MCP Tools, One Protocol** — Mood tracking. Daily journal. Session logs. People database. Gaming progress. Contest deadlines. Interests. CSV import/export. Mood trend analysis. Entity triggers. All through one MCP connection.

## 30-Second Install

```bash
git clone https://github.com/zhen85988-chen/synapse-core.git
cd synapse-core
pip install mcp
claude mcp add synapse-core -- python synapse_memory_mcp.py
# Restart Claude Code. Done. It remembers now.
```

## The Stack

```
You → Claude Code → MCP → Synapse Core → ~/.synapse-core/synapse_memory.db
                              ↑
                         35 memory_* tools
                         (read / write / search / backup / snapshot / graph)
```

One file. That's the whole thing. Portable. Copyable. Yours.

## CLI Quick Hits

```bash
python synapse_memory.py startup                       # Full health check
python synapse_memory.py mood "unstoppable"            # Set how you feel
python synapse_memory.py bm25-search "that bug from Tuesday"
python synapse_memory.py heartbeat                     # Backup + verify + clean
```

## Project Map

```
synapse-core/
├── synapse_memory.py          # Core engine (SQLite + argparse, ~2,400 lines)
├── synapse_memory_mcp.py      # MCP server (35 tools, rate-limited)
├── schema.sql                 # Reference schema
├── test_memory.py             # 37 tests, all green, 2s flat
├── README.md                  # You're right here
├── LICENSE.txt                # GPL v3
└── .mcp.json.example          # Drop-in MCP config
```

## Tests (Because Memory Is Too Important To Guess)

```bash
pip install pytest
pytest test_memory.py -v
# 37 passed in 2s. Temp databases only. Your real data is sacred.
```

## License

**GNU General Public License v3.0.** Free to use, modify, share. If you distribute it (SaaS counts) — you open your changes under GPL v3 too. Shared pain, shared gain.

---

<div align="center">

### ⭐ Star this repo if you want your AI to remember you tomorrow.

*Built in 21 days by an 18-year-old who just wanted his name to survive a session.*

**[⭐ Star](https://github.com/zhen85988-chen/synapse-core)** · **[🐛 Bug](https://github.com/zhen85988-chen/synapse-core/issues)** · **[🔱 Fork](https://github.com/zhen85988-chen/synapse-core/fork)**

*One star = one less AI with amnesia.*

</div>
