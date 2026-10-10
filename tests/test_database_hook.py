"""Exercise the hook with command strings; never execute the candidate commands."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex" / "hooks" / "protect_database.py"


@pytest.mark.parametrize("command", [
    "rm expense_tracker.db",
    "rm -- expense_tracker.db",
    "rm *.db",
    "rm -rf .",
    "rm -rf ../expense-tracker",
    "rm \\\nexpense_tracker.db",
    "echo ready\nrm expense_tracker.db",
    "unlink expense_tracker.db",
    "sudo rm expense_tracker.db",
    "env MODE=test rm expense_tracker.db",
    "sh -c 'rm expense_tracker.db'",
    "cd database && rm ../expense_tracker.db",
    "rm $DATABASE",
    "if true; then rm expense_tracker.db; fi",
    "echo `rm expense_tracker.db`",
    "rm expense_{tracker,other}.db",
    "find . -name expense_tracker.db -delete",
    "python3 -c 'import os; os.remove(\"expense_tracker.db\")'",
    "python3 -c 'from os import unlink as delete; delete(\"expense_tracker.db\")'",
    "python3 -c 'from pathlib import Path; Path(\"expense_tracker.db\").unlink()'",
    "python3 -c 'from pathlib import Path; p = Path(\"expense_tracker.db\"); p.unlink()'",
    "python3 -c 'import shutil; shutil.rmtree(\".\")'",
])
def test_blocks_database_deletion(command):
    result = run_hook({"tool_input": {"command": command}, "cwd": str(ROOT)})
    assert result.returncode == 2, result.stderr
    assert "BLOCKED:" in result.stderr


@pytest.mark.parametrize("command", [
    "echo rm expense_tracker.db",
    "cat expense_tracker.db",
    "echo '`rm expense_tracker.db`'",
    "rm notes.txt; cat expense_tracker.db",
    "rm -rf /tmp/spendly-hook-unrelated",
    "cd database && rm notes.txt",
    "python3 -m pytest",
    "python3 -c 'print(\"os.remove(expense_tracker.db)\")'",
    "python3 -c 'import os; os.remove(\"notes.txt\")'",
])
def test_allows_unrelated_commands(command):
    result = run_hook({"tool_input": {"command": command}, "cwd": str(ROOT)})
    assert result.returncode == 0, result.stderr


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=json.dumps(payload),
        text=True, capture_output=True, check=False,
    )


def test_resolves_command_working_directory():
    result = run_hook({
        "tool_input": {"command": "rm ../expense_tracker.db"},
        "cwd": str(ROOT / "database"),
    })
    assert result.returncode == 2


def test_invalid_input_is_blocked():
    assert run_hook({"tool_input": {"command": None}}).returncode == 2


def test_hook_configuration_executes_guard():
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
    hook = config["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Bash"
    result = subprocess.run(
        hook["hooks"][0]["command"], shell=True, cwd=str(ROOT),
        input=json.dumps({"tool_input": {"command": "rm expense_tracker.db"}}),
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2, result.stderr
