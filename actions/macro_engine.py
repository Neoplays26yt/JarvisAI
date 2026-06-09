"""
macro_engine_action.py — JARVIS Macro Engine action.

Exposes core/macro_engine.py as a JARVIS tool.
Allows listing, creating, running, editing, and deleting macros.
"""

import sys
import json
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = _get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "macros.json"


def _log(msg: str, player=None) -> None:
    print(f"[Macro] {msg}")
    if player:
        try:
            player.write_log(f"MACRO: {msg}")
        except Exception:
            pass


def _get_engine():
    """Lazy-load the MacroEngine singleton."""
    try:
        from core.macro_engine import MacroEngine
        return MacroEngine()
    except Exception as e:
        raise RuntimeError(f"Could not load MacroEngine: {e}") from e


# ── Actions ───────────────────────────────────────────────────────────────────

def _list_macros(player=None) -> str:
    try:
        engine = _get_engine()
        macros = engine.list_macros()
        if not macros:
            return "No macros defined yet. Use action='create' to add one."
        lines = [f"⚡ Macros ({len(macros)}):"]
        for name, data in sorted(macros.items()):
            desc  = data.get("description", "")
            steps = len(data.get("steps", []))
            lines.append(f"  • {name}" + (f" — {desc}" if desc else "") + f" ({steps} steps)")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not list macros: {e}"


def _run_macro(name: str, speak=None, player=None) -> str:
    if not name:
        return "Please provide a macro name to run."
    try:
        engine  = _get_engine()
        macros  = engine.list_macros()
        # Partial name match
        if name not in macros:
            name_lower = name.lower()
            for k in macros:
                if name_lower in k.lower() or k.lower() in name_lower:
                    name = k
                    break
        if name not in macros:
            return f"Macro '{name}' not found. Use action='list' to see available macros."
        _log(f"Running macro '{name}'...", player)
        engine.execute_macro(name, speak=speak)
        steps = len(macros[name].get("steps", []))
        return f"Macro '{name}' started ({steps} steps). Running in background."
    except Exception as e:
        return f"Could not run macro '{name}': {e}"


def _create_macro(name: str, description: str, steps, player=None) -> str:
    if not name:
        return "Please provide a macro name."
    if not steps:
        return "Please provide at least one step."

    # steps may come in as a list of dicts or a JSON string
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            return "Steps must be a JSON array of {tool, parameters} objects."
    if not isinstance(steps, list):
        return "Steps must be a list of {tool, parameters} objects."

    try:
        engine = _get_engine()
        macros = engine.list_macros()
        if name in macros:
            # Update instead of error
            engine.edit_macro(name, description=description, steps=steps)
            _log(f"Updated macro '{name}'", player)
            return f"Macro '{name}' updated with {len(steps)} steps."
        engine.create_macro(name, description or "", steps)
        _log(f"Created macro '{name}'", player)
        return f"Macro '{name}' created with {len(steps)} steps."
    except Exception as e:
        return f"Could not create macro '{name}': {e}"


def _delete_macro(name: str, player=None) -> str:
    if not name:
        return "Please provide a macro name to delete."
    try:
        engine = _get_engine()
        engine.delete_macro(name)
        _log(f"Deleted macro '{name}'", player)
        return f"Macro '{name}' deleted."
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Could not delete macro '{name}': {e}"


def _info_macro(name: str, player=None) -> str:
    if not name:
        return "Please provide a macro name."
    try:
        engine = _get_engine()
        macros = engine.list_macros()
        if name not in macros:
            name_lower = name.lower()
            for k in macros:
                if name_lower in k.lower():
                    name = k
                    break
        if name not in macros:
            return f"Macro '{name}' not found."
        data  = macros[name]
        steps = data.get("steps", [])
        lines = [
            f"⚡ Macro: {name}",
            f"   Description: {data.get('description', '(none)')}",
            f"   Steps: {len(steps)}",
        ]
        for i, s in enumerate(steps, 1):
            tool   = s.get("tool", "?")
            params = s.get("parameters", {})
            lines.append(f"   {i}. {tool} — {json.dumps(params)[:60]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not get macro info: {e}"


# ── Entry Point ───────────────────────────────────────────────────────────────

def macro_engine(
    parameters: dict = None,
    player=None,
    speak=None,
) -> str:
    """
    JARVIS Macro Engine.

    Record and replay sequences of JARVIS tool calls as named macros.

    parameters:
        action      : list | run | create | delete | info
        name        : Macro name
        description : Macro description (for create)
        steps       : List of {tool: str, parameters: dict} steps (for create), or JSON string
    """
    try:
        p      = parameters or {}
        action = p.get("action", "list").strip().lower()
        name   = p.get("name", "").strip()

        _log(f"action={action}  name={name!r}", player)

        if action == "list":
            result = _list_macros(player)
        elif action == "run":
            result = _run_macro(name, speak=speak, player=player)
        elif action == "create":
            result = _create_macro(
                name=name,
                description=p.get("description", ""),
                steps=p.get("steps", []),
                player=player,
            )
        elif action == "delete":
            result = _delete_macro(name, player)
        elif action == "info":
            result = _info_macro(name, player)
        else:
            result = (
                f"Unknown action: '{action}'. "
                "Use: list | run | create | delete | info"
            )

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Macro engine error: {e}"
