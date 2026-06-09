"""
project_manager.py — Development Project Tracker for JARVIS
============================================================
Manages a persistent registry of development projects stored in
~/.jarvis/projects.json.

Entry point:
    project_manager(parameters: dict, player=None, speak=None) -> str

Supported actions (parameters['action']):
    add         – Register a new project
    list        – List projects, optionally filtered by status
    open        – Open project folder in VS Code
    set_status  – Change a project's status
    note        – Append a note to a project
    delete      – Remove a project record (files are NOT deleted)
    info        – Show full project details
    stats       – Aggregate breakdown by status and language

Data file: ~/.jarvis/projects.json
"""

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
MODULE = "Projects"
DATA_DIR = Path.home() / ".jarvis"
DATA_FILE = DATA_DIR / "projects.json"

VALID_STATUSES = {"active", "paused", "completed", "archived"}
STATUS_EMOJI = {
    "active": "🟢",
    "paused": "⏸️",
    "completed": "✅",
    "archived": "📦",
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load() -> list:
    """Load projects from disk; return empty list on failure."""
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[{MODULE}] WARNING: could not read {DATA_FILE}: {exc}")
        return []


def _save(projects: list) -> None:
    """Atomically persist project list to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(projects, fh, indent=2, ensure_ascii=False)
    tmp.replace(DATA_FILE)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().isoformat()


# ── Match helpers ─────────────────────────────────────────────────────────────

def _find_project(projects: list, query: str):
    """Return first project matching by exact id, then partial name."""
    for p in projects:
        if p["id"] == query:
            return p
    ql = query.lower()
    for p in projects:
        if ql in p["name"].lower():
            return p
    return None


# ── Action handlers ───────────────────────────────────────────────────────────

def _add(parameters: dict, projects: list) -> str:
    name = (parameters.get("name") or "").strip()
    if not name:
        return "❌ 'name' is required to add a project."

    proj = {
        "id": _new_id(),
        "name": name,
        "path": parameters.get("path", ""),
        "description": parameters.get("description", ""),
        "status": "active",
        "language": parameters.get("language", ""),
        "created_at": _now(),
        "last_opened": "",
        "tags": parameters.get("tags", []),
        "notes": [],
    }
    projects.append(proj)
    _save(projects)
    print(f"[{MODULE}] Added project '{name}' (id={proj['id']})")
    return (
        f"✅ Project registered!\n"
        f"  ID       : {proj['id']}\n"
        f"  Name     : {proj['name']}\n"
        f"  Path     : {proj['path'] or 'not set'}\n"
        f"  Language : {proj['language'] or 'not set'}"
    )


def _list(parameters: dict, projects: list) -> str:
    status_filter = parameters.get("status", "all").lower()
    if status_filter != "all" and status_filter not in VALID_STATUSES:
        status_filter = "all"

    filtered = [
        p for p in projects
        if status_filter == "all" or p.get("status") == status_filter
    ]

    if not filtered:
        return f"📭 No projects found (filter: {status_filter})."

    lines = [f"📁 Projects ({status_filter}) — {len(filtered)} item(s):\n"]
    for idx, p in enumerate(filtered, 1):
        lang = f" [{p['language']}]" if p.get("language") else ""
        tags = f" | tags: {', '.join(p['tags'])}" if p.get("tags") else ""
        lines.append(
            f"  {idx}. [{p['id']}] {STATUS_EMOJI.get(p.get('status', 'active'), '?')} "
            f"{p['name']}{lang}{tags}"
        )
        if p.get("description"):
            lines.append(f"       {p['description'][:80]}")
    return "\n".join(lines)


def _open(parameters: dict, projects: list) -> str:
    query = (parameters.get("id") or parameters.get("name") or "").strip()
    if not query:
        return "❌ Provide 'id' or 'name' to open a project."

    proj = _find_project(projects, query)
    if proj is None:
        return f"❌ No project found matching '{query}'."

    project_path = proj.get("path", "").strip()
    if not project_path:
        return f"⚠️ Project '{proj['name']}' has no path set. Add one with set_status or update manually."

    path_obj = Path(project_path)
    if not path_obj.exists():
        return f"⚠️ Path does not exist: {project_path}"

    try:
        subprocess.Popen(["code", str(path_obj)], shell=True)
        proj["last_opened"] = _now()
        _save(projects)
        print(f"[{MODULE}] Opened '{proj['name']}' in VS Code at {project_path}")
        return f"🚀 Opened '{proj['name']}' in VS Code.\n  Path: {project_path}"
    except FileNotFoundError:
        return (
            "❌ 'code' command not found. Ensure VS Code is installed "
            "and added to PATH."
        )
    except Exception as exc:
        return f"❌ Failed to open VS Code: {exc}"


def _set_status(parameters: dict, projects: list) -> str:
    query = (parameters.get("id") or parameters.get("name") or "").strip()
    new_status = (parameters.get("status") or "").strip().lower()

    if not query:
        return "❌ Provide 'id' or 'name' to identify the project."
    if new_status not in VALID_STATUSES:
        return (
            f"❌ Invalid status '{new_status}'. "
            f"Valid: {', '.join(sorted(VALID_STATUSES))}"
        )

    proj = _find_project(projects, query)
    if proj is None:
        return f"❌ No project found matching '{query}'."

    old = proj.get("status", "active")
    proj["status"] = new_status
    _save(projects)
    print(f"[{MODULE}] Project '{proj['name']}': {old} → {new_status}")
    return (
        f"{STATUS_EMOJI.get(new_status, '?')} Status updated: "
        f"'{proj['name']}' → {new_status}"
    )


def _note(parameters: dict, projects: list) -> str:
    query = (parameters.get("id") or parameters.get("name") or "").strip()
    note_text = (parameters.get("note") or parameters.get("text") or "").strip()

    if not query:
        return "❌ Provide 'id' or 'name' to identify the project."
    if not note_text:
        return "❌ Provide 'note' text to add."

    proj = _find_project(projects, query)
    if proj is None:
        return f"❌ No project found matching '{query}'."

    entry = {"timestamp": _now(), "text": note_text}
    proj.setdefault("notes", []).append(entry)
    _save(projects)
    print(f"[{MODULE}] Added note to '{proj['name']}'")
    return f"📝 Note added to '{proj['name']}':\n  {note_text}"


def _delete(parameters: dict, projects: list) -> str:
    query = (parameters.get("id") or parameters.get("name") or "").strip()
    if not query:
        return "❌ Provide 'id' or 'name' to identify the project."

    proj = _find_project(projects, query)
    if proj is None:
        return f"❌ No project found matching '{query}'."

    projects.remove(proj)
    _save(projects)
    print(f"[{MODULE}] Deleted project '{proj['name']}' ({proj['id']})")
    return f"🗑️ Removed project record: '{proj['name']}' (files NOT deleted)"


def _info(parameters: dict, projects: list) -> str:
    query = (parameters.get("id") or parameters.get("name") or "").strip()
    if not query:
        return "❌ Provide 'id' or 'name' to identify the project."

    proj = _find_project(projects, query)
    if proj is None:
        return f"❌ No project found matching '{query}'."

    notes = proj.get("notes", [])
    note_lines = []
    for n in notes[-5:]:  # Last 5 notes
        note_lines.append(f"    [{n['timestamp'][:10]}] {n['text']}")

    lines = [
        f"📁 Project: {proj['name']}",
        f"  ID          : {proj['id']}",
        f"  Status      : {STATUS_EMOJI.get(proj.get('status','active'), '?')} {proj.get('status','active')}",
        f"  Language    : {proj.get('language') or 'not set'}",
        f"  Path        : {proj.get('path') or 'not set'}",
        f"  Description : {proj.get('description') or 'none'}",
        f"  Tags        : {', '.join(proj.get('tags', [])) or 'none'}",
        f"  Created     : {proj.get('created_at', '')[:19]}",
        f"  Last Opened : {proj.get('last_opened', '')[:19] or 'never'}",
        f"  Notes ({len(notes)}):",
    ]
    lines.extend(note_lines or ["    (none)"])
    return "\n".join(lines)


def _stats(projects: list) -> str:
    if not projects:
        return "📊 No projects registered."

    status_counts: dict = {s: 0 for s in VALID_STATUSES}
    lang_counts: dict = {}

    for p in projects:
        s = p.get("status", "active")
        status_counts[s] = status_counts.get(s, 0) + 1
        lang = p.get("language", "Unknown") or "Unknown"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    lines = [f"📊 Project Statistics ({len(projects)} total)\n", "  By Status:"]
    for status, emoji in STATUS_EMOJI.items():
        lines.append(f"    {emoji} {status.capitalize():<12}: {status_counts.get(status, 0)}")

    lines.append("\n  By Language:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        lines.append(f"    • {lang:<20}: {count}")

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def project_manager(parameters: dict, player=None, speak=None) -> str:
    """
    Development project tracker for JARVIS.

    Parameters
    ----------
    parameters : dict
        action      : str  – One of: add, list, open, set_status, note,
                             delete, info, stats
        name        : str  – Project name (add/open/set_status/note/delete/info)
        id          : str  – Project ID (alternative identifier)
        path        : str  – Filesystem path (add)
        description : str  – Short description (add)
        language    : str  – Programming language (add)
        tags        : list – Tag strings (add)
        status      : str  – active|paused|completed|archived (set_status/list)
        note        : str  – Note text to append (note)
    player : object, optional
        JARVIS player for write_log().
    speak : callable, optional
        TTS callback.

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        action = (parameters.get("action") or "list").strip().lower()
        print(f"[{MODULE}] Action: '{action}' | params: {parameters}")

        projects = _load()

        if action == "add":
            result = _add(parameters, projects)
        elif action == "list":
            result = _list(parameters, projects)
        elif action == "open":
            result = _open(parameters, projects)
        elif action == "set_status":
            result = _set_status(parameters, projects)
        elif action == "note":
            result = _note(parameters, projects)
        elif action == "delete":
            result = _delete(parameters, projects)
        elif action == "info":
            result = _info(parameters, projects)
        elif action == "stats":
            result = _stats(projects)
        else:
            result = (
                f"❓ Unknown action '{action}'. "
                "Valid: add, list, open, set_status, note, delete, info, stats"
            )

        if player and hasattr(player, "write_log"):
            player.write_log(f"[{MODULE}] {action}: {result[:120]}")
        if speak and callable(speak):
            speak(result)

        return result

    except Exception as exc:
        msg = f"[{MODULE}] Unexpected error: {exc}"
        print(msg)
        if player and hasattr(player, "write_log"):
            player.write_log(msg)
        return f"❌ Project manager error: {exc}"
