#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo ""
echo "  Running Synapse Core Setup Wizard..."
echo ""
python3 "$DIR/setup_wizard.py"
