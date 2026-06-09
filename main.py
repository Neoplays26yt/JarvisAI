import asyncio
import re
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)
from agent.orchestrator import get_orchestrator_state, is_risky_action

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.stop_diagram      import stop_diagram
from actions.camera_control    import camera_control
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.github_automation import github_automation

# New actions (Phase 1: clipboard, monitor, terminal, focus)
try:
    from actions.clipboard_manager import clipboard_manager
    _HAS_CLIPBOARD = True
except ImportError:
    _HAS_CLIPBOARD = False
    clipboard_manager = None

try:
    from actions.system_monitor import system_monitor
    _HAS_MONITOR = True
except ImportError:
    _HAS_MONITOR = False
    system_monitor = None

try:
    from actions.terminal_agent import terminal_agent
    _HAS_TERMINAL = True
except ImportError:
    _HAS_TERMINAL = False
    terminal_agent = None

try:
    from actions.focus_mode import focus_mode
    _HAS_FOCUS = True
except ImportError:
    _HAS_FOCUS = False
    focus_mode = None

# New actions (Phase 2: workspace, macro, task, project, document, memory)
try:
    from actions.workspace_manager import workspace_manager
    _HAS_WORKSPACE = True
except ImportError:
    _HAS_WORKSPACE = False
    workspace_manager = None

try:
    from actions.macro_engine import macro_engine
    _HAS_MACRO = True
except ImportError:
    _HAS_MACRO = False
    macro_engine = None

try:
    from actions.task_manager import task_manager
    _HAS_TASKS = True
except ImportError:
    _HAS_TASKS = False
    task_manager = None

try:
    from actions.project_manager import project_manager
    _HAS_PROJECTS = True
except ImportError:
    _HAS_PROJECTS = False
    project_manager = None

try:
    from actions.document_assistant import document_assistant
    _HAS_DOCASSIST = True
except ImportError:
    _HAS_DOCASSIST = False
    document_assistant = None

try:
    from actions.workspace_memory import workspace_memory
    _HAS_WSMEM = True
except ImportError:
    _HAS_WSMEM = False
    workspace_memory = None


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("gemini_api_key", "").strip()
        if not key:
            raise ValueError("gemini_api_key is empty in api_keys.json")
        return key
    except FileNotFoundError:
        raise RuntimeError(
            f"API key file not found: {API_CONFIG_PATH}. "
            "Please complete the JARVIS initialisation first."
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"api_keys.json is corrupt: {exc}") from exc


_CACHED_PROMPT = None
def _load_system_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is not None:
        return _CACHED_PROMPT
    try:
        _CACHED_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
        return _CACHED_PROMPT
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
    "name": "camera_control",
    "description": "Interfaces with the webcam. Can start a live feed, stop it, take a photo, or record video.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start | stop | take_photo | start_recording | stop_recording"
            }
        },
        "required": ["action"]
    }
},
{
    "name": "screen_share_control",
    "description": "Interfaces with live screen sharing. Can start a live feed of the user's screen or stop it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start | stop"
            }
        },
        "required": ["action"]
    }
},
{
    "name": "activate_homework_mode",
    "description": "Activates homework assistant mode. Use this when the user uploads a homework assignment, asks for help with schoolwork, or provides an academic worksheet.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "subject": {
                "type": "STRING",
                "description": "The subject of the homework if known (e.g., Math, History)."
            }
        }
    }
},
    {
    "name": "system_specs",
    "description": "Returns detailed system specifications including CPU, RAM, OS, and Motherboard info.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
},
    {
        "name": "open_app",
        "description": (
            "Opens OR closes any application on the computer. "
            "Use action='open' to launch an app (default). "
            "Use action='close' to terminate/quit a running app. "
            "Always call this tool — never just say you opened or closed it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "open (default) | close"
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify', 'Discord')"
                }
            },
            "required": ["app_name"]
        }
    },

    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
                "visual": {"type": "BOOLEAN", "description": "Set to true if user wants to see results visually in a browser"},
                "auto_close": {"type": "INTEGER", "description": "Close browser after showing results for this many seconds (default 8). Pass 0 to leave open."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "stop_diagram",
        "description": "Closes the active live explanation diagram, mind map, or visual representation.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "open | list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": (
            "Advanced Developer Agent. Use for all coding tasks: "
            "write | edit | explain | run | build | optimize | screen_debug | "
            "review (code review: bugs/security/style) | "
            "debug (investigate bugs and errors) | "
            "document (add docstrings and README) | "
            "test (generate unit tests) | "
            "analyze (complexity metrics, patterns) | "
            "dependencies (import analysis) | "
            "architecture (project structure analysis). "
            "Use 'auto' to auto-detect the right action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | optimize | screen_debug | review | debug | document | test | analyze | dependencies | architecture | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do, problem description, or change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file"},
                "code":        {"type": "STRING", "description": "Raw code string for explain/review/analyze"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": []
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "tasks — pending to-dos, actionable items | "
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "confirm_action",
        "description": "Confirm the execution of a risky or destructive action that was previously pending.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "decision": {"type": "STRING", "description": "'proceed' or 'cancel'"}
            },
            "required": ["decision"]
        }
    },
    {
        "name": "github_automation",
        "description": (
            "Full Git and GitHub automation. Use for any git operation: "
            "init (create repo), scaffold (add .gitignore + README), "
            "status (check changes), add (stage files), commit (commit with message), "
            "push (push to remote), pull (pull from remote), log (commit history), "
            "branch (list or create branches), checkout (switch branch), "
            "diff (show changes), clone (clone repo), reset (reset to ref), "
            "stash (save/restore uncommitted work), remote_add (add remote URL)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "description": "init | scaffold | status | add | commit | push | pull | log | branch | checkout | diff | clone | reset | stash | remote_add"},
                "path":         {"type": "STRING", "description": "Local repository path (default: '.')"},
                "message":      {"type": "STRING", "description": "Commit message or stash message"},
                "files":        {"type": "STRING", "description": "Files to stage for add (default: '.')"},
                "remote":       {"type": "STRING", "description": "Remote name (default: 'origin')"},
                "branch":       {"type": "STRING", "description": "Branch name"},
                "name":         {"type": "STRING", "description": "New branch name or remote name"},
                "url":          {"type": "STRING", "description": "Repository URL for clone or remote_add"},
                "count":        {"type": "INTEGER", "description": "Number of log entries (default: 10)"},
                "create":       {"type": "BOOLEAN", "description": "Create new branch on checkout"},
                "staged":       {"type": "BOOLEAN", "description": "Show staged diff"},
                "mode":         {"type": "STRING", "description": "Reset mode: soft | mixed | hard"},
                "ref":          {"type": "STRING", "description": "Git ref for reset (default: HEAD)"},
                "stash_action": {"type": "STRING", "description": "push | pop | list | drop for stash"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "clipboard_manager",
        "description": "Manages the system clipboard: get current content, set text, clear, or access clipboard history.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "get | set | clear | history_add | history_list | history_clear"},
                "text":   {"type": "STRING", "description": "Text to set on clipboard"},
                "count":  {"type": "INTEGER", "description": "Number of history entries to show (default: 10)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_monitor",
        "description": "Real-time system monitoring: CPU, RAM, disk, processes, battery, temperature, uptime, startup apps.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "snapshot | processes | kill | battery | temperature | uptime | startup_apps"},
                "count":   {"type": "INTEGER", "description": "Number of processes to show (default: 10)"},
                "sort_by": {"type": "STRING", "description": "Sort processes by: cpu | memory (default: cpu)"},
                "name":    {"type": "STRING", "description": "Process name to kill"},
                "pid":     {"type": "INTEGER", "description": "Process PID to kill"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "terminal_agent",
        "description": "Safe terminal command executor. Runs whitelisted commands: git, pip, python, node, npm, dir/ls, etc. Blocks dangerous commands.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Shell command to execute"},
                "cwd":     {"type": "STRING", "description": "Working directory (default: home)"},
                "timeout": {"type": "INTEGER", "description": "Timeout in seconds (default: 30)"},
            },
            "required": ["command"]
        }
    },
    {
        "name": "focus_mode",
        "description": "Productivity focus mode: start a timed focus session, check time remaining, stop session, or schedule a break reminder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "start | status | stop | schedule_break"},
                "duration":   {"type": "INTEGER", "description": "Focus duration in minutes (default: 25)"},
                "goal":       {"type": "STRING", "description": "What you are focusing on"},
                "minutes":    {"type": "INTEGER", "description": "Minutes until break for schedule_break"},
                "close_apps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "App process names to close when starting focus"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "workspace_manager",
        "description": (
            "Manages named workspaces — sets of apps that open/close together. "
            "Use action='activate' to switch to a workspace (opens configured apps). "
            "Use action='list' to see all workspaces. "
            "Use action='create' to define a new workspace. "
            "Use action='info' to inspect a workspace. "
            "Use action='delete' to remove a workspace."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "activate | list | create | delete | info"},
                "name":        {"type": "STRING", "description": "Workspace name"},
                "description": {"type": "STRING", "description": "Workspace description (for create)"},
                "apps":        {"type": "STRING", "description": "Comma-separated app commands, or JSON array of {name, launch_cmd, path}"},
                "close_apps":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Process names to close on activate"},
                "directory":   {"type": "STRING", "description": "Default working directory"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "macro_engine",
        "description": (
            "Advanced automation ONLY. Records and replays sequences of JARVIS tool calls as named macros. "
            "DO NOT use this tool for normal queries, single-step actions, or basic scripting. "
            "ONLY use when the user EXPLICITLY asks to 'create a macro' or 'save this sequence'. "
            "Use action='list' to see macros. "
            "Use action='run' to execute a macro. "
            "Use action='create' to define a new macro with steps. "
            "Use action='delete' to remove a macro. "
            "Use action='info' to inspect steps of a macro."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | run | create | delete | info"},
                "name":        {"type": "STRING", "description": "Macro name"},
                "description": {"type": "STRING", "description": "Macro description (for create)"},
                "steps":       {"type": "STRING", "description": "JSON array of {tool, parameters} steps for create"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "task_manager",
        "description": (
            "Personal to-do and task management. "
            "add: create a task. list: view tasks (filter by status). start/complete: update status. "
            "delete: remove. search: find by keyword. stats: summary counts."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "add | list | start | complete | delete | clear_done | search | stats"},
                "title":       {"type": "STRING", "description": "Task title (for add)"},
                "description": {"type": "STRING", "description": "Task description"},
                "priority":    {"type": "STRING", "description": "low | normal | high (default: normal)"},
                "due_date":    {"type": "STRING", "description": "Due date (e.g. 2025-12-31)"},
                "id":          {"type": "STRING", "description": "Task ID or partial title for start/complete/delete"},
                "status":      {"type": "STRING", "description": "Filter for list: all | todo | in_progress | done"},
                "keyword":     {"type": "STRING", "description": "Search keyword"},
                "tags":        {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Task tags"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "project_manager",
        "description": (
            "Tracks development projects with paths, statuses, notes, and tags. "
            "add: register a project. list: view projects. open: open in VSCode. "
            "set_status: change status. note: add a note. delete: remove. info/stats: details."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "add | list | open | set_status | note | delete | info | stats"},
                "name":        {"type": "STRING", "description": "Project name or ID"},
                "path":        {"type": "STRING", "description": "Filesystem path to the project"},
                "description": {"type": "STRING", "description": "Project description"},
                "language":    {"type": "STRING", "description": "Primary language (python, js, etc.)"},
                "status":      {"type": "STRING", "description": "active | paused | completed | archived"},
                "note":        {"type": "STRING", "description": "Note text to add"},
                "tags":        {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Project tags"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "document_assistant",
        "description": (
            "AI-powered document writing and analysis. "
            "summarize: condense text. rewrite: change tone (professional/casual/formal). "
            "proofread: check grammar/spelling. expand: add detail. outline: create structure. "
            "email: draft an email. translate: convert to another language. "
            "extract_key_points: bullet-point summary."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":          {"type": "STRING", "description": "summarize | rewrite | proofread | expand | outline | email | translate | extract_key_points"},
                "text":            {"type": "STRING", "description": "Input text to process"},
                "file_path":       {"type": "STRING", "description": "Path to a file to read text from"},
                "tone":            {"type": "STRING", "description": "Tone for rewrite: professional | casual | formal | persuasive | concise"},
                "topic":           {"type": "STRING", "description": "Topic for outline action"},
                "target_language": {"type": "STRING", "description": "Target language for translate"},
                "recipient":       {"type": "STRING", "description": "Email recipient (for email action)"},
                "subject":         {"type": "STRING", "description": "Email subject"},
                "body_points":     {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Key points for email body"},
                "output_path":     {"type": "STRING", "description": "Path to save the output"},
                "save_output":     {"type": "BOOLEAN", "description": "Auto-save output to file"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "workspace_memory",
        "description": (
            "Contextual memory store for sessions and persistent context. "
            "remember/recall/forget: key-value context. learn: store a learned fact. "
            "log_session: record session summary. session_history: view past sessions. "
            "list_context/list_learned: browse stored data. stats: memory overview."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "remember | recall | forget | learn | list_context | list_learned | log_session | session_history | stats | clear_context"},
                "key":        {"type": "STRING", "description": "Context key for remember/recall/forget"},
                "value":      {"type": "STRING", "description": "Value to store for remember"},
                "fact":       {"type": "STRING", "description": "Fact to learn"},
                "confidence": {"type": "NUMBER", "description": "Confidence 0.0–1.0 for learn (default: 0.8)"},
                "summary":    {"type": "STRING", "description": "Session summary for log_session"},
                "tools_used": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Tools used in session"},
                "outcomes":   {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Session outcomes"},
                "count":      {"type": "INTEGER", "description": "Number of sessions to show"},
                "confirmed":  {"type": "BOOLEAN", "description": "Confirm destructive operations"},
            },
            "required": ["action"]
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR [{tool_name}]: {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")
        # Ensure state returns to listening after error notification
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        import platform
        os_ctx = (
            f"[SYSTEM SPECS]\n"
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n\n"
        )
        parts.append(os_ctx)
        if mem_str:
            parts.append(mem_str)
            
        orchestrator = get_orchestrator_state()
        if orchestrator.active_workspace:
            ws_ctx = f"[ACTIVE WORKSPACE]\n{json.dumps(orchestrator.active_workspace, indent=2)}\n\n"
            parts.append(ws_ctx)
            
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 TOOL_START  name={name}  args={json.dumps(args, ensure_ascii=False)[:200]}")
        self.ui.set_state("THINKING")
        self.ui.write_log(f"SYS: Running {name}…")

        # ── save_memory: fire-and-forget, no state change needed ──────────────
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 SAVED  {category}/{key} = {value[:60]}")
            # Restore state immediately — this is a silent background op
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        orchestrator = get_orchestrator_state()

        # ── confirm_action: resolve pending risky action ───────────────────────
        if name == "confirm_action":
            decision = args.get("decision", "cancel")
            if decision == "proceed" and orchestrator.pending_confirmation:
                pending = orchestrator.pending_confirmation
                print(f"[Orchestrator] 🔓 CONFIRMED  tool={pending['tool_name']}")
                self.ui.write_log(f"SYS: Action confirmed — executing {pending['tool_name']}")
                name = pending['tool_name']
                args = pending['args']
                orchestrator.clear_confirmation()
                # Fall through to normal execution below
            else:
                orchestrator.clear_confirmation()
                self.ui.write_log("SYS: Action cancelled by user.")
                print("[Orchestrator] 🚫 CANCELLED  pending action")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": "Action cancelled by user."}
                )

        # ── Risk gate ─────────────────────────────────────────────────────────
        if is_risky_action(name, args):
            already_pending = (
                orchestrator.pending_confirmation
                and orchestrator.pending_confirmation.get('tool_name') == name
            )
            if not already_pending:
                msg = orchestrator.require_confirmation(name, args)
                print(f"[Orchestrator] 🛑 BLOCKED  risky tool='{name}' — awaiting confirmation")
                self.ui.write_log(f"SYS: Confirmation required for {name}")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": msg}
                )

        loop   = asyncio.get_event_loop()
        result = "Done."
        tool_success = True

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "stop_diagram":
                r = await loop.run_in_executor(None, lambda: stop_diagram(parameters=args, player=self.ui))
                result = r or "Diagram closed."

            elif name == "camera_control":
                r = await loop.run_in_executor(None, lambda: camera_control(parameters=args, player=self.ui))
                result = r or "Camera command executed."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                # Vision runs in a daemon thread; UI returns to LISTENING after launch
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                queue = get_queue()
                # Wire UI log callback once so task events appear in the activity log
                queue.set_log_callback(self.ui.write_log)
                task_id  = queue.submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "screen_share_control":
                from actions.screen_share import screen_share_control
                r = await loop.run_in_executor(None, lambda: screen_share_control(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "activate_homework_mode":
                from actions.homework_assistant import activate_homework_mode
                r = await loop.run_in_executor(None, lambda: activate_homework_mode(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "system_specs":
                from actions.system_specs import get_system_specs
                r = await loop.run_in_executor(None, lambda: get_system_specs(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: JARVIS shutdown initiated.")
                print("[JARVIS] 🔴 SHUTDOWN requested")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1.5)
                    # Flush Qt event loop cleanly before exit using main thread
                    from PySide6.QtWidgets import QApplication
                    from PySide6.QtCore import QMetaObject, Qt
                    try:
                        self.ui.hide_media() # Stop camera explicitly
                    except: pass
                    app = QApplication.instance()
                    if app:
                        QMetaObject.invokeMethod(app, "quit", Qt.ConnectionType.QueuedConnection)
                        time.sleep(1.0)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            elif name == "github_automation":
                r = await loop.run_in_executor(None, lambda: github_automation(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Done."

            elif name == "clipboard_manager":
                if _HAS_CLIPBOARD and clipboard_manager:
                    r = await loop.run_in_executor(None, lambda: clipboard_manager(parameters=args, player=self.ui))
                    result = r or "Done."
                else:
                    result = "Clipboard manager is not available. Run: pip install pyperclip"

            elif name == "system_monitor":
                if _HAS_MONITOR and system_monitor:
                    r = await loop.run_in_executor(None, lambda: system_monitor(parameters=args, player=self.ui))
                    result = r or "Done."
                else:
                    result = "System monitor is not available. Run: pip install psutil"

            elif name == "terminal_agent":
                if _HAS_TERMINAL and terminal_agent:
                    r = await loop.run_in_executor(None, lambda: terminal_agent(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Terminal agent module is not available."

            elif name == "focus_mode":
                if _HAS_FOCUS and focus_mode:
                    r = await loop.run_in_executor(None, lambda: focus_mode(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Focus mode module is not available."

            elif name == "workspace_manager":
                if _HAS_WORKSPACE and workspace_manager:
                    r = await loop.run_in_executor(None, lambda: workspace_manager(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Workspace manager is not available."

            elif name == "macro_engine":
                if _HAS_MACRO and macro_engine:
                    r = await loop.run_in_executor(None, lambda: macro_engine(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Macro engine is not available."

            elif name == "task_manager":
                if _HAS_TASKS and task_manager:
                    r = await loop.run_in_executor(None, lambda: task_manager(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Task manager is not available."

            elif name == "project_manager":
                if _HAS_PROJECTS and project_manager:
                    r = await loop.run_in_executor(None, lambda: project_manager(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Project manager is not available."

            elif name == "document_assistant":
                if _HAS_DOCASSIST and document_assistant:
                    r = await loop.run_in_executor(None, lambda: document_assistant(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Document assistant is not available."

            elif name == "workspace_memory":
                if _HAS_WSMEM and workspace_memory:
                    r = await loop.run_in_executor(None, lambda: workspace_memory(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."
                else:
                    result = "Workspace memory is not available."

            else:
                result = f"Unknown tool: {name}"
                tool_success = False

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            tool_success = False
            traceback.print_exc()
            self.speak_error(name, e)

        # ── Always restore UI state after tool completes ───────────────────────
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        # ── Structured log entry for every tool result ─────────────────────────
        status_icon = "✓" if tool_success else "✗"
        result_short = str(result)[:120].replace("\n", " ")
        print(f"[JARVIS] 📤 TOOL_END  name={name}  status={'ok' if tool_success else 'err'}  result={result_short}")
        self.ui.write_log(f"{status_icon} {name}: {result_short}")

        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                import re
                                match = re.search(r'```mermaid\n(.*?)```', full_out, re.DOTALL)
                                if match:
                                    self.ui.show_diagram(match.group(1).strip())
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=0,
            latency="high",
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        try:
            api_key = _get_api_key()
        except RuntimeError as exc:
            self.ui.write_log(f"ERR: {exc}")
            self.ui.set_state("ERROR")
            print(f"[JARVIS] ❌ STARTUP_FAIL  {exc}")
            return  # Cannot proceed without a valid API key

        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )

        reconnect_count = 0
        while True:
            try:
                print(f"[JARVIS] 🔌 CONNECT_ATTEMPT  #{reconnect_count + 1}")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()
                    reconnect_count       = 0  # reset on successful connection

                    print("[JARVIS] ✅ CONNECTED")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                reconnect_count += 1
                print(f"[JARVIS] ⚠️ SESSION_ERROR  #{reconnect_count}  {e}")
                traceback.print_exc()

            # ── Clean disconnect: stop speaking, show RECONNECTING state ────────
            self.set_speaking(False)
            self.ui.set_state("RECONNECTING")
            delay = min(3 * reconnect_count, 30)  # back-off up to 30s
            print(f"[JARVIS] 🔄 RECONNECT_WAIT  {delay}s  (attempt #{reconnect_count + 1})")
            self.ui.write_log(f"SYS: Reconnecting in {delay}s…")
            await asyncio.sleep(max(delay, 3))

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
