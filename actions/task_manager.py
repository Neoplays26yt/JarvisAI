"""
task_manager.py — Personal Task/To-Do Management System for JARVIS
===================================================================
Manages a persistent list of tasks stored in ~/.jarvis/tasks.json.

Entry point:
    task_manager(parameters: dict, player=None, speak=None) -> str

Supported actions (parameters['action']):
    add          – Create a new task
    list         – List tasks, optionally filtered by status
    start        – Mark a task as in_progress
    complete     – Mark a task as done
    delete       – Remove a task
    clear_done   – Purge all completed tasks
    search       – Full-text search across title and description
    stats        – Summary counts and breakdowns

Data file: ~/.jarvis/tasks.json
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
MODULE = "Tasks"
DATA_DIR = Path.home() / ".jarvis"
DATA_FILE = DATA_DIR / "tasks.json"

VALID_STATUSES = {"todo", "in_progress", "done"}
VALID_PRIORITIES = {"low", "normal", "high"}

PRIORITY_EMOJI = {"low": "🟢", "normal": "🟡", "high": "🔴"}
STATUS_EMOJI = {"todo": "📋", "in_progress": "🔄", "done": "✅"}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load() -> list:
    """Load tasks from disk; return empty list if file absent or corrupt."""
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[{MODULE}] WARNING: could not read {DATA_FILE}: {exc}")
        return []


def _save(tasks: list) -> None:
    """Atomically persist task list to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(tasks, fh, indent=2, ensure_ascii=False)
    tmp.replace(DATA_FILE)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().isoformat()


# ── Match helpers ─────────────────────────────────────────────────────────────

def _find_task(tasks: list, query: str):
    """Return first task whose id or title (case-insensitive) matches query."""
    # Exact id match first
    for t in tasks:
        if t["id"] == query:
            return t
    # Partial title match
    ql = query.lower()
    for t in tasks:
        if ql in t["title"].lower():
            return t
    return None


# ── Action handlers ───────────────────────────────────────────────────────────

def _add(parameters: dict, tasks: list) -> str:
    title = (parameters.get("title") or "").strip()
    if not title:
        return "❌ 'title' is required to add a task."

    priority = parameters.get("priority", "normal").lower()
    if priority not in VALID_PRIORITIES:
        priority = "normal"

    task = {
        "id": _new_id(),
        "title": title,
        "description": parameters.get("description", ""),
        "status": "todo",
        "priority": priority,
        "created_at": _now(),
        "due_date": parameters.get("due_date", ""),
        "tags": parameters.get("tags", []),
    }
    tasks.append(task)
    _save(tasks)
    print(f"[{MODULE}] Added task '{title}' (id={task['id']})")
    return (
        f"✅ Task added!\n"
        f"  ID       : {task['id']}\n"
        f"  Title    : {task['title']}\n"
        f"  Priority : {PRIORITY_EMOJI[priority]} {priority}\n"
        f"  Due      : {task['due_date'] or 'not set'}"
    )


def _list(parameters: dict, tasks: list) -> str:
    status_filter = parameters.get("status", "all").lower()
    if status_filter != "all" and status_filter not in VALID_STATUSES:
        status_filter = "all"

    filtered = [
        t for t in tasks
        if status_filter == "all" or t["status"] == status_filter
    ]

    if not filtered:
        return f"📭 No tasks found (filter: {status_filter})."

    lines = [f"📝 Tasks ({status_filter}) — {len(filtered)} item(s):\n"]
    for idx, t in enumerate(filtered, 1):
        due = f" | due: {t['due_date']}" if t.get("due_date") else ""
        tags = f" | tags: {', '.join(t['tags'])}" if t.get("tags") else ""
        lines.append(
            f"  {idx}. [{t['id']}] {STATUS_EMOJI.get(t['status'], '?')} "
            f"{PRIORITY_EMOJI.get(t['priority'], '')} {t['title']}"
            f"{due}{tags}"
        )
        if t.get("description"):
            lines.append(f"       {t['description'][:80]}")
    return "\n".join(lines)


def _set_status(parameters: dict, tasks: list, new_status: str) -> str:
    query = (parameters.get("id") or parameters.get("title") or "").strip()
    if not query:
        return "❌ Provide 'id' or 'title' to identify the task."

    task = _find_task(tasks, query)
    if task is None:
        return f"❌ No task found matching '{query}'."

    old = task["status"]
    task["status"] = new_status
    _save(tasks)
    print(f"[{MODULE}] Task '{task['title']}' ({task['id']}): {old} → {new_status}")
    label = {"in_progress": "🔄 Started", "done": "✅ Completed"}.get(new_status, new_status)
    return f"{label}: [{task['id']}] {task['title']}"


def _delete(parameters: dict, tasks: list) -> str:
    query = (parameters.get("id") or parameters.get("title") or "").strip()
    if not query:
        return "❌ Provide 'id' or 'title' to identify the task."

    task = _find_task(tasks, query)
    if task is None:
        return f"❌ No task found matching '{query}'."

    tasks.remove(task)
    _save(tasks)
    print(f"[{MODULE}] Deleted task '{task['title']}' ({task['id']})")
    return f"🗑️ Deleted task: [{task['id']}] {task['title']}"


def _clear_done(tasks: list) -> str:
    before = len(tasks)
    remaining = [t for t in tasks if t["status"] != "done"]
    removed = before - len(remaining)
    if removed == 0:
        return "ℹ️ No completed tasks to clear."
    _save(remaining)
    print(f"[{MODULE}] Cleared {removed} done task(s)")
    return f"🧹 Removed {removed} completed task(s). {len(remaining)} task(s) remaining."


def _search(parameters: dict, tasks: list) -> str:
    keyword = (parameters.get("keyword") or parameters.get("query") or "").strip().lower()
    if not keyword:
        return "❌ Provide 'keyword' to search."

    matches = [
        t for t in tasks
        if keyword in t["title"].lower() or keyword in t.get("description", "").lower()
    ]
    if not matches:
        return f"🔍 No tasks found matching '{keyword}'."

    lines = [f"🔍 Search results for '{keyword}' — {len(matches)} match(es):\n"]
    for t in matches:
        lines.append(
            f"  [{t['id']}] {STATUS_EMOJI.get(t['status'], '?')} "
            f"{PRIORITY_EMOJI.get(t['priority'], '')} {t['title']} "
            f"({t['status']})"
        )
    return "\n".join(lines)


def _stats(tasks: list) -> str:
    if not tasks:
        return "📊 No tasks in the system."

    status_counts = {"todo": 0, "in_progress": 0, "done": 0}
    priority_counts = {"low": 0, "normal": 0, "high": 0}
    overdue = 0
    now_str = _now()

    for t in tasks:
        status_counts[t.get("status", "todo")] += 1
        priority_counts[t.get("priority", "normal")] += 1
        due = t.get("due_date", "")
        if due and t["status"] != "done" and due < now_str:
            overdue += 1

    total = len(tasks)
    lines = [
        f"📊 Task Statistics ({total} total)\n",
        "  Status breakdown:",
        f"    📋 Todo       : {status_counts['todo']}",
        f"    🔄 In Progress: {status_counts['in_progress']}",
        f"    ✅ Done       : {status_counts['done']}",
        "",
        "  Priority breakdown:",
        f"    🔴 High       : {priority_counts['high']}",
        f"    🟡 Normal     : {priority_counts['normal']}",
        f"    🟢 Low        : {priority_counts['low']}",
        "",
        f"  ⚠️  Overdue     : {overdue}",
    ]
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def task_manager(parameters: dict, player=None, speak=None) -> str:
    """
    Personal task management system for JARVIS.

    Parameters
    ----------
    parameters : dict
        action   : str  – One of: add, list, start, complete, delete,
                          clear_done, search, stats
        title    : str  – Task title (add/start/complete/delete)
        id       : str  – Task ID (start/complete/delete)
        description : str  – Task description (add)
        priority : str  – low | normal | high (add)
        due_date : str  – ISO date string (add)
        tags     : list – List of tag strings (add)
        status   : str  – Filter for list: all | todo | in_progress | done
        keyword  : str  – Search keyword (search)
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

        tasks = _load()

        if action == "add":
            result = _add(parameters, tasks)
        elif action == "list":
            result = _list(parameters, tasks)
        elif action == "start":
            result = _set_status(parameters, tasks, "in_progress")
        elif action == "complete":
            result = _set_status(parameters, tasks, "done")
        elif action == "delete":
            result = _delete(parameters, tasks)
        elif action == "clear_done":
            result = _clear_done(tasks)
        elif action == "search":
            result = _search(parameters, tasks)
        elif action == "stats":
            result = _stats(tasks)
        else:
            result = (
                f"❓ Unknown action '{action}'. "
                "Valid: add, list, start, complete, delete, clear_done, search, stats"
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
        return f"❌ Task manager error: {exc}"
