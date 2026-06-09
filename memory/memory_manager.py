import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "tasks":         {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                # ── Prune stale task entries (older than 30 days) ──────────────
                data = _prune_stale_tasks(data)
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


# ── Stale task cleanup ───────────────────────────────────────────────────
TASK_MAX_AGE_DAYS = 30


def _prune_stale_tasks(memory: dict) -> dict:
    """Remove task entries whose 'updated' date is older than TASK_MAX_AGE_DAYS."""
    tasks = memory.get("tasks", {})
    if not tasks:
        return memory
    cutoff = datetime.now()
    stale_keys = []
    for key, entry in tasks.items():
        if not isinstance(entry, dict):
            continue
        updated_str = entry.get("updated", "")
        if not updated_str:
            continue
        try:
            updated_date = datetime.strptime(updated_str, "%Y-%m-%d")
            age_days = (cutoff - updated_date).days
            if age_days > TASK_MAX_AGE_DAYS:
                stale_keys.append(key)
        except ValueError:
            pass
    for key in stale_keys:
        del memory["tasks"][key]
        print(f"[Memory] 👤 Pruned stale task: tasks/{key} (age > {TASK_MAX_AGE_DAYS}d)")
    return memory


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    import difflib
    from datetime import datetime
    changed = False
    for k, v in updates.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, dict) and "value" not in v:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
                changed = True
            if _recursive_update(target[k], v):
                changed = True
        else:
            new_val = _truncate_value(str(v["value"] if isinstance(v, dict) else v))
            
            # Semantic Deduplication
            is_dup = False
            for e_k, e_v in target.items():
                e_val_str = str(e_v.get("value", e_v) if isinstance(e_v, dict) else e_v)
                if difflib.SequenceMatcher(None, new_val.lower(), e_val_str.lower()).ratio() > 0.85:
                    is_dup = True
                    break
                    
            if not is_dup:
                entry = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
                target[k] = entry
                changed = True
            else:
                print(f"[Memory] [SKIPPED] Duplicate semantic memory prevented: '{new_val}'")
    return changed


def _is_transient_noise(val: str) -> bool:
    import re
    if len(val) < 3:
        return True
    val_lower = val.lower().strip()
    # Exact match for common noise
    exact_noise = {"hi", "hello", "how are you", "weather", "goodbye", "thanks", "ok", "yes", "no", "sure", "done"}
    if val_lower in exact_noise:
        return True
    
    # Regex heuristics for transient chat patterns
    noise_patterns = [
        r"^(can you|could you|please)\s",
        r"^(what is|who is|where is|when is)\s",
        r"^user (said|asked)\s",
        r"^thank you",
        r"^(ok|okay|alright)\b"
    ]
    for p in noise_patterns:
        if re.search(p, val_lower):
            return True
    return False

def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
        
    valid_categories = {"identity", "preferences", "projects", "tasks", "relationships", "wishes", "notes"}
    filtered_update = {}
    
    for cat, items in memory_update.items():
        if cat not in valid_categories:
            print(f"[Memory] [REJECTED] Invalid category: {cat}")
            continue
        if isinstance(items, dict):
            valid_items = {}
            for k, v in items.items():
                val_str = v.get("value", "") if isinstance(v, dict) else str(v)
                if cat in ('projects', 'tasks') or not _is_transient_noise(val_str):
                    valid_items[k] = v
                else:
                    print(f"[Memory] [REJECTED] Transient noise for {cat}/{k}: {val_str}")
            if valid_items:
                filtered_update[cat] = valid_items

    if not filtered_update:
        return load_memory()

    memory = load_memory()
    if _recursive_update(memory, filtered_update):
        save_memory(memory)
        print(f"[Memory] [SAVED] {list(filtered_update.keys())}")
    return memory

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    tasks = memory.get("tasks", {})
    if tasks:
        lines.append("")
        lines.append("Pending Tasks / To-dos:")
        for key, entry in list(tasks.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "tasks", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget
