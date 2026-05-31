#!/usr/bin/env python3
# token_guard.py — PreToolUse hook + report command
# Hook: echo '<json>' | python token_guard.py
# Report: python token_guard.py report
import json, os, re, sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR  = Path(__file__).resolve().parent.parent
PATTERNS_FILE = SCRIPT_DIR / "config" / "patterns.yaml"
LOG_DIR     = Path.home() / ".claude" / "token-optimizer"
LOG_FILE    = LOG_DIR / "blocked.log"
THRESHOLD   = 1000
_COST_PER_TOKEN = (0.70 * 3.00 + 0.30 * 15.00) / 1_000_000  # Sonnet 4.6, 70/30 split
_CONTINUE   = json.dumps({"action": "continue"})


def load_patterns():
    try:
        import yaml
        with open(PATTERNS_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def avg_tokens(p):
    return (p.get("token_estimate_low", 0) + p.get("token_estimate_high", 0)) // 2


def match_pattern(command, data):
    if not data or not command:
        return None
    if command.strip().startswith("# token-optimizer: skip"):
        return None
    for p in data.get("patterns", []) + data.get("enterprise_patterns", []):
        for kw in p.get("bash_patterns", []):
            if re.search(kw, command.strip(), re.IGNORECASE | re.MULTILINE):
                return p
    return None


def build_message(p):
    avg = avg_tokens(p)
    cost = avg * _COST_PER_TOKEN
    lines = [
        "You already know this one.",
        f"\n  {p['manual_alternative']}",
        f"\n  {p.get('relatable_reason', '')}",
        f"  Saves ~${cost:.4f}  ({avg:,} tokens).",
    ]
    if p.get("hybrid_steps"):
        lines += ["\n  Or go hybrid (saves ~60-70%):"] + [f"    {s}" for s in p["hybrid_steps"]]
    lines += ["\n  To let Claude do it anyway:\n    # token-optimizer: skip\n    [your command here]"]
    return "\n".join(lines)


def log_blocked(p):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    avg = avg_tokens(p)
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"[{ts}] BLOCKED | pattern: {p['id']} | "
            f"est_tokens_saved: {avg:,} | est_cost_saved: ${avg * _COST_PER_TOKEN:.4f} | "
            f"name: {p['name']}\n"
        )


def run_report():
    if not LOG_FILE.exists():
        print(f"No blocked operations logged yet.\nLog: {LOG_FILE}"); return
    data = load_patterns()
    org  = (data or {}).get("team_config", {}).get("org_name", "")
    cutoff = datetime.now() - timedelta(days=7)
    total_tok, total_cost, counts = 0, 0.0, {}
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            if not m or datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") < cutoff:
                continue
            for pat, key, cast in [
                (r"est_tokens_saved: ([\d,]+)", "tok", lambda v: int(v.replace(",", ""))),
                (r"est_cost_saved: \$([\d.]+)",  "cost", float),
                (r"pattern: ([\w-]+)",            "pid",  str),
            ]:
                mm = re.search(pat, line)
                if mm:
                    if key == "tok":  total_tok  += cast(mm.group(1))
                    elif key == "cost": total_cost += cast(mm.group(1))
                    else: counts[mm.group(1)] = counts.get(mm.group(1), 0) + 1
    top  = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    n    = sum(counts.values())
    sep  = "=" * 60
    hdr  = f"token-optimizer weekly report{f'  [{org}]' if org else ''}"
    print(f"\n{sep}\n{hdr}\n{sep}")
    print(f"Period:         last 7 days\nTokens saved:   {total_tok:,}\nEst. $ saved:   ${total_cost:.2f}\nOps blocked:    {n}\nTop pattern:    {top[0][0] if top else 'none'}")
    print(f"{sep}\n\n--- paste this anywhere ---")
    print(f"Saved {total_tok:,} tokens (${total_cost:.2f}) this week with token-optimizer. "
          f"Top pattern: {top[0][0] if top else 'none'}. {n} ops blocked. "
          f"github.com/swapniltamse/token-optimizer")
    print("---\n")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        run_report(); return
    if os.environ.get("TOKEN_OPTIMIZER_DISABLED") == "1":
        print(_CONTINUE); return
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        print(_CONTINUE); return

    tool_name  = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    if tool_name not in ("Bash", "Write"):
        print(_CONTINUE); return

    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    data    = load_patterns()
    matched = match_pattern(command, data)

    if matched:
        cfg       = (data or {})
        threshold = cfg.get("settings", {}).get("block_threshold_tokens", THRESHOLD)
        required  = set(cfg.get("team_config", {}).get("required_patterns", []))
        if avg_tokens(matched) >= threshold or matched.get("id") in required:
            log_blocked(matched)
            print(json.dumps({"action": "block", "message": build_message(matched)}))
            return

    print(_CONTINUE)


if __name__ == "__main__":
    main()
