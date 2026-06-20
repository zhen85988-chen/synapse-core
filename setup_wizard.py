#!/usr/bin/env python3
"""
Synapse Core — Interactive Setup Wizard
One script to install MCP memory on any AI agent.
Covers 18 agents: Claude Code, Cursor, Windsurf, Cline, Continue, Codex,
Gemini CLI, Kimi Code, OpenCode, GitHub Copilot, 通义灵码, Trae, CodeGeeX,
Fitten Code, Decode (MarsCode), Augment, MiMo Code (小米), DevEco Code (华为).

Usage:
    python setup_wizard.py
"""

import sys
import os
import json
import subprocess
import platform
import shutil
from pathlib import Path

# ── Fix Windows encoding ──────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Constants ─────────────────────────────────────────────────────────
SYNAPSE_DIR = Path(__file__).resolve().parent
MCP_SERVER_PATH = SYNAPSE_DIR / "synapse_memory_mcp.py"
COVER_PATH = SYNAPSE_DIR / "setup_cover.jpg"
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
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "magenta": "\033[95m",
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


def section(title):
    print(f"\n{color('cyan', '══')} {color('bold', title)} {color('cyan', '═' * (60 - len(title)))}")


def ok(msg):
    print(f"  {color('green', '✔')} {msg}")


def fail(msg):
    print(f"  {color('red', '✘')} {msg}")


def warn(msg):
    print(f"  {color('yellow', '⚠')} {msg}")


def info(msg):
    print(f"  {color('dim', '›')} {msg}")


# ── Agent catalog ─────────────────────────────────────────────────────
# Each agent: display name, config type, global path, project path, config key, notes
AGENTS = [
    # ── International ──
    {
        "id": "claude-code",
        "name": "Claude Code (CLI)",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [
            HOME / ".claude" / "settings.json",
            HOME / ".claude.json",
        ],
        "project_paths": [
            ".claude/settings.json",
            ".mcp.json",
        ],
        "mcp_key": "mcpServers",
        "hint": "终端运行 claude 即可",
    },
    {
        "id": "cursor",
        "name": "Cursor AI",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".cursor" / "mcp.json"],
        "project_paths": [".cursor/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "VS Code 内核的 Cursor IDE",
    },
    {
        "id": "windsurf",
        "name": "Windsurf",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".codeium" / "windsurf" / "mcp_config.json"],
        "project_paths": [],  # Windsurf only has global
        "mcp_key": "mcpServers",
        "hint": "文件名是 mcp_config.json 不是 mcp.json",
    },
    {
        "id": "cline",
        "name": "Cline (VS Code)",
        "group": "国际",
        "config_type": "vscode_settings",
        "global_paths": [
            HOME / "AppData" / "Roaming" / "Code" / "User" / "settings.json" if IS_WIN else
            HOME / "Library" / "Application Support" / "Code" / "User" / "settings.json" if IS_MAC else
            HOME / ".config" / "Code" / "User" / "settings.json",
        ],
        "project_paths": [".vscode/settings.json"],
        "mcp_key": "cline.mcpServers",
        "hint": "写入 VS Code settings.json 的 cline.mcpServers 字段",
    },
    {
        "id": "continue",
        "name": "Continue.dev",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".continue" / "config.json"],
        "project_paths": [".continue/config.json"],
        "mcp_key": "mcpServers",
        "hint": "开源 AI 编程助手",
    },
    {
        "id": "codex",
        "name": "Codex CLI (OpenAI)",
        "group": "国际",
        "config_type": "toml",
        "global_paths": [HOME / ".codex" / "config.toml"],
        "project_paths": [".codex/config.toml"],
        "mcp_key": None,  # TOML format, handled separately
        "hint": "TOML 格式，跟其他都不一样",
    },
    {
        "id": "gemini-cli",
        "name": "Gemini CLI (Google)",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".gemini" / "mcp.json"],
        "project_paths": [".gemini/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "Google Gemini CLI 工具",
    },
    {
        "id": "kimi-code",
        "name": "Kimi Code (月之暗面)",
        "group": "国产",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".kimi-code" / "mcp.json"],
        "project_paths": [".kimi-code/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "月之暗面 Kimi 编程助手",
    },
    {
        "id": "mimo-code",
        "name": "MiMo Code (小米)",
        "group": "国产",
        "config_type": "mimo_code",
        "global_paths": [HOME / ".mimo-code" / "config.json"],
        "project_paths": [".mimo-code.json"],
        "mcp_key": "mcpServers",
        "hint": "⚠ 数组格式 mcpServers，兼容 Claude Code 配置迁移",
    },
    {
        "id": "deveco-code",
        "name": "DevEco Code (华为)",
        "group": "国产",
        "config_type": "opencode",
        "global_paths": [HOME / ".deveco-code" / "config.json"],
        "project_paths": ["deveco.jsonc"],
        "mcp_key": "mcp",
        "hint": "基于 OpenCode，鸿蒙开发专属 AI Agent",
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "group": "国际",
        "config_type": "opencode",
        "global_paths": [
            HOME / ".config" / "opencode" / "opencode.json"
        ],
        "project_paths": ["opencode.json"],
        "mcp_key": "mcp",  # ← "mcp" not "mcpServers"
        "hint": "⚠ 格式不同：mcp key + 数组命令 + type:local",
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".vscode" / "mcp.json"],
        "project_paths": [".vscode/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "VS Code Copilot 的 MCP 配置",
    },
    {
        "id": "augment",
        "name": "Augment",
        "group": "国际",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".augment" / "mcp.json"],
        "project_paths": ["augment/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "开源 AI 编程助手",
    },
    # ── 国产 ──
    {
        "id": "lingma",
        "name": "通义灵码 / Qoder CN",
        "group": "国产",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".lingma" / "mcp-settings.json"],
        "project_paths": [".lingma/mcp-settings.json"],
        "mcp_key": "mcpServers",
        "hint": "阿里出品，魔搭 MCP 广场 3000+ 工具",
    },
    {
        "id": "trae",
        "name": "Trae (字节跳动)",
        "group": "国产",
        "config_type": "json_mcpServers",
        "global_paths": [HOME / ".trae" / "mcp.json"],
        "project_paths": [".trae/mcp.json"],
        "mcp_key": "mcpServers",
        "hint": "字节免费 IDE，600万+ 开发者",
    },
    {
        "id": "codegeex",
        "name": "CodeGeeX (智谱)",
        "group": "国产",
        "config_type": "vscode_settings",
        "global_paths": [],
        "project_paths": [".vscode/settings.json"],
        "mcp_key": "codegeex.mcpServers",
        "hint": "智谱开源免费编程助手",
    },
    {
        "id": "fitten",
        "name": "Fitten Code (非十科技)",
        "group": "国产",
        "config_type": "manual_only",
        "global_paths": [],
        "project_paths": [],
        "mcp_key": None,
        "hint": "⚠ 只能通过 UI 界面手动添加，无配置文件",
    },
    {
        "id": "decode",
        "name": "Decode / 豆包 MarsCode",
        "group": "国产",
        "config_type": "manual_only",
        "global_paths": [],
        "project_paths": [],
        "mcp_key": None,
        "hint": "⚠ 通过 MCP 市场或 UI 手动添加",
    },
]


# ── Detection ──────────────────────────────────────────────────────────
def detect_python():
    """Find a usable Python with mcp installed. Return (path, version_str)."""
    candidates = [sys.executable]

    if IS_WIN:
        for base in [HOME / "AppData" / "Local" / "Programs" / "Python",
                      Path("C:/Program Files/Python"),
                      Path("C:/Program Files (x86)/Python"),
                      HOME / "miniconda3",
                      HOME / "anaconda3",
                      HOME / ".conda"]:
            if base.exists():
                for py in sorted(base.rglob("python*.exe")):
                    if py not in candidates:
                        candidates.append(py)
        # Scan PATH for python
        for p in os.environ.get("PATH", "").split(os.pathsep):
            p = p.strip().strip('"')
            for pattern in ["python.exe", "python3.exe"]:
                exe = Path(p) / pattern
                if exe.exists() and exe not in candidates:
                    candidates.append(exe)
    else:
        for p in ["/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"]:
            if Path(p).exists():
                candidates.append(Path(p))

    for py in candidates:
        try:
            r = subprocess.run([str(py), "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "Python 3" in r.stdout:
                ver = r.stdout.strip()
                # Check mcp
                r2 = subprocess.run([str(py), "-c", "import mcp"], capture_output=True, text=True, timeout=10)
                if r2.returncode == 0:
                    return str(py), ver, True  # has mcp
                else:
                    return str(py), ver, False  # has python, no mcp
        except Exception:
            continue

    return None, None, None


def detect_installed_agents():
    """Scan filesystem for installed agents."""
    found = set()
    for agent in AGENTS:
        for path in agent["global_paths"]:
            if path.exists():
                found.add(agent["id"])
                break
        # Also check if project path exists in CWD
        for rel_path in agent["project_paths"]:
            if Path.cwd().joinpath(rel_path).exists():
                found.add(agent["id"])
                break
        # Heuristic: check executable
        if agent["id"] == "cursor":
            if IS_WIN:
                cursor_dirs = [HOME / "AppData" / "Local" / "Programs" / "cursor",
                               HOME / "AppData" / "Local" / "cursor"]
                for d in cursor_dirs:
                    if list(d.glob("Cursor*.exe")) or (d / "Cursor.exe").exists():
                        found.add("cursor")
                        break
            elif IS_MAC:
                if Path("/Applications/Cursor.app").exists():
                    found.add("cursor")
        if agent["id"] == "cline":
            # VS Code extension — check extensions dir
            if IS_WIN:
                vscode_ext = HOME / ".vscode" / "extensions"
            elif IS_MAC:
                vscode_ext = HOME / ".vscode" / "extensions"
            else:
                vscode_ext = HOME / ".vscode" / "extensions"
            if vscode_ext.exists():
                for d in vscode_ext.iterdir():
                    if d.name.startswith("saoudrizwan.claude-dev") or d.name.startswith("cline"):
                        found.add("cline")
                        break
        if agent["id"] == "trae":
            if IS_WIN:
                trae_dirs = [HOME / "AppData" / "Local" / "Programs" / "Trae"]
                for d in trae_dirs:
                    if d.exists():
                        found.add("trae")
                        break
            elif IS_MAC:
                if Path("/Applications/Trae.app").exists():
                    found.add("trae")
        if agent["id"] == "windsurf":
            if IS_WIN:
                ws = HOME / "AppData" / "Local" / "Programs" / "Windsurf"
                if ws.exists():
                    found.add("windsurf")
            elif IS_MAC:
                if Path("/Applications/Windsurf.app").exists():
                    found.add("windsurf")
        if agent["id"] == "mimo-code":
            # Check npm global install
            for npm_base in [HOME / "AppData" / "Roaming" / "npm",
                             Path("/usr/local/lib/node_modules"),
                             HOME / ".npm" / "global"]:
                if npm_base.exists() and list(npm_base.glob("mimo-code*")):
                    found.add("mimo-code")
                    break
        if agent["id"] == "deveco-code":
            if IS_WIN:
                deveco_base = Path("C:/Program Files/Huawei/DevEco Studio")
                if deveco_base.exists():
                    found.add("deveco-code")
            elif IS_MAC:
                if Path("/Applications/DevEco-Studio.app").exists():
                    found.add("deveco-code")

    return found


# ── Config generators (per agent format) ──────────────────────────────

def _raw_mcp_config(python_path: str, server_path: str) -> dict:
    """Standard mcpServers entry used by most agents."""
    return {
        "command": python_path,
        "args": [server_path],
    }


def gen_config_json_mcpServers(python_path: str, server_path: str) -> dict:
    return {"mcpServers": {"synapse-core": _raw_mcp_config(python_path, server_path)}}


def gen_config_opencode(python_path: str, server_path: str) -> dict:
    return {
        "mcp": {
            "synapse-core": {
                "type": "local",
                "command": [python_path, server_path],
                "environment": {},
            }
        }
    }


def gen_config_toml_codex(python_path: str, server_path: str) -> str:
    return (
        "# Synapse Core MCP — AI permanent memory\n"
        "[[mcp_servers]]\n"
        f'name = "synapse-core"\n'
        f'command = "{python_path}"\n'
        f'args = ["{server_path}"]\n'
    )


def gen_config_mimo_code(python_path: str, server_path: str) -> dict:
    """MiMo Code uses array-based mcpServers, not object."""
    return {
        "mcpServers": [
            {
                "name": "synapse-core",
                "command": python_path,
                "args": [server_path],
                "enabled": True,
            }
        ]
    }


def gen_config_vscode_settings(mcp_key: str, python_path: str, server_path: str) -> dict:
    return {mcp_key: {"synapse-core": _raw_mcp_config(python_path, server_path)}}


def gen_manual_instructions(agent_name: str) -> str:
    return (
        f"\n  {color('yellow', t('manual_guide_title', agent_name))}\n\n"
        f"  {t('manual_step1', agent_name)}\n"
        f"  {t('manual_step2')}\n"
        f"  {t('manual_step3', color('green', sys.executable))}\n"
        f"  {t('manual_step4', color('green', str(MCP_SERVER_PATH)))}\n"
        f"  {t('manual_step5', agent_name)}\n"
    )


# ── File writers ───────────────────────────────────────────────────────

def read_json_safe(path: Path) -> dict:
    """Read JSON safely, return {} on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json_safe(path: Path, data: dict):
    """Write JSON with pretty print, create dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_mcp_json(existing: dict, new_mcp: dict, mcp_key: str = "mcpServers") -> dict:
    """Merge new MCP servers into existing config, preserving existing entries."""
    if mcp_key not in existing:
        existing[mcp_key] = {}
    existing[mcp_key].update(new_mcp.get(mcp_key, new_mcp.get("mcp", {})))
    return existing


def write_global_config(agent: dict, python_path: str, server_path: str):
    """Write MCP config to global path."""
    target = agent["global_paths"][0]
    config_type = agent["config_type"]
    mcp_key = agent.get("mcp_key", "mcpServers")

    if config_type == "json_mcpServers":
        existing = read_json_safe(target)
        new_cfg = gen_config_json_mcpServers(python_path, server_path)
        merged = merge_mcp_json(existing, new_cfg, mcp_key)
        write_json_safe(target, merged)
        ok(t("write_ok", target))

    elif config_type == "opencode":
        existing = read_json_safe(target)
        new_cfg = gen_config_opencode(python_path, server_path)
        merged = merge_mcp_json(existing, new_cfg, "mcp")
        write_json_safe(target, merged)
        ok(t("write_ok_opencode", target))

    elif config_type == "mimo_code":
        existing = read_json_safe(target)
        existing_servers = existing.get("mcpServers", [])
        if not isinstance(existing_servers, list):
            existing_servers = []
        new_servers = gen_config_mimo_code(python_path, server_path)["mcpServers"]
        existing_names = {s.get("name") for s in existing_servers}
        for s in new_servers:
            if s["name"] not in existing_names:
                existing_servers.append(s)
        existing["mcpServers"] = existing_servers
        write_json_safe(target, existing)
        ok(t("write_ok_mimo", target))

    elif config_type == "toml":
        toml_snippet = gen_config_toml_codex(python_path, server_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if "synapse-core" in existing:
                warn(t("write_exists", target))
                return
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n" + toml_snippet)
        else:
            target.write_text(toml_snippet, encoding="utf-8")
        ok(t("write_ok_toml", target))

    elif config_type == "vscode_settings":
        existing = read_json_safe(target)
        new_cfg = gen_config_vscode_settings(mcp_key, python_path, server_path)
        existing.update(new_cfg)
        write_json_safe(target, existing)
        ok(t("write_ok_vscode", target, mcp_key))

    elif config_type == "manual_only":
        info(t("write_skip_manual", agent["name"]))


def write_project_config(agent: dict, python_path: str, server_path: str, project_root: Path):
    """Write MCP config to project path."""
    config_type = agent["config_type"]
    mcp_key = agent.get("mcp_key", "mcpServers")

    for rel_path in agent.get("project_paths", []):
        target = project_root / rel_path

        if config_type == "json_mcpServers":
            existing = read_json_safe(target)
            new_cfg = gen_config_json_mcpServers(python_path, server_path)
            merged = merge_mcp_json(existing, new_cfg, mcp_key)
            write_json_safe(target, merged)
            ok(t("write_ok", target))

        elif config_type == "opencode":
            existing = read_json_safe(target)
            new_cfg = gen_config_opencode(python_path, server_path)
            merged = merge_mcp_json(existing, new_cfg, "mcp")
            write_json_safe(target, merged)
            ok(t("write_ok_opencode", target))

        elif config_type == "mimo_code":
            existing = read_json_safe(target)
            existing_servers = existing.get("mcpServers", [])
            if not isinstance(existing_servers, list):
                existing_servers = []
            new_servers = gen_config_mimo_code(python_path, server_path)["mcpServers"]
            existing_names = {s.get("name") for s in existing_servers}
            for s in new_servers:
                if s["name"] not in existing_names:
                    existing_servers.append(s)
            existing["mcpServers"] = existing_servers
            write_json_safe(target, existing)
            ok(t("write_ok_mimo", target))

        elif config_type == "toml":
            toml_snippet = gen_config_toml_codex(python_path, server_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if "synapse-core" in existing:
                    warn(t("write_exists", target))
                    return
                with open(target, "a", encoding="utf-8") as f:
                    f.write("\n" + toml_snippet)
            else:
                target.write_text(toml_snippet, encoding="utf-8")
            ok(t("write_ok_toml", target))

        elif config_type == "vscode_settings":
            existing = read_json_safe(target)
            new_cfg = gen_config_vscode_settings(mcp_key, python_path, server_path)
            existing.update(new_cfg)
            write_json_safe(target, existing)
            ok(t("write_ok_vscode", target, mcp_key))

        elif config_type == "manual_only":
            info(f"跳过 {agent['name']} — 需手动配置")


# ── Validation ─────────────────────────────────────────────────────────
def validate_install(python_path: str):
    """Try importing the MCP server as a basic sanity check."""
    try:
        r = subprocess.run(
            [python_path, "-c", f"import importlib.util; spec=importlib.util.spec_from_file_location('x', r'{MCP_SERVER_PATH}'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print('OK')"],
            capture_output=True, text=True, timeout=15,
            cwd=str(SYNAPSE_DIR),
        )
        return r.returncode == 0 and "OK" in r.stdout
    except Exception as e:
        fail(t("validate_fail_") + f": {e}")
        return False


# ── Multi-select UI ────────────────────────────────────────────────────
def multi_select_agents(installed: set) -> list:
    """Interactive multi-select from AGENTS list. Returns selected agent dicts."""
    print(f"\n{color('bold', "选择要安装的 Agent（输入序号，空格分隔，a=全选，回车确认）:")}")
    print(f"  {color('dim', "已检测到的 Agent 已标记 [*]")}\n")

    for i, agent in enumerate(AGENTS):
        num = f"{i+1:2d}"
        detected = agent["id"] in installed
        marker = color("green", "[*]") if detected else "[ ]"
        group_tag = color("yellow", f"[{agent['group']}]") if agent["group"] == "国产" else color("blue", f"[{agent['group']}]")
        name = agent["name"]
        hint_text = f"  {color('dim', agent['hint'])}" if agent.get("hint") else ""
        config_type_text = color("dim", f"  [{agent['config_type']}]")
        print(f"  {num}. {marker} {group_tag} {name}{config_type_text}{hint_text}")

    print(f"\n  {color('dim', t('select_default'))}")

    try:
        raw = input(f"\n  {color('bold', '>>>')} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n")
        return []

    selected = set()

    if raw == "":
        # Default: install detected agents
        for agent in AGENTS:
            if agent["id"] in installed:
                selected.add(agent["id"])
    elif raw.lower() == "a":
        for agent in AGENTS:
            selected.add(agent["id"])
    else:
        try:
            nums = [int(x.strip()) for x in raw.split() if x.strip().isdigit()]
            for n in nums:
                if 1 <= n <= len(AGENTS):
                    selected.add(AGENTS[n - 1]["id"])
        except ValueError:
            warn(t("select_invalid"))
            for agent in AGENTS:
                if agent["id"] in installed:
                    selected.add(agent["id"])

    result = [a for a in AGENTS if a["id"] in selected]
    return result


# ── I18n: Chinese / English ──────────────────────────────────────────────
I18N = {
    "banner_subtitle": {"zh": "开 发 向 导 安 装 程 序", "en": "D E V   W I Z A R D   I N S T A L L E R"},
    "banner_tagline": {"zh": "Your AI's permanent memory. One setup, 18 agents.\n", "en": "Your AI's permanent memory. One setup, 18 agents.\n"},
    "lang_ask": {"zh": "选择语言 / Select language (1=中文 2=English, 默认1) >>>", "en": "Select language (1=中文 2=English, default=1) >>>"},
    "lang_set": {"zh": "已选择: 中文", "en": "Selected: English"},
    "cover_found": {"zh": "封面图: {}", "en": "Cover image: {}"},
    "cover_missing": {"zh": "未找到封面图，跳过", "en": "Cover image not found, skipping"},

    "step1": {"zh": "Step 1/5 — 环境检查", "en": "Step 1/5 — Environment Check"},
    "step2": {"zh": "Step 2/5 — 检测已安装的 Agent", "en": "Step 2/5 — Detecting Installed Agents"},
    "step3": {"zh": "Step 3/5 — 选择目标 Agent", "en": "Step 3/5 — Select Target Agents"},
    "step4": {"zh": "Step 4/5 — Python 路径确认", "en": "Step 4/5 — Confirm Python Path"},
    "step5": {"zh": "Step 5/5 — 写入 MCP 配置", "en": "Step 5/5 — Write MCP Configs"},
    "validate": {"zh": "验证安装", "en": "Validate Install"},

    "py_version_ok": {"zh": "Python {}.{}.{}", "en": "Python {}.{}.{}"},
    "py_version_fail": {"zh": "Python {}.{} — 需要 >= 3.10", "en": "Python {}.{} — need >= 3.10"},
    "py_found": {"zh": "检测到 Python: {}", "en": "Detected Python: {}"},
    "py_ver_info": {"zh": "版本: {}", "en": "Version: {}"},
    "py_not_found": {"zh": "未找到可用的 Python 解释器", "en": "No usable Python interpreter found"},
    "mcp_missing": {"zh": "未安装 mcp 模块，尝试安装...", "en": "mcp not installed, trying to install..."},
    "mcp_ok": {"zh": "mcp 安装成功", "en": "mcp installed successfully"},
    "mcp_fail": {"zh": "mcp 安装失败:\n", "en": "mcp install failed:\n"},
    "mcp_manual": {"zh": "请手动运行: {}", "en": "Please run manually: {}"},
    "mcp_error": {"zh": "安装 mcp 出错: {}", "en": "Error installing mcp: {}"},
    "server_missing": {"zh": "MCP Server 文件不存在: {}", "en": "MCP Server file not found: {}"},
    "server_ok": {"zh": "MCP Server: {}", "en": "MCP Server: {}"},

    "detected": {"zh": "检测到 {}", "en": "Detected {}"},
    "no_agent_found": {"zh": "未自动检测到 Agent（将展示全部选项）", "en": "No agents auto-detected (showing all options)"},

    "select_prompt": {"zh": "选择要安装的 Agent（输入序号，空格分隔，a=全选，回车确认）:", "en": "Select agents to install (enter numbers, space separated, a=all, Enter=confirm):"},
    "select_hint": {"zh": "已检测到的 Agent 已标记 [*]", "en": "Auto-detected agents marked with [*]"},
    "select_invalid": {"zh": "无效输入，使用默认（检测到的 Agent）", "en": "Invalid input, using defaults (detected agents)"},
    "select_default": {"zh": "直接回车 = 只装检测到的 Agent", "en": "Enter = install detected agents only"},

    "selected_none": {"zh": "未选择任何 Agent，退出。", "en": "No agents selected, exiting."},
    "selected_count": {"zh": "已选择 {} 个 Agent:", "en": "{} agents selected:"},

    "current_py": {"zh": "当前 Python: {}", "en": "Current Python: {}"},
    "py_hint1": {"zh": "绝对路径可确保 IDE 中的 Agent 能找到 Python", "en": "Absolute path ensures IDE agents can find Python"},
    "py_hint2": {"zh": "直接回车 = 使用当前路径", "en": "Enter = use current path"},
    "py_prompt": {"zh": "Python 路径 >>>", "en": "Python path >>>"},
    "py_ok": {"zh": "使用: {}", "en": "Using: {}"},
    "py_no_mcp": {"zh": "该 Python 未安装 mcp，尝试安装...", "en": "Python has no mcp, trying to install..."},
    "py_invalid": {"zh": "不是有效的 Python 3，使用默认路径", "en": "Not a valid Python 3, using default"},
    "py_path_invalid": {"zh": "路径无效，使用默认路径", "en": "Invalid path, using default"},

    "install_mode": {"zh": "安装模式:", "en": "Install mode:"},
    "mode_option1": {"zh": "1. 全局安装 (推荐) — 所有项目都能用", "en": "1. Global install (recommended) — all projects"},
    "mode_option2": {"zh": "2. 当前目录安装 — 仅当前项目", "en": "2. Project install — current project only"},
    "mode_option3": {"zh": "3. 两者都装", "en": "3. Both"},
    "mode_prompt": {"zh": "选择 (1/2/3, 默认1) >>>", "en": "Choose (1/2/3, default=1) >>>"},

    "write_ok": {"zh": "写入 {}", "en": "Wrote {}"},
    "write_ok_opencode": {"zh": "写入 {} (OpenCode 格式)", "en": "Wrote {} (OpenCode format)"},
    "write_ok_mimo": {"zh": "写入 {} (MiMo Code 数组格式)", "en": "Wrote {} (MiMo Code array format)"},
    "write_ok_toml": {"zh": "写入 {} (TOML 格式)", "en": "Wrote {} (TOML format)"},
    "write_ok_vscode": {"zh": "写入 {} (key: {})", "en": "Wrote {} (key: {})"},
    "write_skip_manual": {"zh": "跳过 {} — 需手动配置（无文件路径）", "en": "Skipping {} — manual config required"},
    "write_exists": {"zh": "已存在 synapse-core 配置，跳过 {}", "en": "synapse-core already configured, skipping {}"},
    "write_fail_global": {"zh": "全局配置写入失败: {}", "en": "Global config write failed: {}"},
    "write_fail_project": {"zh": "项目配置写入失败: {}", "en": "Project config write failed: {}"},
    "write_no_path": {"zh": "无已知配置路径，跳过", "en": "No known config path, skipping"},
    "write_cant_auto": {"zh": "无法自动配置 — {}", "en": "Cannot auto-configure — {}"},

    "validate_ok": {"zh": "MCP Server 加载成功！", "en": "MCP Server loaded successfully!"},
    "validate_fail": {"zh": "MCP Server 加载有问题，请手动检查", "en": "MCP Server load failed, please check manually"},

    "manual_header": {"zh": "以下 Agent 需要手动配置：", "en": "The following agents require manual configuration:"},

    "done_title": {"zh": "✅ 安装完成！", "en": "✅ Installation Complete!"},
    "done_next": {"zh": "下一步：", "en": "Next steps:"},
    "done_restart": {"zh": "• 重启你的 AI Agent", "en": "• Restart your AI agent"},
    "done_try1": {"zh": "• 尝试输入: \"帮我记住我喜欢吃什么\"", "en": "• Try saying: \"Remember that I like pizza\""},
    "done_try2": {"zh": "• 下次打开对话: \"我喜欢吃什么？\"", "en": "• Next session: \"What food do I like?\""},
    "done_try3": {"zh": "• AI 应该能记住并回答了 🎉", "en": "• Your AI should remember and answer 🎉"},
    "done_star": {"zh": "⭐ 如果觉得有用，GitHub 上给个 Star:", "en": "⭐ If you find this useful, drop a star on GitHub:"},

    "manual_guide_title": {"zh": "━━━ {} 手动配置指南 ━━━", "en": "━━━ {} Manual Setup Guide ━━━"},
    "manual_step1": {"zh": "1. 打开 {} 的 设置/偏好 → MCP 服务", "en": "1. Open {} Settings/Preferences → MCP Services"},
    "manual_step2": {"zh": "2. 添加 MCP Server，名称填: synapse-core", "en": "2. Add MCP Server, name: synapse-core"},
    "manual_step3": {"zh": "3. 命令填: {}", "en": "3. Command: {}"},
    "manual_step4": {"zh": "4. 参数填: {}", "en": "4. Args: {}"},
    "manual_step5": {"zh": "5. 保存后重启 {}", "en": "5. Save and restart {}"},
}

_LANG = "zh"  # default

def t(key, *args):
    """Get translated string, with optional format args."""
    entry = I18N.get(key, {})
    text = entry.get(_LANG, key)
    if args:
        text = text.format(*args)
    return text
def main():
    print("\n" + "=" * 66)
    print(color("cyan", """
   ░██████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗
   ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝
   ╚█████╗  ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗
    ╚═══██╗  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝
   ██████╔╝   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗
   ╚═════╝    ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝
"""))
    print(color("bold", "         C O R E   ·   " + t("banner_subtitle")))
    print(color("dim", "         " + t("banner_tagline")))
    print("=" * 66)

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
    print(f"  {color('green', t('lang_set'))}")

    if COVER_PATH.exists():
        info(t("cover_found", COVER_PATH.name))
    else:
        warn(t("cover_missing"))

    # ── Step 1: Check env ──────────────────────────────────────────────
    section(t("step1"))

    py_ver = sys.version_info
    if py_ver >= (3, 10):
        ok(t("py_version_ok", py_ver.major, py_ver.minor, py_ver.micro))
    else:
        fail(t("py_version_fail", py_ver.major, py_ver.minor))
        sys.exit(1)

    # Detect Python with mcp
    py_path, py_ver_str, has_mcp = detect_python()
    if not py_path:
        fail(t("py_not_found"))
        sys.exit(1)

    ok(t("py_found", color('green', py_path)))
    info(t("py_ver_info", py_ver_str))

    if not has_mcp:
        warn(t("mcp_missing"))
        try:
            r = subprocess.run([py_path, "-m", "pip", "install", "mcp"],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                ok(t("mcp_ok"))
            else:
                fail(t("mcp_fail") + r.stderr[-500:])
                print(f"\n  {t('mcp_manual', color('green', py_path + ' -m pip install mcp'))}")
                sys.exit(1)
        except Exception as e:
            fail(t("mcp_error", e))
            sys.exit(1)

    if not MCP_SERVER_PATH.exists():
        fail(t("server_missing", MCP_SERVER_PATH))
        sys.exit(1)
    ok(t("server_ok", MCP_SERVER_PATH.name))

    # ── Step 2: Detect agents ──────────────────────────────────────────
    section(t("step2"))

    installed = detect_installed_agents()
    if installed:
        for agent in AGENTS:
            if agent["id"] in installed:
                ok(t("detected", agent["name"]))
    else:
        info(t("no_agent_found"))

    # ── Step 3: Select agents ──────────────────────────────────────────
    section(t("step3"))

    selected = multi_select_agents(installed)

    if not selected:
        print(f"\n{color('yellow', t('selected_none'))}")
        sys.exit(0)

    print(f"\n  {t('selected_count', color('green', str(len(selected))))}")
    for agent in selected:
        print(f"    • {agent['name']} {color('dim', f'({agent['group']})')}")

    # ── Step 4: Python path confirm ────────────────────────────────────
    section(t("step4"))

    print(f"  {t('current_py', color('green', py_path))}")
    print(f"  {color('dim', t('py_hint1'))}")
    print(f"  {color('dim', t('py_hint2'))}")

    try:
        new_path = input(f"\n  {color('bold', t('py_prompt'))} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n")
        sys.exit(0)

    if new_path:
        # Verify
        try:
            r = subprocess.run([new_path, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "Python 3" in r.stdout:
                py_path = new_path
                ok(t("py_ok", py_path))
                # Check mcp on new path
                r2 = subprocess.run([py_path, "-c", "import mcp"], capture_output=True, text=True, timeout=10)
                if r2.returncode != 0:
                    warn(t("py_no_mcp"))
                    subprocess.run([py_path, "-m", "pip", "install", "mcp"], timeout=60)
            else:
                fail(t("py_invalid"))
        except Exception:
            fail(t("py_path_invalid"))

    server_path = str(MCP_SERVER_PATH.resolve())

    # ── Install mode ───────────────────────────────────────────────────
    print(f"\n  {color('dim', t('install_mode'))}")
    print(f"    {t("mode_option1")}")
    print(f"    {t("mode_option2")}")
    print(f"    {t("mode_option3")}")

    try:
        mode = input(f"\n  {color('bold', t('mode_prompt'))} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n")
        sys.exit(0)

    do_global = mode in ("", "1", "3")
    do_project = mode in ("2", "3")

    # ── Step 5: Write configs ──────────────────────────────────────────
    section(t("step5"))

    manual_agents = []

    for agent in selected:
        print(f"\n  {color('bold', agent['name'])} {color('dim', f'({agent['group']})')}")

        if agent["config_type"] == "manual_only":
            manual_agents.append(agent)
            warn(t("write_cant_auto", agent["hint"]))
            continue

        if do_global and agent["global_paths"]:
            try:
                write_global_config(agent, py_path, server_path)
            except Exception as e:
                fail(t("write_fail_global", e))

        if do_project and agent["project_paths"]:
            try:
                write_project_config(agent, py_path, server_path, Path.cwd())
            except Exception as e:
                fail(t("write_fail_project", e))

        if not agent["global_paths"] and not agent["project_paths"]:
            warn(t("write_no_path"))

    # ── Validate ───────────────────────────────────────────────────────
    section(t("validate"))
    if validate_install(py_path):
        ok(t("validate_ok"))
    else:
        warn(t("validate_fail"))

    # ── Manual instructions ────────────────────────────────────────────
    if manual_agents:
        print(f"\n{color('yellow', '━' * 60)}")
        print(color('yellow', t('manual_header')))
        for agent in manual_agents:
            print(gen_manual_instructions(agent["name"]))

    # ── Done ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 66}")
    print(color("green", f"""
   {t('done_title')}

   {t('done_next')}
   {t('done_restart')}
   {t('done_try1')}
   {t('done_try2')}
   {t('done_try3')}

   {t('done_star')}
   https://github.com/zhen85988-chen/synapse-core
"""))
    print("=" * 66 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{color('dim', '已取消')}\n")
        sys.exit(0)
