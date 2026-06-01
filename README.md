# token-optimizer

Companies are pausing Claude Code subscriptions. Token bills are climbing faster than the value delivered.

token-optimizer fixes the habit, not the tool.

---

## What it does

It catches the moment you ask Claude to do something you already know how to do yourself.

```
You: git commit

[Claude Code]
You already know this one.

  git commit -m "fix: describe what you changed"

  You were there. You know what changed.
  Saves ~$0.0330  (5,000 tokens).

  To let Claude do it anyway:
    # token-optimizer: skip
    git commit
```

That exchange took zero tokens. You got a reminder, not a bill.

Now picture that firing 10 times a day across a 10-person team.

---

## The math

| Operation | What Claude does | Avg tokens | Cost |
|-----------|-----------------|-----------|------|
| Write a commit message | Reads working dir, runs git diff, generates text | 5,000 | ~$0.033 |
| Summarize git diff | Reads entire diff into context | 3,000 | ~$0.020 |
| Find all references to a function | Runs grep -r across repo | 1,250 | ~$0.008 |
| Generate SQL from scratch | Invents schema from scratch when you know it | 3,750 | ~$0.025 |

None of these need Claude. Each takes under 10 seconds to do yourself.

---

## How it works

Two layers, one job.

```
You describe a task
        |
    SKILL.md          <- you invoke with /token-optimizer
    Checks your intent against the pattern library
    Returns: MANUAL / HYBRID / AGENTIC
        |
        | (if AGENTIC, Claude starts working)
        v
    token_guard.py    <- fires automatically on every Bash/Write call
    Matches the command against bash_patterns in patterns.yaml
    Blocks if matched + above token threshold
        |
        v
    blocked.log       <- every blocked op logged with timestamp + $ saved
        |
        v
    token-optimizer report  <- weekly summary, paste-ready for sharing
```

The skill catches waste before it starts. The hook catches it even when you forget to invoke the skill.

---

## What it catches

| Pattern | You say to Claude | Claude was about to | Manual alternative | Avg tokens |
|---------|------------------|--------------------|--------------------|-----------|
| git-commit | "write a commit message" | Read your whole working dir | `git commit -m "..."` | 5,000 |
| git-diff | "show me the diff" | Read the entire diff | `git diff --stat` | 3,000 |
| git-log | "recent commits" | Run verbose git log | `git log --oneline -10` | 2,000 |
| variable-rename | "rename this variable" | Read 12 files | F2 in VS Code | 2,900 |
| find-usages | "find references to" | Run grep -r | IDE Find References | 1,250 |
| sql-from-scratch | "write me a SQL query" | Guess your schema | Write rough SELECT, Claude optimizes | 3,750 |
| organize-imports | "clean up imports" | Read every import | Shift+Alt+O in VS Code | 1,250 |
| simple-find-replace | "replace X with Y in this file" | Read the file, run sed | Ctrl+H in your IDE | 1,200 |
| git-status | "what files changed" | Run git status, parse output | `git status` | 550* |
| list-directory | "list files in this folder" | Run ls, read directory | `ls` or file explorer | 400* |

The full pattern library is in `config/patterns.yaml`. All 10 patterns are documented with the relatable reason each one was added. *Patterns marked with an asterisk are below the default 1,000-token block threshold — they are logged but not blocked unless you lower `block_threshold_tokens` in settings.

---

## Install

**Mac/Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/swapniltamse/token-optimizer/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/swapniltamse/token-optimizer/main/install.ps1 | iex
```

Requires Python 3. PyYAML is installed automatically.

The installer downloads the skill files to `~/.claude/skills/token-optimizer/`, registers the PreToolUse hook in `~/.claude/settings.json`, and creates the log directory. It merges your existing settings — nothing is overwritten.

Then restart Claude Code.

Your pattern library is at `~/.claude/skills/token-optimizer/config/patterns.yaml`. Open it on day one to verify the rules or adjust the blocking threshold before your first session.

---

## Usage

**Evaluate a task before starting:**
```
/token-optimizer write a commit message for my changes
```

**Review what was missed in this session:**
```
/token-optimizer audit
```

**View active patterns:**
```
/token-optimizer config
```

**Weekly savings report:**
```bash
python3 ~/.claude/skills/token-optimizer/hooks/token_guard.py report
```

---

## Configure

**Adjust the blocking threshold** (tokens, based on avg of low/high estimate):

In `config/patterns.yaml`:
```yaml
settings:
  block_threshold_tokens: 1000   # raise to 2000 for lighter touch
```

**Add a team pattern:**

```yaml
enterprise_patterns:
  - id: check-deploy
    name: Check deployment status
    skill_keywords: [check deploy, is it deployed]
    bash_patterns: ["^kubectl get pods", "^heroku releases"]
    manual_alternative: "Open your deployment dashboard"
    relatable_reason: "The dashboard shows this in real time."
    token_estimate_low: 500
    token_estimate_high: 2000
```

**Override for one command** (bypass prefix):
```bash
# token-optimizer: skip
git commit
```

**Disable completely** (CI/CD pipelines):
```bash
TOKEN_OPTIMIZER_DISABLED=1 claude
```

**Push config to your whole team:**

Commit `config/patterns.yaml` to your shared dotfiles repo. Set `team_config.org_name` for branded reports. Use `team_config.required_patterns` to make specific patterns non-bypassable.

```yaml
team_config:
  org_name: "Acme Engineering"
  required_patterns: ["git-commit"]
```

Then add to your team's bootstrap script:
```bash
curl -fsSL https://raw.githubusercontent.com/swapniltamse/token-optimizer/main/install.sh | bash
cp dotfiles/token-optimizer/patterns.yaml ~/.claude/skills/token-optimizer/config/patterns.yaml
```

---

## What it does NOT do

It does not block legitimate agentic work. If your task is not in the pattern library, Claude proceeds immediately with no message, no friction, no delay.

It does not read or store your code content. The hook sees the command string, not file contents.

It does not make network calls. Zero telemetry. No data leaves your machine.

It does not fight you. The bypass prefix passes any command through in one line.

**Right use cases:** high-frequency, low-complexity operations you run 10-20 times a day. Git housekeeping. File navigation. SQL that starts from scratch when you already know the schema.

**Wrong use cases:** complex refactors that need Claude to read multiple files. Debugging sessions. Any task where the AI output is genuinely worth the token cost.

---

## My savings this week

Run the report, fill this in, share it:

The output is formatted to paste directly into a team Slack channel or a weekly engineering status report. Engineering managers: this is your visibility line into how much the team is self-correcting.

```
python3 ~/.claude/skills/token-optimizer/hooks/token_guard.py report
```

The last line of the report is formatted to paste directly into a comment or post:

```
Saved [X] tokens ($[Y]) this week with token-optimizer.
Top pattern: [Z]. [N] ops blocked.
github.com/swapniltamse/token-optimizer
```

---

## Contributing

The pattern library is the product. If you find an operation that is consistently faster to do manually, open a PR with a new entry in `config/patterns.yaml`.

Required fields per pattern: `id`, `name`, `skill_keywords`, `bash_patterns`, `manual_alternative`, `relatable_reason`, `token_estimate_low`, `token_estimate_high`.

Token estimates: use your own Claude Code usage dashboard for real numbers. Conservative is better than inflated.

---

## Author

Built by [Swapnil Tamse](https://www.linkedin.com/in/swapniltamse/) — engineering leader, AI/AI Security, NYC.

[LinkedIn post that started this](https://www.linkedin.com/feed/update/urn:li:activity:7467175698206445568/) — context on why token discipline matters at team scale.

---

## License

MIT.
