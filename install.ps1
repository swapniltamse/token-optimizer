# token-optimizer install script for Windows PowerShell 5.1
# Usage: irm https://raw.githubusercontent.com/swapniltamse/token-optimizer/main/install.ps1 | iex
#
# Requires: Python 3, Claude Code
# PyYAML is installed automatically if missing.
$ErrorActionPreference = "Stop"

$Repo     = "swapniltamse/token-optimizer"
$Branch   = "main"
$RawBase  = "https://raw.githubusercontent.com/$Repo/$Branch"

$ClaudeDir   = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { "$env:USERPROFILE\.claude" }
$SkillDir    = "$ClaudeDir\skills\token-optimizer"
$LogDir      = "$ClaudeDir\token-optimizer"
$SettingsPath = "$ClaudeDir\settings.json"

Write-Host ""
Write-Host "Installing token-optimizer..."
Write-Host ""

# ── 1. Download skill files ───────────────────────────────────────────────
$Files = @("SKILL.md", "hooks/token_guard.py", "config/patterns.yaml")
foreach ($File in $Files) {
    $Dest   = Join-Path $SkillDir $File
    $Parent = Split-Path $Dest -Parent
    if (-not (Test-Path $Parent)) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    Invoke-WebRequest -Uri "$RawBase/$File" -OutFile $Dest -UseBasicParsing
    Write-Host "  Downloaded $File"
}

# ── 2. Find Python ────────────────────────────────────────────────────────
$PythonCmd = $null
foreach ($Cmd in @("python", "python3", "py")) {
    if (Get-Command $Cmd -ErrorAction SilentlyContinue) { $PythonCmd = $Cmd; break }
}
if (-not $PythonCmd) {
    Write-Host ""
    Write-Host "ERROR: Python 3 is required but was not found."
    Write-Host "Install it from https://python.org then re-run this script."
    exit 1
}
Write-Host "  Python: $(& $PythonCmd --version)"

# ── 3. Install PyYAML ────────────────────────────────────────────────────
$YamlCheck = & $PythonCmd -c "import yaml; print('ok')" 2>$null
if ($YamlCheck -eq "ok") {
    Write-Host "  PyYAML: already installed"
} else {
    Write-Host "  Installing PyYAML..."
    & $PythonCmd -m pip install pyyaml --quiet
    Write-Host "  PyYAML: installed"
}

# ── 4. Merge hook into settings.json (idempotent) ────────────────────────
$SettingsDir = Split-Path $SettingsPath -Parent
if (-not (Test-Path $SettingsDir)) { New-Item -ItemType Directory -Path $SettingsDir -Force | Out-Null }

$HookCmd = "$PythonCmd `"$SkillDir\hooks\token_guard.py`""

# Use single-quoted here-string so PowerShell does not expand $ inside Python code
$PyScript = @'
import json, os, sys

settings_path = sys.argv[1]
hook_cmd      = sys.argv[2]

try:
    with open(settings_path) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

entry = {
    "matcher": "Bash|Write",
    "hooks": [{"type": "command", "command": hook_cmd}]
}

hooks = cfg.setdefault("hooks", {})
pre   = hooks.setdefault("PreToolUse", [])

if any("token_guard.py" in str(h) for h in pre):
    print("  Hook: already registered in settings.json")
else:
    pre.append(entry)
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(cfg, f, indent=2)
    print("  Hook: registered in settings.json")
'@

$TempScript = [System.IO.Path]::GetTempFileName() + ".py"
$PyScript | Out-File -FilePath $TempScript -Encoding utf8
& $PythonCmd $TempScript $SettingsPath $HookCmd
Remove-Item $TempScript -Force

# ── 5. Create log directory ───────────────────────────────────────────────
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
Write-Host "  Log dir: $LogDir"

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "token-optimizer installed."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart Claude Code (the hook loads at startup)"
Write-Host "  2. Run /token-optimizer in Claude Code to get started"
Write-Host "  3. Check your savings: $PythonCmd '$SkillDir\hooks\token_guard.py' report"
Write-Host ""
