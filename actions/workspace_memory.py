"""
workspace_memory.py — Contextual Memory Store for JARVIS Sessions
==================================================================
Provides a persistent, structured memory layer that stores context snippets,
learned facts, and session summaries across JARVIS interactions.

Entry point:
    workspace_memory(parameters: dict, player=None, speak=None) -> str

Supported actions (parameters['action']):
    remember       – Store a context key-value pair
    recall         – Retrieve a context item by key (fuzzy fallback)
    forget         – Delete a context item by key
    learn          – Record a learned fact with confidence score
    list_context   – List all context keys with value previews
    list_learned   – List all learned facts sorted by confidence
    log_session    – Log a session summary entry
    session_history– Show last N session summaries
    stats          – Show memory statistics
    clear_context  – Wipe all context (requires confirmed=True)

Data file: ~/.jarvis/workspace_memory.json
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
MODULE = "WorkspaceMem"
DATA_DIR = Path.home() / ".jarvis"
DATA_FILE = DATA_DIR / "workspace_memory.json"

PREVIEW_LEN = 60  # Characters to show in key previews


# ── Data structure ────────────────────────────────────────────────────────────

def _empty_store() -> dict:
    """Return a fresh, empty memory store."""
    return {
        "sessions": [],
        "context": {},
        "learned": [],
    }


# ── Atomic I/O ────────────────────────────────────────────────────────────────

def _load() -> dict:
    """
    Load the memory store from disk.
    Returns an empty store if the file is missing or corrupt.
    """
    if not DATA_FILE.exists():
        return _empty_store()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        # Ensure required top-level keys exist
        store = _empty_store()
        store.update(data)
        return store
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[{MODULE}] WARNING: could not read {DATA_FILE}: {exc}")
        return _empty_store()


def _save(store: dict) -> None:
    """
    Atomically persist the memory store to disk.
    Writes to a .tmp file first, then renames to prevent corruption.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, ensure_ascii=False)
    tmp.replace(DATA_FILE)


def _now() -> str:
    return datetime.now().isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# ── Fuzzy key matching ────────────────────────────────────────────────────────

def _fuzzy_key(context: dict, query: str):
    """
    Find the best matching context key.
    Priority: exact > starts-with > contains (case-insensitive).
    Returns (matched_key, match_type) or (None, None).
    """
    ql = query.lower()
    # Exact
    if query in context:
        return query, "exact"
    # Case-insensitive exact
    for k in context:
        if k.lower() == ql:
            return k, "exact"
    # Starts-with
    for k in context:
        if k.lower().startswith(ql):
            return k, "starts-with"
    # Contains
    for k in context:
        if ql in k.lower():
            return k, "contains"
    return None, None


# ── Action handlers ───────────────────────────────────────────────────────────

def _remember(parameters: dict, store: dict) -> str:
    key = (parameters.get("key") or "").strip()
    value = parameters.get("value")

    if not key:
        return "❌ 'key' is required for the remember action."
    if value is None:
        return "❌ 'value' is required for the remember action."

    existed = key in store["context"]
    store["context"][key] = {
        "value": value,
        "created_at": store["context"][key].get("created_at", _now()) if existed else _now(),
        "last_accessed": _now(),
    }
    _save(store)
    verb = "Updated" if existed else "Stored"
    print(f"[{MODULE}] {verb} context key: '{key}'")
    preview = str(value)[:PREVIEW_LEN]
    return f"🧠 {verb} memory: [{key}] → {preview}{'…' if len(str(value)) > PREVIEW_LEN else ''}"


def _recall(parameters: dict, store: dict) -> str:
    key = (parameters.get("key") or "").strip()
    if not key:
        return "❌ 'key' is required for the recall action."

    context = store["context"]

    # Exact match
    if key in context:
        item = context[key]
        item["last_accessed"] = _now()
        _save(store)
        print(f"[{MODULE}] Recalled key: '{key}'")
        return f"🔍 [{key}]\n  Value       : {item['value']}\n  Stored      : {item.get('created_at','')[:19]}\n  Last Accessed: {item['last_accessed'][:19]}"

    # Fuzzy fallback
    matched_key, match_type = _fuzzy_key(context, key)
    if matched_key:
        item = context[matched_key]
        item["last_accessed"] = _now()
        _save(store)
        print(f"[{MODULE}] Fuzzy-recalled '{matched_key}' for query '{key}' ({match_type})")
        return (
            f"🔍 No exact match for '{key}'. Found via {match_type}: [{matched_key}]\n"
            f"  Value       : {item['value']}\n"
            f"  Stored      : {item.get('created_at','')[:19]}\n"
            f"  Last Accessed: {item['last_accessed'][:19]}"
        )

    return f"❓ No context found for '{key}'. Use 'remember' to store it."


def _forget(parameters: dict, store: dict) -> str:
    key = (parameters.get("key") or "").strip()
    if not key:
        return "❌ 'key' is required for the forget action."

    if key in store["context"]:
        del store["context"][key]
        _save(store)
        print(f"[{MODULE}] Forgot context key: '{key}'")
        return f"🗑️ Forgotten: [{key}]"

    # Try fuzzy
    matched_key, match_type = _fuzzy_key(store["context"], key)
    if matched_key:
        del store["context"][matched_key]
        _save(store)
        print(f"[{MODULE}] Forgot fuzzy key '{matched_key}' (query: '{key}')")
        return f"🗑️ Forgotten (matched via {match_type}): [{matched_key}]"

    return f"❓ No context key found matching '{key}'."


def _learn(parameters: dict, store: dict) -> str:
    fact = (parameters.get("fact") or "").strip()
    if not fact:
        return "❌ 'fact' is required for the learn action."

    raw_confidence = parameters.get("confidence", 0.8)
    try:
        confidence = float(raw_confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.8

    source = (parameters.get("source") or "user").strip()

    entry = {
        "id": _new_id(),
        "fact": fact,
        "confidence": confidence,
        "source": source,
        "timestamp": _now(),
    }
    store["learned"].append(entry)
    _save(store)
    print(f"[{MODULE}] Learned fact (confidence={confidence:.2f}): {fact[:60]}")
    return (
        f"📚 Learned!\n"
        f"  Fact       : {fact}\n"
        f"  Confidence : {confidence:.0%}\n"
        f"  Source     : {source}"
    )


def _list_context(store: dict) -> str:
    context = store["context"]
    if not context:
        return "🧠 No context stored. Use 'remember' to add items."

    lines = [f"🧠 Context Store — {len(context)} item(s):\n"]
    for key, item in sorted(context.items()):
        preview = str(item.get("value", ""))[:PREVIEW_LEN]
        ellipsis = "…" if len(str(item.get("value", ""))) > PREVIEW_LEN else ""
        accessed = item.get("last_accessed", "")[:10]
        lines.append(f"  [{key}]  →  {preview}{ellipsis}  (accessed: {accessed})")
    return "\n".join(lines)


def _list_learned(store: dict) -> str:
    learned = store["learned"]
    if not learned:
        return "📚 No learned facts yet. Use 'learn' to add facts."

    sorted_facts = sorted(learned, key=lambda x: x.get("confidence", 0), reverse=True)
    lines = [f"📚 Learned Facts — {len(learned)} item(s) (sorted by confidence):\n"]
    for f in sorted_facts:
        conf = f.get("confidence", 0)
        bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
        ts = f.get("timestamp", "")[:10]
        lines.append(f"  [{bar}] {conf:.0%}  {f['fact']}")
        lines.append(f"          source: {f.get('source','')} | {ts}")
    return "\n".join(lines)


def _log_session(parameters: dict, store: dict) -> str:
    summary = (parameters.get("summary") or "").strip()
    if not summary:
        return "❌ 'summary' is required for log_session."

    session = {
        "id": _new_id(),
        "timestamp": _now(),
        "summary": summary,
        "tags": parameters.get("tags", []),
        "tools_used": parameters.get("tools_used", []),
        "outcomes": parameters.get("outcomes", []),
    }
    store["sessions"].append(session)
    _save(store)
    print(f"[{MODULE}] Session logged (id={session['id']})")
    return (
        f"📓 Session logged!\n"
        f"  ID       : {session['id']}\n"
        f"  Summary  : {summary[:80]}\n"
        f"  Tags     : {', '.join(session['tags']) or 'none'}\n"
        f"  Tools    : {', '.join(session['tools_used']) or 'none'}"
    )


def _session_history(parameters: dict, store: dict) -> str:
    count = parameters.get("count", 5)
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 5

    sessions = store["sessions"]
    if not sessions:
        return "📓 No sessions logged yet."

    recent = sessions[-count:][::-1]  # Most recent first
    lines = [f"📓 Last {len(recent)} session(s):\n"]
    for s in recent:
        ts = s.get("timestamp", "")[:19].replace("T", " ")
        tags = f"  tags: {', '.join(s.get('tags',[]))}" if s.get("tags") else ""
        outcomes = s.get("outcomes", [])
        lines.append(f"  [{s.get('id','')}] {ts}")
        lines.append(f"    {s.get('summary','')}")
        if tags:
            lines.append(f"    {tags}")
        if outcomes:
            lines.append(f"    outcomes: {'; '.join(str(o) for o in outcomes)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _stats(store: dict) -> str:
    ctx_count = len(store["context"])
    learned_count = len(store["learned"])
    session_count = len(store["sessions"])

    # Average confidence of learned facts
    confidences = [f.get("confidence", 0) for f in store["learned"]]
    avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

    # Most recently accessed context key
    recent_key = ""
    recent_ts = ""
    for k, item in store["context"].items():
        ts = item.get("last_accessed", "")
        if ts > recent_ts:
            recent_ts = ts
            recent_key = k

    lines = [
        "🧠 Workspace Memory Statistics",
        "",
        f"  Context items   : {ctx_count}",
        f"  Learned facts   : {learned_count}",
        f"  Avg confidence  : {avg_conf:.0%}" if learned_count else "  Avg confidence  : N/A",
        f"  Sessions logged : {session_count}",
        f"  Last accessed   : [{recent_key}] at {recent_ts[:19]}" if recent_key else "  Last accessed   : N/A",
        f"  Data file       : {DATA_FILE}",
    ]
    return "\n".join(lines)


def _clear_context(parameters: dict, store: dict) -> str:
    confirmed = parameters.get("confirmed", False)
    if not confirmed:
        count = len(store["context"])
        return (
            f"⚠️ This will delete ALL {count} context item(s). "
            "Pass confirmed=True to proceed."
        )
    count = len(store["context"])
    store["context"] = {}
    _save(store)
    print(f"[{MODULE}] Cleared {count} context item(s)")
    return f"🧹 Cleared {count} context item(s). Sessions and learned facts are unaffected."


# ── Entry point ───────────────────────────────────────────────────────────────

def workspace_memory(parameters: dict, player=None, speak=None) -> str:
    """
    Contextual memory store for JARVIS workspaces and sessions.

    Parameters
    ----------
    parameters : dict
        action      : str   – remember | recall | forget | learn |
                              list_context | list_learned | log_session |
                              session_history | stats | clear_context
        key         : str   – Context key (remember / recall / forget)
        value       : any   – Context value (remember)
        fact        : str   – Fact to learn (learn)
        confidence  : float – Confidence score 0.0-1.0 (learn, default 0.8)
        source      : str   – Source of fact (learn, default 'user')
        summary     : str   – Session summary (log_session)
        tags        : list  – Tags for session (log_session)
        tools_used  : list  – Tools used in session (log_session)
        outcomes    : list  – Session outcomes (log_session)
        count       : int   – Number of sessions to show (session_history, default 5)
        confirmed   : bool  – Confirmation flag for destructive ops (clear_context)
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
        action = (parameters.get("action") or "stats").strip().lower()
        print(f"[{MODULE}] Action: '{action}' | params keys: {list(parameters.keys())}")

        store = _load()

        if action == "remember":
            result = _remember(parameters, store)
        elif action == "recall":
            result = _recall(parameters, store)
        elif action == "forget":
            result = _forget(parameters, store)
        elif action == "learn":
            result = _learn(parameters, store)
        elif action == "list_context":
            result = _list_context(store)
        elif action == "list_learned":
            result = _list_learned(store)
        elif action == "log_session":
            result = _log_session(parameters, store)
        elif action == "session_history":
            result = _session_history(parameters, store)
        elif action == "stats":
            result = _stats(store)
        elif action == "clear_context":
            result = _clear_context(parameters, store)
        else:
            result = (
                f"❓ Unknown action '{action}'. "
                "Valid: remember, recall, forget, learn, list_context, "
                "list_learned, log_session, session_history, stats, clear_context"
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
        return f"❌ Workspace memory error: {exc}"
