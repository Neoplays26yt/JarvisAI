"""
terminal_agent.py — JARVIS Action Module
=========================================
A safety-gated terminal command executor.  Commands are matched against a
whitelist of safe prefixes before execution; known dangerous patterns are
explicitly blocked with a clear refusal message.

Usage (parameters dict):
    command  (str) : Shell command to run.
    cwd      (str) : Working directory (default: Path.home()).
    timeout  (int) : Max seconds to wait (default: 30).

Output is a structured string containing:
    command, return_code, stdout (≤3000 chars), stderr (≤1000 chars).

Logs with [Terminal] prefix.
"""

import subprocess
import sys
import traceback
from pathlib import Path

_MODULE = "Terminal"

# ---------------------------------------------------------------------------
# Safety configuration
# ---------------------------------------------------------------------------

# Blocked patterns — checked as case-insensitive substrings of the command.
_BLOCKED_PATTERNS: list[str] = [
    "rm -rf",
    "rm -r /",
    "del /f",
    "del /s",
    "format c",
    "format /",
    "mkfs",
    "sudo rm",
    "dd if=",
    "reg delete",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
    "taskkill /f",
    "net user",
    ":(){:|:&};:",   # fork bomb
    ">(dev/null",
    "mv / ",
]

# Allowed command prefixes — at least one must match (case-insensitive).
_ALLOWED_PREFIXES: set[str] = {
    # Version control
    "git",
    # Python ecosystem
    "pip", "pip3", "python", "python3",
    # Node / JS ecosystem
    "node", "npm", "npx", "yarn",
    # Basic shell navigation / info
    "echo", "dir", "ls", "pwd", "cd", "cat", "type",
    # File / directory management (safe subset)
    "mkdir", "copy", "xcopy", "robocopy", "cp", "mv",
    # Build systems / compilers
    "dotnet", "cargo", "go", "javac", "java", "mvn",
    "make", "cmake", "gcc", "g++", "clang",
    # Shell helpers
    "where", "which", "find", "grep", "rg",
    # Standalone terminals
    "start", "cmd", "powershell", "pwsh", "wt",
    # Misc. dev tools
    "curl", "wget", "ssh-keygen", "openssl",
    "docker", "kubectl", "terraform",
    "pytest", "coverage", "mypy", "ruff", "black", "flake8",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_blocked(command: str) -> tuple[bool, str]:
    """
    Return (True, reason) if the command matches a blocked pattern,
    else (False, '').
    """
    cmd_lower = command.lower().strip()
    for pattern in _BLOCKED_PATTERNS:
        if pattern.lower() in cmd_lower:
            return True, pattern
    return False, ""


def _is_allowed(command: str) -> bool:
    """
    Return True if the command starts with (or is) one of the allowed prefixes.
    Strips leading whitespace and handles quoted commands.
    """
    cmd_stripped = command.strip().lstrip('"').lstrip("'")
    first_token  = cmd_stripped.split()[0] if cmd_stripped.split() else ""
    first_lower  = first_token.lower()

    # Match exact token against the allowed set
    if first_lower in _ALLOWED_PREFIXES:
        return True

    # Also accept Windows-style paths to allowed executables
    # e.g. C:\Python311\python.exe
    for prefix in _ALLOWED_PREFIXES:
        if first_lower.endswith(f"{prefix}.exe") or first_lower.endswith(prefix):
            return True

    return False


def _truncate(text: str, max_len: int) -> str:
    """Truncate text and append a note if it was cut."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n… [truncated — {len(text) - max_len} chars omitted]"


def _format_result(command: str, returncode: int,
                   stdout: str, stderr: str) -> str:
    """Build a structured, human-readable result string."""
    lines = [
        "── Terminal Result ──────────────────────",
        f"  Command     : {command}",
        f"  Return Code : {returncode}",
    ]
    if stdout:
        lines.append("  ── stdout ──────────────────────────────")
        lines.append(stdout)
    else:
        lines.append("  stdout      : (empty)")

    if stderr:
        lines.append("  ── stderr ──────────────────────────────")
        lines.append(stderr)

    lines.append("─────────────────────────────────────────")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def terminal_agent(parameters: dict, player=None, speak=None) -> str:
    """
    JARVIS safe terminal command executor.

    Only commands whose first token appears in the _ALLOWED_PREFIXES set are
    executed.  Commands matching any _BLOCKED_PATTERNS entry are refused
    immediately without execution.

    Parameters
    ----------
    parameters : dict
        command (str) : Shell command to run.
        cwd     (str) : Working directory path (default: user home dir).
        timeout (int) : Seconds before the command is killed (default: 30).
    player : optional
        Unused; present for interface compatibility.
    speak : callable, optional
        If provided, called with a concise TTS-friendly result.

    Returns
    -------
    str
        Structured output string with command, return code, stdout, stderr.
    """
    command = str(parameters.get("command", "")).strip()
    cwd_raw = str(parameters.get("cwd", "")).strip()
    timeout = int(parameters.get("timeout", 30))

    print(f"[{_MODULE}] Received command='{command[:80]}' cwd='{cwd_raw}' timeout={timeout}")

    # ── Guard: empty command ────────────────────────────────────────────────
    if not command:
        result = "Error: No command provided. Please set parameters['command']."
        if callable(speak):
            speak(result)
        return result

    # ── Guard: blocked patterns ─────────────────────────────────────────────
    blocked, reason = _is_blocked(command)
    if blocked:
        result = (
            f"🚫 REFUSED: Command blocked for safety reasons.\n"
            f"   Matched blocked pattern: '{reason}'\n"
            f"   Command: {command}\n\n"
            "This action is not permitted by JARVIS terminal policy."
        )
        print(f"[{_MODULE}] Blocked command — pattern='{reason}'")
        if callable(speak):
            speak(f"Command refused. Matched blocked pattern: {reason}")
        return result

    # ── Guard: not in whitelist ─────────────────────────────────────────────
    if not _is_allowed(command):
        first_token = command.split()[0] if command.split() else command
        result = (
            f"🚫 REFUSED: Command '{first_token}' is not in the allowed list.\n"
            f"   Allowed categories: "
            f"git, pip, python, node, npm, echo, dir, ls, pwd, cd, cat, type, "
            f"mkdir, copy, xcopy, robocopy, dotnet, cargo, go, javac, make, "
            f"cmake, and more.\n"
            "If you need this command, contact the JARVIS administrator."
        )
        print(f"[{_MODULE}] Not-allowed command prefix: '{first_token}'")
        if callable(speak):
            speak(f"Command '{first_token}' is not on the allowed list.")
        return result

    # ── Resolve working directory ───────────────────────────────────────────
    if cwd_raw:
        cwd_path = Path(cwd_raw)
        if not cwd_path.is_dir():
            result = f"Error: Working directory does not exist: {cwd_raw}"
            if callable(speak):
                speak(result)
            return result
    else:
        cwd_path = Path.home()

    # ── Execute ─────────────────────────────────────────────────────────────
    print(f"[{_MODULE}] Executing: {command} (cwd={cwd_path}, timeout={timeout}s)")
    try:
        first_token = command.split()[0].lower() if command.split() else ""
        # Spawn interactive terminal if requested or if command inherently suggests it on Windows
        is_windows = sys.platform == "win32"
        if (interactive or first_token in {"start", "cmd", "powershell", "pwsh", "wt"}) and is_windows:
            # Prepare shell command for new window
            if first_token not in {"start", "cmd", "powershell", "pwsh", "wt"}:
                cmd_to_run = f'start cmd /k "{command}"'
            else:
                cmd_to_run = command

            proc = subprocess.Popen(
                cmd_to_run,
                shell=True,
                cwd=str(cwd_path),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            result = f"Launched standalone interactive desktop terminal for command: {command}"
            print(f"[{_MODULE}] Launched standalone terminal.")
        else:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = _truncate(proc.stdout.rstrip(), 3000)
            stderr = _truncate(proc.stderr.rstrip(), 1000)
            result = _format_result(command, proc.returncode, stdout, stderr)
            print(f"[{_MODULE}] Completed — return_code={proc.returncode}, "
                  f"stdout_len={len(proc.stdout)}, stderr_len={len(proc.stderr)}")

    except subprocess.TimeoutExpired:
        result = (
            f"Error: Command timed out after {timeout} seconds.\n"
            f"  Command: {command}"
        )
        print(f"[{_MODULE}] Timeout after {timeout}s")

    except FileNotFoundError as exc:
        result = f"Error: Command not found — {exc}"
        print(f"[{_MODULE}] FileNotFoundError: {exc}")

    except Exception as exc:
        print(f"[{_MODULE}] Unhandled exception: {exc}")
        print(traceback.format_exc())
        result = f"Terminal error: {exc}"

    if callable(speak):
        # Provide a concise TTS summary (avoid reading out long stdout)
        first_line = result.split("\n")[0]
        speak(first_line)

    return result
