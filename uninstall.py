#!/usr/bin/env python3
"""
Synapse Core — Uninstall
Remove Synapse Core MCP config from all known agent paths.

Usage:
    python uninstall.py
"""

import sys
import os
import json
from pathlib import Path

# ── Fix Windows encoding ──────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Constants ─────────────────────────────────────────────────────────
HOME = Path.home()
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

C = {
    "rst": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
}
if IS_WIN:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        for k in C:
            C[k] = ""


def color(c, text):
    return f"{C.get(c, '')}{text}{C['rst']}"


def ok(msg):
    print(f"  {color('green', '✔')} {msg}")


def fail(msg):
    print(f"  {color('red', '✘')} {msg}")


def info(msg):
    print(f"  {color('dim', '›')} {msg}")


# ── I18n: Chinese / English (same structure as setup_wizard) ─────────────
UI = {
    "banner_title": {"zh": "卸 载 · 安 装 向 导", "en": "U N I N S T A L L   W I Z A R D"},
    "banner_subtitle": {"zh": "SYNAPSE CORE · 清除 MCP 配置", "en": "SYNAPSE CORE · Remove MCP Config"},
    "lang_ask": {"zh": "选择语言 / Select language (1=中文 2=English, 默认1) >>>", "en": "Select language (1=中文 2=English, default=1) >>>"},
    "lang_set": {"zh": "已选择: 中文", "en": "Selected: English"},
    "banner_desc": {"zh": "将从所有已知 Agent 配置文件中移除 synapse-core", "en": "Remove synapse-core from all known agent config files"},
    "confirm_prompt": {"zh": "输入 y 确认 >>>", "en": "Type y to confirm >>>"},
    "cancelled": {"zh": "已取消", "en": "Cancelled"},
    "removed": {"zh": "已移除 {}", "en": "Removed {}"},
    "remove_fail": {"zh": "移除 {} 失败: {}", "en": "Failed to remove {}: {}"},
    "not_found": {"zh": "未找到 Synapse Core 配置，无需卸载", "en": "No Synapse Core config found, nothing to uninstall"},
    "done": {"zh": "✅ 卸载完成。重启 Agent 后生效。", "en": "✅ Uninstall complete. Restart your agent for changes to take effect."},
}

_LANG = "zh"

def t(key, *args):
    entry = UI.get(key, {})
    text = entry.get(_LANG, key)
    if args:
        text = text.format(*args)
    return text


def read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json_safe(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── Agent catalog (same as setup_wizard) ──────────────────────────────
AGENTS = [
    {"id": "claude-code", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".claude" / "settings.json", HOME / ".claude.json"],
     "project_paths": [".claude/settings.json", ".mcp.json"]},
    {"id": "cursor", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".cursor" / "mcp.json"],
     "project_paths": [".cursor/mcp.json"]},
    {"id": "windsurf", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".codeium" / "windsurf" / "mcp_config.json"],
     "project_paths": []},
    {"id": "cline", "config_type": "vscode_settings", "mcp_key": "cline.mcpServers",
     "global_paths": [
         HOME / "AppData" / "Roaming" / "Code" / "User" / "settings.json" if IS_WIN else
         HOME / "Library" / "Application Support" / "Code" / "User" / "settings.json" if IS_MAC else
         HOME / ".config" / "Code" / "User" / "settings.json",
     ],
     "project_paths": [".vscode/settings.json"]},
    {"id": "continue", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".continue" / "config.json"],
     "project_paths": [".continue/config.json"]},
    {"id": "codex", "config_type": "toml", "mcp_key": None,
     "global_paths": [HOME / ".codex" / "config.toml"],
     "project_paths": [".codex/config.toml"]},
    {"id": "gemini-cli", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".gemini" / "mcp.json"],
     "project_paths": [".gemini/mcp.json"]},
    {"id": "kimi-code", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".kimi-code" / "mcp.json"],
     "project_paths": [".kimi-code/mcp.json"]},
    {"id": "mimo-code", "config_type": "mimo_code", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".mimo-code" / "config.json"],
     "project_paths": [".mimo-code.json"]},
    {"id": "deveco-code", "config_type": "opencode", "mcp_key": "mcp",
     "global_paths": [HOME / ".deveco-code" / "config.json"],
     "project_paths": ["deveco.jsonc"]},
    {"id": "opencode", "config_type": "opencode", "mcp_key": "mcp",
     "global_paths": [HOME / ".config" / "opencode" / "opencode.json"],
     "project_paths": ["opencode.json"]},
    {"id": "copilot", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".vscode" / "mcp.json"],
     "project_paths": [".vscode/mcp.json"]},
    {"id": "augment", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".augment" / "mcp.json"],
     "project_paths": ["augment/mcp.json"]},
    {"id": "lingma", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".lingma" / "mcp-settings.json"],
     "project_paths": [".lingma/mcp-settings.json"]},
    {"id": "trae", "config_type": "json_mcpServers", "mcp_key": "mcpServers",
     "global_paths": [HOME / ".trae" / "mcp.json"],
     "project_paths": [".trae/mcp.json"]},
    {"id": "codegeex", "config_type": "vscode_settings", "mcp_key": "codegeex.mcpServers",
     "global_paths": [],
     "project_paths": [".vscode/settings.json"]},
    {"id": "fitten", "config_type": "manual_only", "mcp_key": None,
     "global_paths": [], "project_paths": []},
    {"id": "decode", "config_type": "manual_only", "mcp_key": None,
     "global_paths": [], "project_paths": []},
]


def uninstall():
    removed_any = False
    for agent in AGENTS:
        mcp_key = agent.get("mcp_key", "mcpServers")
        config_type = agent["config_type"]
        all_paths = list(agent.get("global_paths", [])) + [
            Path.cwd() / p if not Path(p).is_absolute() else Path(p)
            for p in agent.get("project_paths", [])
        ]
        for target in all_paths:
            if not target.exists():
                continue
            try:
                existing = read_json_safe(target)
                modified = False
                if config_type == "mimo_code":
                    servers = existing.get("mcpServers", [])
                    if isinstance(servers, list):
                        new_servers = [s for s in servers if s.get("name") != "synapse-core"]
                        if len(new_servers) != len(servers):
                            existing["mcpServers"] = new_servers
                            modified = True
                elif config_type == "toml":
                    content = target.read_text(encoding="utf-8")
                    if "synapse-core" in content:
                        lines = content.split("\n")
                        new_lines = []
                        skip = False
                        for line in lines:
                            if "Synapse Core MCP" in line or "synapse-core" in line:
                                skip = True
                                continue
                            if skip and line.strip() and not line.startswith("#") and "name =" not in line and "command =" not in line and "args =" not in line:
                                skip = False
                            if not skip:
                                new_lines.append(line)
                        target.write_text("\n".join(new_lines), encoding="utf-8")
                        modified = True
                elif mcp_key in existing:
                    servers = existing[mcp_key]
                    if isinstance(servers, dict) and "synapse-core" in servers:
                        del servers["synapse-core"]
                        modified = True
                if modified:
                    write_json_safe(target, existing)
                    ok(t("removed", target))
                    removed_any = True
            except Exception as e:
                fail(t("remove_fail", target, e))
    if not removed_any:
        info(t("not_found"))


def main():
    print("\n" + color("cyan", "═" * 60))
    print(color("cyan", """
   ██╗   ██╗███╗   ██╗██╗███╗   ██╗███████╗████████╗ █████╗ ██╗     ██╗
   ██║   ██║████╗  ██║██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗██║     ██║
   ██║   ██║██╔██╗ ██║██║██╔██╗ ██║███████╗   ██║   ███████║██║     ██║
   ██║   ██║██║╚██╗██║██║██║╚██╗██║╚════██║   ██║   ██╔══██║██║     ██║
   ╚██████╔╝██║ ╚████║██║██║ ╚████║███████║   ██║   ██║  ██║███████╗███████╗
    ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝
"""))
    print(color("bold", "         S Y N A P S E   C O R E   ·   " + t("banner_title")))
    print(color("dim", "         " + t("banner_desc") + "\n"))
    print(color("cyan", "═" * 60))

    # ── Language selection ────────────────────────────────────────────────
    global _LANG
    print(f"\n  {color('bold', t('lang_ask'))}")
    try:
        lang_raw = input(f"  {color('bold', '>>>')} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n")
        sys.exit(0)
    if lang_raw == "2":
        _LANG = "en"
    print(f"  {color('green', '✔')} {t('lang_set')}")

    print(f"\n  {color('yellow', '⚠')} {color('bold', t('confirm_ask'))}")
    try:
        raw = input(f"  {color('red', '>>>')} {t('confirm_prompt')}").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n")
        sys.exit(0)

    if raw.lower() != "y":
        print(f"\n  {color('dim', t('cancelled'))}\n")
        sys.exit(0)

    section_title = t("banner_desc")
    padding = max(0, 60 - len(section_title.encode('utf-8')) - 2)
    print(f"\n{color('cyan', '──')} {section_title} {color('cyan', '─' * padding)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{color('dim', t('cancelled'))}\n")
        sys.exit(0)
