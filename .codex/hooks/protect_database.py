"""Guard common shell deletion commands; this is not a shell sandbox.

Unknown deletion targets and quoted wildcard filenames are treated conservatively.
External scripts, eval, arbitrary language runtimes, and filesystem writes outside
the matched Bash tool are not comprehensively analyzed by this guard.
"""

import ast
import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_ROOT / "expense_tracker.db"


def dangerous_path(value, cwd):
    """Treat unknown paths conservatively; include database ancestors and globs."""
    if not isinstance(value, str) or not value or any(c in value for c in "$`"):
        return True
    value = re.sub(r"\{[^{}]*,[^{}]*\}", "*", value)
    path = os.path.abspath(os.path.join(str(cwd), os.path.expanduser(value)))
    targets = [DATABASE, *DATABASE.parents]
    if any(fnmatch.fnmatchcase(str(target), path) for target in targets):
        return True
    resolved = Path(path).resolve()
    return resolved == DATABASE or resolved in DATABASE.parents


def python_deletes_database(source, cwd):
    """Recognize common inline Python deletion calls without executing Python."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True
    values = {}
    aliases = {}

    def name(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return name(node.value) + "." + node.attr
        return ""

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.BinOp):
            left, right = literal(node.left), literal(node.right)
            if left is not None and right is not None:
                if isinstance(node.op, ast.Div):
                    return os.path.join(left, right)
                if isinstance(node.op, ast.Add):
                    return left + right
        if isinstance(node, ast.Call) and name(node.func) in ("Path", "pathlib.Path"):
            parts = [literal(arg) for arg in node.args]
            if parts and all(part is not None for part in parts):
                return os.path.join(*parts)
        return None

    # Source order handles ordinary aliases and simple path assignments.
    for node in sorted(ast.walk(tree), key=lambda item: getattr(item, "lineno", 0)):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or "") + "." + item.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = literal(node.value)
        elif isinstance(node, ast.Call):
            function = name(node.func)
            if function in ("os.remove", "os.unlink", "os.rmdir", "shutil.rmtree"):
                argument = node.args[0] if node.args else next(
                    (kw.value for kw in node.keywords if kw.arg in ("path", "name")), None
                )
                if dangerous_path(literal(argument), cwd):
                    return True
            elif isinstance(node.func, ast.Attribute) and node.func.attr in ("unlink", "rmdir"):
                if dangerous_path(literal(node.func.value), cwd):
                    return True
            elif function in ("os.chdir", "os.fchdir"):
                # Relative targets after a runtime directory change are ambiguous.
                return True
    return False


def command_blocks(command, cwd):
    while command and command[0] in ("if", "then", "elif", "else", "do", "!", "{"):
        command = command[1:]
    if not command:
        return False, cwd
    while command and ("=" in command[0] and command[0].split("=", 1)[0].isidentifier()):
        command = command[1:]
    while command and Path(command[0]).name in ("sudo", "command", "builtin", "env"):
        command = command[1:]
        while command and (command[0].startswith("-") or "=" in command[0]):
            command = command[1:]
    if not command:
        return False, cwd
    executable, args = Path(command[0]).name, command[1:]
    if executable == "cd":
        target = next((arg for arg in args if not arg.startswith("-")), "~")
        if any(c in target for c in "$`*?["):
            return True, cwd
        return False, Path(os.path.abspath(os.path.join(str(cwd), os.path.expanduser(target))))
    if executable in ("rm", "unlink", "rmdir"):
        operands = []
        options = True
        for arg in args:
            if options and arg == "--":
                options = False
            elif options and arg.startswith("-"):
                continue
            else:
                operands.append(arg)
        return any(dangerous_path(arg, cwd) for arg in operands), cwd
    if executable == "find" and any(arg in args for arg in ("-delete", "-exec", "-execdir")):
        roots = []
        for arg in args:
            if arg.startswith("-") or arg in ("!", "("):
                break
            roots.append(arg)
        return any(dangerous_path(root, cwd) for root in (roots or ["."])), cwd
    if executable in ("sh", "bash", "zsh", "dash"):
        for index, arg in enumerate(args):
            if arg.startswith("-") and "c" in arg[1:]:
                return index + 1 >= len(args) or shell_blocks(args[index + 1], cwd), cwd
    if executable.startswith("python") and "-c" in args:
        index = args.index("-c") + 1
        return index >= len(args) or python_deletes_database(args[index], cwd), cwd
    return False, cwd


def shell_blocks(source, cwd):
    # Backticks execute a nested shell command, except inside single quotes.
    quote = None
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        if char == "`" and quote != "'":
            end = source.find("`", index + 1)
            if end == -1 or shell_blocks(source[index + 1:end], cwd):
                return True
            index = end
        index += 1
    source = source.replace("\\\n", "")
    lexer = shlex.shlex(source, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return True
    command = []
    for token in tokens + [";"]:
        if token and all(char in ";&|()\n" for char in token):
            blocked, cwd = command_blocks(command, cwd)
            if blocked:
                return True
            command = []
        else:
            command.append(token)
    return False


def main():
    try:
        data = json.load(sys.stdin)
        command = data["tool_input"]["command"]
        if isinstance(command, list) and all(isinstance(part, str) for part in command):
            command = " ".join(shlex.quote(part) for part in command)
        if not isinstance(command, str):
            raise ValueError("Expected a shell command")
        cwd = Path(data.get("cwd") or PROJECT_ROOT)
        blocked = shell_blocks(command, cwd)
    except (KeyError, TypeError, ValueError, OSError):
        print("BLOCKED: Database guard could not safely inspect the command.", file=sys.stderr)
        return 2
    if blocked:
        print("BLOCKED: Command may delete expense_tracker.db or its containing directory.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
