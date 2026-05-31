"""
Unit tests for hooks/token_guard.py

Design notes:
- token_guard.main() reads from stdin, writes JSON to stdout
- Tests use unittest.mock to control stdin/stdout without filesystem side effects
- Pattern loading uses the real config/patterns.yaml (no mocking of file I/O)
  so tests break if the pattern library changes in a breaking way — that is intentional
- Each test class covers one behavioral contract

Run: pytest tests/ -v
"""
import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import token_guard


# ── helpers ────────────────────────────────────────────────────────────────

def _payload(tool_name: str, **kwargs) -> str:
    """Build a JSON payload string as Claude Code would send it."""
    return json.dumps({"tool_name": tool_name, "tool_input": kwargs})


def _run(payload_str: str, env: dict = None) -> dict:
    """Feed payload through main(), return parsed stdout as a dict."""
    with patch.dict(os.environ, env or {}, clear=False):
        with patch("sys.stdin", StringIO(payload_str)):
            buf = StringIO()
            with patch("sys.stdout", buf):
                token_guard.main()
            return json.loads(buf.getvalue())


# ── bypass mechanism ───────────────────────────────────────────────────────

class TestBypassMechanism:
    def test_skip_prefix_at_start_bypasses(self):
        """The canonical bypass: comment at the very start of the command."""
        payload = _payload("Bash", command="# token-optimizer: skip\ngit commit")
        assert _run(payload)["action"] == "continue"

    def test_skip_prefix_with_leading_whitespace_bypasses(self):
        """Leading whitespace before the prefix still counts as start-of-command."""
        payload = _payload("Bash", command="  # token-optimizer: skip\ngit commit")
        assert _run(payload)["action"] == "continue"

    def test_skip_prefix_mid_command_does_not_bypass(self):
        """The skip comment only works at the start. Mid-command comments do not bypass."""
        payload = _payload("Bash", command="git commit\n# token-optimizer: skip")
        assert _run(payload)["action"] == "block"


# ── env var kill switch ────────────────────────────────────────────────────

class TestEnvVarKillSwitch:
    def test_disabled_1_passes_everything_through(self):
        payload = _payload("Bash", command="git commit")
        assert _run(payload, {"TOKEN_OPTIMIZER_DISABLED": "1"})["action"] == "continue"

    def test_disabled_0_still_blocks(self):
        """Only the exact string '1' disables the hook."""
        payload = _payload("Bash", command="git commit")
        assert _run(payload, {"TOKEN_OPTIMIZER_DISABLED": "0"})["action"] == "block"

    def test_disabled_true_string_still_blocks(self):
        payload = _payload("Bash", command="git commit")
        assert _run(payload, {"TOKEN_OPTIMIZER_DISABLED": "true"})["action"] == "block"


# ── tool filtering ─────────────────────────────────────────────────────────

class TestToolFiltering:
    def test_read_not_intercepted(self):
        assert _run(_payload("Read", file_path="/some/file.py"))["action"] == "continue"

    def test_edit_not_intercepted(self):
        assert _run(_payload("Edit", file_path="/f.py", old_string="a", new_string="b"))["action"] == "continue"

    def test_glob_not_intercepted(self):
        assert _run(_payload("Glob", pattern="**/*.py"))["action"] == "continue"

    def test_grep_not_intercepted(self):
        assert _run(_payload("Grep", pattern="def main"))["action"] == "continue"


# ── git patterns ───────────────────────────────────────────────────────────

class TestGitPatterns:
    def test_bare_git_commit_blocked(self):
        assert _run(_payload("Bash", command="git commit"))["action"] == "block"

    def test_git_commit_amend_blocked(self):
        assert _run(_payload("Bash", command="git commit --amend"))["action"] == "block"

    def test_git_commit_with_message_not_blocked(self):
        """User already wrote their own message — not our business."""
        assert _run(_payload("Bash", command='git commit -m "fix: resolve null pointer"'))["action"] == "continue"

    def test_git_commit_with_flag_before_message_not_blocked(self):
        assert _run(_payload("Bash", command='git commit -S -m "signed commit"'))["action"] == "continue"

    def test_bare_git_diff_blocked(self):
        assert _run(_payload("Bash", command="git diff"))["action"] == "block"

    def test_git_diff_head_blocked(self):
        assert _run(_payload("Bash", command="git diff HEAD~1"))["action"] == "block"

    def test_git_diff_stat_not_blocked(self):
        """--stat is the cheap summary we recommend. It must not trigger the block."""
        assert _run(_payload("Bash", command="git diff --stat"))["action"] == "continue"

    def test_git_diff_specific_file_not_blocked(self):
        assert _run(_payload("Bash", command="git diff src/main.py"))["action"] == "continue"

    def test_verbose_git_log_blocked(self):
        assert _run(_payload("Bash", command="git log"))["action"] == "block"

    def test_git_log_with_flags_blocked(self):
        assert _run(_payload("Bash", command="git log -10"))["action"] == "block"

    def test_git_log_oneline_not_blocked(self):
        assert _run(_payload("Bash", command="git log --oneline -10"))["action"] == "continue"


# ── file operation patterns ────────────────────────────────────────────────

class TestFileOperationPatterns:
    def test_find_with_name_blocked(self):
        assert _run(_payload("Bash", command="find . -name '*.py'"))["action"] == "block"

    def test_recursive_grep_blocked(self):
        assert _run(_payload("Bash", command="grep -r 'def main' src/"))["action"] == "block"

    def test_ripgrep_blocked(self):
        assert _run(_payload("Bash", command="rg 'TODO' --type py"))["action"] == "block"


# ── commands that must never be blocked ───────────────────────────────────

class TestNonMatchingPassThrough:
    def test_pytest_continues(self):
        assert _run(_payload("Bash", command="pytest tests/ -v"))["action"] == "continue"

    def test_npm_install_continues(self):
        assert _run(_payload("Bash", command="npm install"))["action"] == "continue"

    def test_git_push_continues(self):
        assert _run(_payload("Bash", command="git push origin main"))["action"] == "continue"

    def test_git_add_continues(self):
        assert _run(_payload("Bash", command="git add -A"))["action"] == "continue"

    def test_git_status_continues(self):
        """git status avg is 550 tokens — below default threshold of 1000."""
        assert _run(_payload("Bash", command="git status"))["action"] == "continue"

    def test_git_checkout_continues(self):
        assert _run(_payload("Bash", command="git checkout -b feature/new"))["action"] == "continue"

    def test_docker_compose_continues(self):
        assert _run(_payload("Bash", command="docker compose up -d"))["action"] == "continue"

    def test_python_script_continues(self):
        assert _run(_payload("Bash", command="python3 manage.py migrate"))["action"] == "continue"

    def test_ls_below_threshold_continues(self):
        """ls avg is 400 tokens — below default threshold of 1000."""
        assert _run(_payload("Bash", command="ls"))["action"] == "continue"

    def test_ls_with_flags_below_threshold_continues(self):
        assert _run(_payload("Bash", command="ls -la /some/dir"))["action"] == "continue"


# ── block message quality ──────────────────────────────────────────────────

class TestBlockMessageContent:
    def _git_commit_message(self) -> str:
        result = _run(_payload("Bash", command="git commit"))
        assert result["action"] == "block"
        return result["message"]

    def test_message_has_human_opener(self):
        msg = self._git_commit_message()
        assert "You already know this one" in msg

    def test_message_has_relatable_reason(self):
        msg = self._git_commit_message()
        assert "You were there" in msg

    def test_message_has_manual_alternative(self):
        msg = self._git_commit_message()
        assert "git commit -m" in msg

    def test_message_has_token_estimate(self):
        msg = self._git_commit_message()
        assert "tokens" in msg

    def test_message_has_dollar_cost(self):
        """Dollar cost must appear — it is the hook for non-technical readers."""
        msg = self._git_commit_message()
        assert "$" in msg

    def test_message_has_bypass_hint(self):
        msg = self._git_commit_message()
        assert "# token-optimizer: skip" in msg

    def test_dollar_appears_before_token_count(self):
        """Dollar cost must come before the raw token number in the message."""
        msg = self._git_commit_message()
        dollar_pos = msg.find("$")
        token_pos = msg.find("tokens")
        assert dollar_pos < token_pos, "Dollar cost should appear before token count"


# ── malformed input — hook must never crash ───────────────────────────────

class TestMalformedInput:
    def test_non_json_stdin_continues(self):
        with patch("sys.stdin", StringIO("not json at all")):
            buf = StringIO()
            with patch("sys.stdout", buf):
                token_guard.main()
            assert json.loads(buf.getvalue())["action"] == "continue"

    def test_empty_stdin_continues(self):
        with patch("sys.stdin", StringIO("")):
            buf = StringIO()
            with patch("sys.stdout", buf):
                token_guard.main()
            assert json.loads(buf.getvalue())["action"] == "continue"

    def test_empty_command_continues(self):
        assert _run(_payload("Bash", command=""))["action"] == "continue"

    def test_missing_tool_input_continues(self):
        with patch("sys.stdin", StringIO(json.dumps({"tool_name": "Bash"}))):
            buf = StringIO()
            with patch("sys.stdout", buf):
                token_guard.main()
            assert json.loads(buf.getvalue())["action"] == "continue"

    def test_missing_tool_name_continues(self):
        with patch("sys.stdin", StringIO(json.dumps({"tool_input": {"command": "ls"}}))):
            buf = StringIO()
            with patch("sys.stdout", buf):
                token_guard.main()
            assert json.loads(buf.getvalue())["action"] == "continue"
