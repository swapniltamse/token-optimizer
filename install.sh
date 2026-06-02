#!/usr/bin/env bash
# token-optimizer install script for Mac/Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/swapniltamse/token-optimizer/main/install.sh | bash
set -euo pipefail

REPO="swapniltamse/token-optimizer"
BRANCH="main"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILL_DIR="$CLAUDE_DIR/skills/token-optimizer"
LOG_DIR="$CLAUDE_DIR/token-optimizer"
SETTINGS="$CLAUDE_DIR/settings.json"

echo ""
echo "Installing token-optimizer..."
echo ""

# ── 1. Download skill files ───────────────────────────────────────────────
mkdir -p "$SKILL_DIR/hooks" "$SKILL_DIR/config"

for file in SKILL.md hooks/token_guard.py config/patterns.yaml; do
    curl -fsSL "$RAW/$file" -o "$SKILL_DIR/$file"
    echo "  Downloaded $file"
done

# ── 2. Check Python 3 ────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "ERROR: Python 3 is required but was not found."
    echo "Install it from https://python.org or via your package manager, then re-run this script."
    exit 1
fi
echo "  Python 3: $(python3 --version)"

# ── 3. Install PyYAML ────────────────────────────────────────────────────
if python3 -c "import yaml" 2>/dev/null; then
    echo "  PyYAML: already installed"
else
    echo "  Installing PyYAML..."
    python3 -m pip install pyyaml --quiet
    echo "  PyYAML: installed"
fi

# ── 4. Merge hook into settings.json (idempotent) ────────────────────────
mkdir -p "$CLAUDE_DIR"
HOOK_CMD="python3 $SKILL_DIR/hooks/token_guard.py"

python3 - <<PYEOF
import json, os, sys

path = "$SETTINGS"
try:
    with open(path) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

entry = {
    "matcher": "Bash|Write|Read",
    "hooks": [{"type": "command", "command": "$HOOK_CMD"}]
}

hooks = cfg.setdefault("hooks", {})
pre   = hooks.setdefault("PreToolUse", [])

if any("token_guard.py" in str(h) for h in pre):
    print("  Hook: already registered in settings.json")
else:
    pre.append(entry)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print("  Hook: registered in settings.json")
PYEOF

# ── 5. Create log directory ───────────────────────────────────────────────
mkdir -p "$LOG_DIR"
echo "  Log dir: $LOG_DIR"

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "token-optimizer installed."
echo ""
echo "Next steps:"
echo "  1. Restart Claude Code (the hook loads at startup)"
echo "  2. Run /token-optimizer in Claude Code to get started"
echo "  3. Check your savings: python3 $SKILL_DIR/hooks/token_guard.py report"
echo ""
