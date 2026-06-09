"""
clipboard_manager.py — JARVIS Action Module
============================================
Manages clipboard operations including get, set, clear, and a persistent
JSON-backed history log stored at ~/.jarvis/clipboard_history.json.

Supported actions (via parameters['action']):
    get          — Return current clipboard text.
    set          — Set clipboard to parameters['text'].
    clear        — Clear the clipboard.
    history_add  — Append current clipboard text to history (max 50 entries).
    history_list — Return the last N history entries (N = parameters.get('count', 10)).
    history_clear— Wipe the history file.

Dependencies:
    pyperclip (with graceful ImportError fallback)
"""

import json
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional dependency — pyperclip
# ---------------------------------------------------------------------------
try:
    import pyperclip
    _PYPERCLIP_AVAILABLE = True
except ImportError:
    _PYPERCLIP_AVAILABLE = False
    print("[Clipboard] WARNING: pyperclip is not installed. "
          "Install it with: pip install pyperclip")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HISTORY_DIR  = Path.home() / ".jarvis"
_HISTORY_FILE = _HISTORY_DIR / "clipboard_history.json"
_MAX_HISTORY  = 50
_MODULE       = "Clipboard"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_history_dir() -> None:
    """Create the ~/.jarvis directory if it does not already exist."""
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _load_history() -> list:
    """Load clipboard history from disk; return empty list on any error."""
    try:
        if _HISTORY_FILE.exists():
            with open(_HISTORY_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    return data
    except Exception as exc:
        print(f"[{_MODULE}] Could not load history: {exc}")
    return []


def _save_history(history: list) -> None:
    """Persist the history list to disk as JSON."""
    _ensure_history_dir()
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[{_MODULE}] Could not save history: {exc}")


def _get_clipboard_text() -> str:
    """Return current clipboard text; raises RuntimeError if pyperclip missing."""
    if not _PYPERCLIP_AVAILABLE:
        raise RuntimeError("pyperclip is not installed.")
    return pyperclip.paste()


def _set_clipboard_text(text: str) -> None:
    """Set clipboard to the given text; raises RuntimeError if pyperclip missing."""
    if not _PYPERCLIP_AVAILABLE:
        raise RuntimeError("pyperclip is not installed.")
    pyperclip.copy(text)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _action_get() -> str:
    """Return the current clipboard content."""
    print(f"[{_MODULE}] Action: get")
    text = _get_clipboard_text()
    if not text:
        return "Clipboard is currently empty."
    preview = text[:200] + ("…" if len(text) > 200 else "")
    return f"Clipboard content ({len(text)} chars):\n{preview}"


def _action_set(parameters: dict) -> str:
    """Set the clipboard to parameters['text']."""
    print(f"[{_MODULE}] Action: set")
    text = parameters.get("text", "")
    if not isinstance(text, str):
        return "Error: 'text' parameter must be a string."
    _set_clipboard_text(text)
    return f"Clipboard set to: {text[:100]}{'…' if len(text) > 100 else ''}"


def _action_clear() -> str:
    """Clear the clipboard by copying an empty string."""
    print(f"[{_MODULE}] Action: clear")
    _set_clipboard_text("")
    return "Clipboard cleared."


def _action_history_add() -> str:
    """Append the current clipboard text to the history file."""
    print(f"[{_MODULE}] Action: history_add")
    text = _get_clipboard_text()
    if not text:
        return "Clipboard is empty — nothing added to history."

    history = _load_history()

    # Avoid duplicate consecutive entries
    if history and history[-1].get("text") == text:
        return "Clipboard text is identical to the last history entry — skipped."

    entry = {
        "text":      text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    history.append(entry)

    # Enforce max size (keep newest entries)
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]

    _save_history(history)
    return (f"Added to clipboard history ({len(history)}/{_MAX_HISTORY} entries). "
            f"Preview: {text[:80]}{'…' if len(text) > 80 else ''}")


def _action_history_list(parameters: dict) -> str:
    """Return the last N history entries."""
    print(f"[{_MODULE}] Action: history_list")
    count = int(parameters.get("count", 10))
    history = _load_history()

    if not history:
        return "Clipboard history is empty."

    recent = history[-count:]
    lines  = [f"Clipboard history (last {len(recent)} of {len(history)} entries):"]
    for i, entry in enumerate(reversed(recent), start=1):
        ts      = entry.get("timestamp", "unknown time")
        preview = entry.get("text", "")[:80]
        if len(entry.get("text", "")) > 80:
            preview += "…"
        lines.append(f"  {i:>2}. [{ts}] {preview}")

    return "\n".join(lines)


def _action_history_clear() -> str:
    """Delete all history entries."""
    print(f"[{_MODULE}] Action: history_clear")
    _save_history([])
    return "Clipboard history cleared."


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def clipboard_manager(parameters: dict, player=None, speak=None) -> str:
    """
    JARVIS clipboard manager action.

    Parameters
    ----------
    parameters : dict
        Must contain 'action' key.  Additional keys depend on the action:
        - 'text'  (str)  : text to set (action='set')
        - 'count' (int)  : number of history entries (action='history_list')
    player : optional
        Unused; present for interface compatibility.
    speak : callable, optional
        If provided, will be called with the result string for TTS output.

    Returns
    -------
    str
        Human-readable result of the requested action.
    """
    action = str(parameters.get("action", "")).strip().lower()
    print(f"[{_MODULE}] Received action='{action}'")

    if not _PYPERCLIP_AVAILABLE and action in ("get", "set", "clear", "history_add"):
        result = ("Error: pyperclip is not available. "
                  "Install it with: pip install pyperclip")
        if callable(speak):
            speak(result)
        return result

    try:
        if action == "get":
            result = _action_get()
        elif action == "set":
            result = _action_set(parameters)
        elif action == "clear":
            result = _action_clear()
        elif action == "history_add":
            result = _action_history_add()
        elif action == "history_list":
            result = _action_history_list(parameters)
        elif action == "history_clear":
            result = _action_history_clear()
        else:
            result = (
                f"Unknown clipboard action: '{action}'. "
                "Valid actions: get, set, clear, history_add, history_list, history_clear."
            )
    except Exception as exc:
        print(f"[{_MODULE}] Unhandled exception: {exc}")
        print(traceback.format_exc())
        result = f"Clipboard error: {exc}"

    print(f"[{_MODULE}] Result: {result[:120]}")
    if callable(speak):
        speak(result)
    return result
