"""
document_assistant.py — AI-Powered Document Writing Assistant for JARVIS
=========================================================================
Uses Google Gemini AI to perform document operations: summarize, rewrite,
proofread, expand, outline, draft emails, translate, and extract key points.

Entry point:
    document_assistant(parameters: dict, player=None, speak=None) -> str

Supported actions (parameters['action']):
    summarize          – Produce a 3-5 sentence summary
    rewrite            – Rewrite text in a specified tone
    proofread          – Identify grammar/spelling/punctuation errors
    expand             – Flesh out a brief piece of text
    outline            – Generate a structured outline for a topic
    email              – Draft a professional email
    translate          – Translate text to a target language
    extract_key_points – Extract key points as a bulleted list
    save               – Save the last produced result to disk

API key source: c:/Users/kavs1/OneDrive/Desktop/Jarvis-main/config/api_keys.json
Model: gemini-2.5-flash
"""

import json
import textwrap
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
MODULE = "DocAssist"
API_KEYS_PATH = Path(r"c:\Users\kavs1\OneDrive\Desktop\Jarvis-main\config\api_keys.json")
DEFAULT_OUTPUT = Path.home() / "Desktop" / "jarvis_document.txt"
MODEL_NAME = "gemini-2.5-flash"

VALID_TONES = {"professional", "casual", "formal", "persuasive", "concise"}

# Module-level cache for the last AI result (enables the 'save' action)
_last_result: dict = {"action": "", "content": ""}


# ── API / client helpers ──────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Read gemini_api_key from api_keys.json; raise RuntimeError on failure."""
    if not API_KEYS_PATH.exists():
        raise RuntimeError(f"API keys file not found: {API_KEYS_PATH}")
    try:
        with API_KEYS_PATH.open("r", encoding="utf-8") as fh:
            keys = json.load(fh)
        key = keys.get("gemini_api_key", "").strip()
        if not key:
            raise RuntimeError("'gemini_api_key' is empty in api_keys.json")
        return key
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed api_keys.json: {exc}") from exc


def _get_model():
    """Initialise and return a Gemini GenerativeModel instance."""
    from google import genai  # noqa: PLC0415
    api_key = _load_api_key()
    client = genai.Client(api_key=api_key)
    return genai.Client(api_key=_get_api_key()), MODEL_NAME


def _ask(prompt: str) -> str:
    """Send prompt to Gemini and return the text response."""
    model = _get_model()
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    # Safely extract text from response
    if hasattr(response, "text"):
        return response.text.strip()
    if hasattr(response, "parts"):
        return "".join(part.text for part in response.parts).strip()
    return str(response)


# ── Text / file loading ───────────────────────────────────────────────────────

def _get_text(parameters: dict) -> str:
    """
    Retrieve text from parameters['text'] or read from parameters['file_path'].
    Raise ValueError if neither is provided or the file is unreadable.
    """
    text = (parameters.get("text") or "").strip()
    if text:
        return text

    file_path = (parameters.get("file_path") or "").strip()
    if file_path:
        fp = Path(file_path)
        if not fp.exists():
            raise ValueError(f"File not found: {file_path}")
        return fp.read_text(encoding="utf-8")

    raise ValueError("Provide 'text' or 'file_path' for this action.")


# ── Save helper ───────────────────────────────────────────────────────────────

def _save_content(content: str, output_path: str = "") -> str:
    """Write content to disk and return a confirmation message."""
    dest = Path(output_path).expanduser() if output_path else DEFAULT_OUTPUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print(f"[{MODULE}] Saved document to {dest}")
    return f"💾 Saved to: {dest}"


def _maybe_autosave(parameters: dict, content: str) -> str:
    """If save_output is True, auto-save and append a note to content."""
    if parameters.get("save_output"):
        note = _save_content(content, parameters.get("output_path", ""))
        return f"{content}\n\n{note}"
    return content


# ── Action handlers ───────────────────────────────────────────────────────────

def _summarize(parameters: dict) -> str:
    text = _get_text(parameters)
    prompt = (
        "Summarize the following text in 3 to 5 clear, concise sentences. "
        "Focus on the most important ideas.\n\n"
        f"TEXT:\n{text}"
    )
    print(f"[{MODULE}] Summarizing {len(text)} chars")
    return _ask(prompt)


def _rewrite(parameters: dict) -> str:
    text = _get_text(parameters)
    tone = parameters.get("tone", "professional").lower()
    if tone not in VALID_TONES:
        tone = "professional"
    tone_hints = {
        "professional": "clear, polished, and business-appropriate",
        "casual": "friendly, conversational, and relaxed",
        "formal": "highly formal, precise, and objective",
        "persuasive": "compelling, confident, and motivating",
        "concise": "brief, direct, and to the point with no filler",
    }
    hint = tone_hints[tone]
    prompt = (
        f"Rewrite the following text in a {tone} tone ({hint}). "
        "Preserve the original meaning while improving clarity and style.\n\n"
        f"ORIGINAL:\n{text}"
    )
    print(f"[{MODULE}] Rewriting in '{tone}' tone ({len(text)} chars)")
    return _ask(prompt)


def _proofread(parameters: dict) -> str:
    text = _get_text(parameters)
    prompt = (
        "Proofread the following text. List all grammar, spelling, and "
        "punctuation errors found. For each error, show:\n"
        "  - Error: <the problematic text>\n"
        "  - Correction: <the corrected version>\n"
        "  - Reason: <brief explanation>\n\n"
        "If no errors are found, say 'No errors found.'\n\n"
        f"TEXT:\n{text}"
    )
    print(f"[{MODULE}] Proofreading {len(text)} chars")
    return _ask(prompt)


def _expand(parameters: dict) -> str:
    text = _get_text(parameters)
    prompt = (
        "Expand the following text with more detail, context, examples, and "
        "depth. Maintain the original tone and intent.\n\n"
        f"ORIGINAL:\n{text}"
    )
    print(f"[{MODULE}] Expanding {len(text)} chars")
    return _ask(prompt)


def _outline(parameters: dict) -> str:
    topic = (parameters.get("topic") or "").strip()
    if not topic:
        raise ValueError("Provide 'topic' for the outline action.")
    prompt = (
        f"Generate a detailed, well-structured outline for the topic: '{topic}'. "
        "Use numbered sections and sub-sections. Include an introduction and conclusion."
    )
    print(f"[{MODULE}] Generating outline for topic: {topic!r}")
    return _ask(prompt)


def _email(parameters: dict) -> str:
    recipient = parameters.get("recipient", "")
    subject = parameters.get("subject", "")
    body_points = parameters.get("body_points", [])
    tone = parameters.get("tone", "professional")

    if not body_points:
        raise ValueError("Provide 'body_points' (list of key points) for the email action.")

    points_text = "\n".join(f"- {p}" for p in body_points)
    prompt = textwrap.dedent(f"""\
        Draft a complete {tone} email with the following details:
        - Recipient: {recipient or 'the reader'}
        - Subject: {subject or '(infer from context)'}
        - Key points to cover:
        {points_text}

        Write a natural, well-structured email with greeting, body paragraphs, and sign-off.
    """)
    print(f"[{MODULE}] Drafting email to '{recipient}' with {len(body_points)} points")
    return _ask(prompt)


def _translate(parameters: dict) -> str:
    text = _get_text(parameters)
    target_lang = parameters.get("target_language", "English")
    prompt = (
        f"Translate the following text into {target_lang}. "
        "Preserve the meaning, tone, and formatting as closely as possible.\n\n"
        f"TEXT:\n{text}"
    )
    print(f"[{MODULE}] Translating {len(text)} chars to '{target_lang}'")
    return _ask(prompt)


def _extract_key_points(parameters: dict) -> str:
    text = _get_text(parameters)
    prompt = (
        "Extract the key points from the following text. "
        "Present them as a clear, concise bulleted list (use • for bullets). "
        "Each bullet should be one short sentence.\n\n"
        f"TEXT:\n{text}"
    )
    print(f"[{MODULE}] Extracting key points from {len(text)} chars")
    return _ask(prompt)


def _save_action(parameters: dict) -> str:
    content = _last_result.get("content", "")
    if not content:
        return "⚠️ No result to save yet. Run another action first."
    output_path = parameters.get("output_path", "")
    return _save_content(content, output_path)


# ── Entry point ───────────────────────────────────────────────────────────────

def document_assistant(parameters: dict, player=None, speak=None) -> str:
    """
    AI-powered document writing and analysis assistant for JARVIS.

    Parameters
    ----------
    parameters : dict
        action          : str  – summarize | rewrite | proofread | expand |
                                 outline | email | translate | extract_key_points | save
        text            : str  – Input text (for most actions)
        file_path       : str  – Path to a text file (alternative to text)
        tone            : str  – Rewrite/email tone: professional|casual|formal|
                                 persuasive|concise (default: professional)
        topic           : str  – Topic for outline generation
        recipient       : str  – Email recipient name/address
        subject         : str  – Email subject line
        body_points     : list – Key points for email body
        target_language : str  – Target language for translation (default: English)
        save_output     : bool – Auto-save result to output_path
        output_path     : str  – File path to save result (default: Desktop)
    player : object, optional
        JARVIS player for write_log().
    speak : callable, optional
        TTS callback.

    Returns
    -------
    str
        AI-generated result or error message.
    """
    global _last_result

    try:
        action = (parameters.get("action") or "summarize").strip().lower()
        print(f"[{MODULE}] Action: '{action}'")

        dispatch = {
            "summarize": _summarize,
            "rewrite": _rewrite,
            "proofread": _proofread,
            "expand": _expand,
            "outline": _outline,
            "email": _email,
            "translate": _translate,
            "extract_key_points": _extract_key_points,
        }

        if action == "save":
            result = _save_action(parameters)
        elif action in dispatch:
            raw_result = dispatch[action](parameters)
            _last_result = {"action": action, "content": raw_result}
            result = _maybe_autosave(parameters, raw_result)
        else:
            result = (
                f"❓ Unknown action '{action}'. "
                "Valid: summarize, rewrite, proofread, expand, outline, "
                "email, translate, extract_key_points, save"
            )

        if player and hasattr(player, "write_log"):
            player.write_log(f"[{MODULE}] {action}: {result[:120]}")
        if speak and callable(speak):
            speak(result[:500])  # Limit TTS output length

        return result

    except ValueError as exc:
        msg = f"[{MODULE}] Input error: {exc}"
        print(msg)
        if player and hasattr(player, "write_log"):
            player.write_log(msg)
        return f"❌ {exc}"

    except RuntimeError as exc:
        msg = f"[{MODULE}] Configuration error: {exc}"
        print(msg)
        if player and hasattr(player, "write_log"):
            player.write_log(msg)
        return f"❌ Configuration error: {exc}"

    except Exception as exc:
        # Attempt to catch common Google API / network errors gracefully
        exc_type = type(exc).__name__
        msg = f"[{MODULE}] AI error ({exc_type}): {exc}"
        print(msg)
        if player and hasattr(player, "write_log"):
            player.write_log(msg)
        return f"❌ Document assistant error ({exc_type}): {exc}"
