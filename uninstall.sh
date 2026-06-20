#!/usr/bin/env bash
# Synapse Core — Uninstall
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "  Uninstalling Synapse Core MCP config..."
echo ""
python3 "$SCRIPT_DIR/uninstall.py"
