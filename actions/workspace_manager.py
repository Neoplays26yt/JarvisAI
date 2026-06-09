"""
workspace_manager_action.py — JARVIS Workspace Manager action.

Exposes core/workspace_manager.py as a JARVIS tool.
Manages named workspaces: activate, list, create, delete, and inspect.
"""

import json
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR       = _get_base_dir()
WORKSPACE_DIR  = Path.home() / ".jarvis" / "workspaces"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str, player=None) -> None:
    print(f"[Workspace] {msg}")
    if player:
        try:
            player.write_log(f"WORKSPACE: {msg}")
        except Exception:
            pass


def _load_all() -> dict:
    """Load all workspace definitions. Returns {name: data}."""
    workspaces = {}
    for f in WORKSPACE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            workspaces[name.lower()] = data
        except Exception as e:
            print(f"[Workspace] Could not load {f}: {e}")
    return workspaces


def _save(data: dict) -> None:
    name = data.get("name", "unnamed").lower().replace(" ", "_")
    path = WORKSPACE_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _delete(name: str) -> bool:
    path = WORKSPACE_DIR / f"{name.lower().replace(' ', '_')}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def _find(name: str, workspaces: dict) -> str | None:
    """Find workspace by exact or partial name."""
    key = name.lower().strip()
    if key in workspaces:
        return key
    for k in workspaces:
        if key in k or k in key:
            return k
    return None


# ── Activate ──────────────────────────────────────────────────────────────────

def _activate(name: str, player=None) -> str:
    """Activate a workspace — closes listed apps, opens listed apps."""
    import subprocess
    import os
    import time

    workspaces = _load_all()
    found = _find(name, workspaces)
    if not found:
        return f"Workspace '{name}' not found. Use 'list' to see available workspaces."

    ws = workspaces[found]
    ws_name = ws.get("name", found)
    _log(f"Activating '{ws_name}'...", player)
    results = []

    # Close apps
    close_apps = ws.get("close_apps", [])
    if close_apps:
        try:
            import psutil
            for app in close_apps:
                app_lower = app.lower()
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        pname = proc.info.get("name", "")
                        if pname and app_lower in pname.lower():
                            proc.terminate()
                            results.append(f"Closed {pname}")
                    except Exception:
                        pass
            if results:
                time.sleep(0.8)
        except ImportError:
            results.append("psutil not installed — could not close apps")

    # Open apps
    open_apps = ws.get("apps", [])
    for app in open_apps:
        launch_cmd = app.get("launch_cmd", "")
        path       = app.get("path", "")
        label      = app.get("name", launch_cmd or path)
        try:
            if launch_cmd:
                subprocess.Popen(launch_cmd, shell=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                results.append(f"Launched {label}")
            elif path and os.path.exists(path):
                os.startfile(path)
                results.append(f"Opened {label}")
            elif path:
                # Try it as a command
                subprocess.Popen(path, shell=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                results.append(f"Launched {label}")
        except Exception as e:
            results.append(f"Could not launch {label}: {e}")

    # Set directory
    directory = ws.get("directory", "")
    if directory and os.path.isdir(directory):
        results.append(f"Working directory: {directory}")

    summary = "\n".join(f"  • {r}" for r in results) if results else "  (no apps configured)"
    _log(f"Workspace '{ws_name}' activated", player)
    return f"Workspace '{ws_name}' activated.\n{summary}"


# ── Create ────────────────────────────────────────────────────────────────────

def _create(name: str, parameters: dict, player=None) -> str:
    """Create or update a workspace definition."""
    if not name:
        return "Please provide a workspace name."

    workspaces = _load_all()
    existing   = workspaces.get(name.lower(), {})

    apps = parameters.get("apps", existing.get("apps", []))
    if isinstance(apps, str):
        # Comma-separated list of app commands
        apps = [{"name": a.strip(), "launch_cmd": a.strip()} for a in apps.split(",") if a.strip()]

    ws = {
        "name":        name,
        "description": parameters.get("description", existing.get("description", "")),
        "apps":        apps,
        "close_apps":  parameters.get("close_apps", existing.get("close_apps", [])),
        "directory":   parameters.get("directory", existing.get("directory", "")),
        "tags":        parameters.get("tags", existing.get("tags", [])),
    }
    _save(ws)
    _log(f"Workspace '{name}' saved", player)
    return f"Workspace '{name}' created/updated with {len(apps)} app(s)."


# ── Actions ───────────────────────────────────────────────────────────────────

def _list_workspaces(player=None) -> str:
    workspaces = _load_all()
    if not workspaces:
        return "No workspaces defined yet. Use action='create' to add one."
    lines = [f"📋 Available Workspaces ({len(workspaces)}):"]
    for key, ws in sorted(workspaces.items()):
        name   = ws.get("name", key)
        desc   = ws.get("description", "")
        n_apps = len(ws.get("apps", []))
        lines.append(f"  • {name}" + (f" — {desc}" if desc else "") + f" ({n_apps} apps)")
    return "\n".join(lines)


def _info(name: str, player=None) -> str:
    workspaces = _load_all()
    found = _find(name, workspaces)
    if not found:
        return f"Workspace '{name}' not found."
    ws = workspaces[found]
    lines = [f"📂 Workspace: {ws.get('name', found)}"]
    if ws.get("description"):
        lines.append(f"   Description: {ws['description']}")
    if ws.get("directory"):
        lines.append(f"   Directory: {ws['directory']}")
    apps = ws.get("apps", [])
    if apps:
        lines.append(f"   Apps ({len(apps)}):")
        for a in apps:
            label = a.get("name") or a.get("launch_cmd") or a.get("path", "?")
            lines.append(f"     • {label}")
    close_apps = ws.get("close_apps", [])
    if close_apps:
        lines.append(f"   Close on activate: {', '.join(close_apps)}")
    return "\n".join(lines)


def _delete_action(name: str, player=None) -> str:
    if not name:
        return "Please provide a workspace name to delete."
    if _delete(name):
        _log(f"Deleted workspace '{name}'", player)
        return f"Workspace '{name}' deleted."
    return f"Workspace '{name}' not found."


# ── Entry Point ───────────────────────────────────────────────────────────────

def workspace_manager(
    parameters: dict = None,
    player=None,
    speak=None,
) -> str:
    """
    JARVIS Workspace Manager.

    Manages named workspace configurations — groups of apps to open/close together.

    parameters:
        action      : activate | list | create | delete | info
        name        : Workspace name
        description : Workspace description (for create)
        apps        : List of app dicts [{name, launch_cmd, path}] or comma-separated string
        close_apps  : List of process names to close on activate
        directory   : Default working directory
        tags        : List of tags
    """
    try:
        p      = parameters or {}
        action = p.get("action", "list").strip().lower()
        name   = p.get("name", "").strip()

        _log(f"action={action}  name={name!r}", player)

        if action == "activate":
            if not name:
                return "Please provide a workspace name to activate."
            result = _activate(name, player)
        elif action == "list":
            result = _list_workspaces(player)
        elif action == "create":
            result = _create(name, p, player)
        elif action == "delete":
            result = _delete_action(name, player)
        elif action == "info":
            if not name:
                return "Please provide a workspace name to inspect."
            result = _info(name, player)
        else:
            result = (
                f"Unknown action: '{action}'. "
                "Use: activate | list | create | delete | info"
            )

        if callable(speak):
            # Only speak the first sentence
            first = result.split("\n")[0]
            speak(first)
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Workspace manager error: {e}"
