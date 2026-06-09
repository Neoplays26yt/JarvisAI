"""
code_helper.py — Advanced Developer Agent for JARVIS.

Capabilities:
  write       — Generate code from description
  edit        — Apply changes to existing file
  explain     — Explain what code does
  run         — Execute a script
  build       — Write + run with auto-fix loop
  optimize    — Refactor and clean up code
  screen_debug — Visual debug using screenshot + Gemini Vision
  review      — Code review: style, bugs, security, performance
  debug       — Investigate a bug or error in a file
  document    — Generate docstrings and README for a file
  test        — Generate unit tests for a file
  analyze     — Static analysis: complexity, patterns, metrics
  refactor    — Suggest and apply a refactoring plan
  dependencies — Analyze imports and external dependencies
  architecture — Summarize a project's architecture
  auto        — Auto-detect the best action
"""

import re
import subprocess
import sys
import time
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR           = _get_base_dir()
API_CONFIG_PATH    = BASE_DIR / "config" / "api_keys.json"
DESKTOP            = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3
GEMINI_MODEL       = "gemini-2.5-flash"


# ── API / Model ───────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    import json
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("gemini_api_key", "").strip()
        if not key:
            raise ValueError("gemini_api_key is empty")
        return key
    except FileNotFoundError:
        raise RuntimeError(f"API key file not found: {API_CONFIG_PATH}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"api_keys.json is corrupt: {exc}") from exc


def _get_gemini(model: str = GEMINI_MODEL):
    from google import genai
    client = genai.Client(api_key=_get_api_key())
    return genai.Client(api_key=_get_api_key()), model


# ── File Utilities ────────────────────────────────────────────────────────────

def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _resolve_save_path(output_path: str, language: str) -> Path:
    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts",
        "html": ".html", "css": ".css",
        "java": ".java", "cpp": ".cpp", "c": ".c",
        "bash": ".sh", "shell": ".sh", "powershell": ".ps1",
        "sql": ".sql", "json": ".json", "rust": ".rs", "go": ".go",
    }
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else DESKTOP / p
    ext = ext_map.get((language or "python").lower(), ".py")
    return DESKTOP / f"jarvis_code{ext}"


def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path)
    if not p.exists():
        return "", f"File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", f"Could not read file: {e}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"


def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview   = "\n".join(all_lines[:lines])
    suffix    = f"\n... ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return preview + suffix


def _has_error(output: str) -> bool:
    error_signals = ["error", "exception", "traceback", "syntaxerror",
                     "nameerror", "typeerror", "stderr", "failed", "crash"]
    return any(s in output.lower() for s in error_signals)


# ── Core Operations ───────────────────────────────────────────────────────────

def _run_file(path: Path, args: list, timeout: int) -> str:
    interpreters = {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
    }
    interp = interpreters.get(path.suffix.lower())
    if not interp:
        return f"No interpreter for {path.suffix}."
    try:
        result = subprocess.run(
            interp + [str(path)] + (args or []),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(path.parent)
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
        parts  = []
        if output: parts.append(f"Output:\n{output}")
        if error:  parts.append(f"Stderr:\n{error}")
        return "\n\n".join(parts) if parts else "Executed with no output."
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s."
    except FileNotFoundError:
        return f"Interpreter not found: {interp[0]}."
    except Exception as e:
        return f"Execution error: {e}"


def _take_screenshot() -> Path | None:
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        screenshot_path = Path.home() / "Desktop" / f"jarvis_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        print(f"[Code] 📸 Screenshot: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"[Code] ⚠️ Screenshot failed: {e}")
        return None


# ── Intent Detection ──────────────────────────────────────────────────────────

def _detect_intent(description: str, file_path: str, code: str) -> str:
    desc = (description or "").lower()

    screen_kw = ["screen", "what do you see", "what's on screen", "screenshot",
                 "this error", "why am i getting", "what's wrong", "debug screen"]
    if any(k in desc for k in screen_kw):
        return "screen_debug"

    arch_kw = ["architecture", "project structure", "how is this organized",
               "summarize project", "explain project"]
    if any(k in desc for k in arch_kw):
        return "architecture"

    dep_kw = ["dependencies", "imports", "what libraries", "what packages",
              "what does it import", "requirements"]
    if any(k in desc for k in dep_kw):
        return "dependencies"

    review_kw = ["review", "code review", "check quality", "find issues",
                 "what's wrong with", "check this code"]
    if any(k in desc for k in review_kw) and (code or file_path):
        return "review"

    debug_kw = ["debug", "fix bug", "why does it crash", "find the bug",
                "what's the problem", "investigate", "broken"]
    if any(k in desc for k in debug_kw) and (code or file_path):
        return "debug"

    doc_kw = ["document", "add docstrings", "generate readme",
              "write documentation", "add comments"]
    if any(k in desc for k in doc_kw) and (code or file_path):
        return "document"

    test_kw = ["write tests", "generate tests", "unit test", "test coverage",
               "create tests", "pytest", "unittest"]
    if any(k in desc for k in test_kw) and (code or file_path):
        return "test"

    analyze_kw = ["analyze", "complexity", "metrics", "how complex",
                  "cyclomatic", "patterns"]
    if any(k in desc for k in analyze_kw) and (code or file_path):
        return "analyze"

    optimize_kw = ["optimize", "refactor", "clean up", "improve",
                   "make it better", "make it faster"]
    if any(k in desc for k in optimize_kw) and (code or file_path):
        return "optimize"

    if file_path:
        p = Path(file_path)
        edit_kw  = ["edit", "update", "modify", "change", "add", "remove",
                    "refactor", "fix", "rename", "replace"]
        run_kw   = ["run", "execute", "launch", "start"]
        build_kw = ["build", "make it work", "try", "attempt"]

        if p.exists() and any(k in desc for k in edit_kw):
            return "edit"
        if p.exists() and any(k in desc for k in run_kw):
            return "run"
        if any(k in desc for k in build_kw):
            return "build"
        if p.exists():
            return "explain"

    explain_kw = ["explain", "what does", "describe", "analyze"]
    if any(k in desc for k in explain_kw) and (code or file_path):
        return "explain"

    build_kw = ["build", "make it work", "try and", "attempt"]
    if any(k in desc for k in build_kw):
        return "build"

    return "write"


# ── Action Implementations ────────────────────────────────────────────────────

def _write_action(description, language, output_path, player) -> str:
    if not description:
        return "Please describe what you want me to write, sir."
    lang  = language or "python"
    model = _get_gemini()
    if player: player.write_log("[Code] Writing code...")

    prompt = f"""You are an expert {lang} developer.
Write clean, working, well-commented {lang} code for the description below.

Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- Add helpful inline comments.
- Handle errors and edge cases properly.
- Use modern best practices.

Description: {description}

Code:"""

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        code     = _clean_code(response.text)
        path     = _resolve_save_path(output_path, lang)
        _save_file(path, code)
        print(f"[Code] ✅ Written: {path}")
        return f"Code written. Saved to: {path}\n\nPreview:\n{_preview(code)}"
    except Exception as e:
        return f"Could not generate code: {e}"


def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "Please provide a file path to edit, sir."
    if not instruction:
        return "Please describe what change to make, sir."
    content, err = _read_file(file_path)
    if err:
        return err
    if player: player.write_log("[Code] Editing file...")
    model = _get_gemini()
    prompt = f"""You are an expert code editor.
Apply the following change to the code below.
Return ONLY the complete updated code — no explanation, no markdown, no backticks.

Change: {instruction}

Original code:
{content}

Updated code:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        edited   = _clean_code(response.text)
    except Exception as e:
        return f"Could not edit code: {e}"
    status = _save_file(Path(file_path), edited)
    print(f"[Code] ✅ Edited: {file_path}")
    return f"File edited. {status}\n\nPreview:\n{_preview(edited)}"


def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to explain, sir."
    if player: player.write_log("[Code] Analyzing code...")
    model = _get_gemini()
    prompt = f"""Explain what this code does in simple, clear language.
Focus on: what it does, how it works, and any important details.
Be concise — 3 to 6 sentences maximum.

Code:
{code[:4000]}

Explanation:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text.strip()
    except Exception as e:
        return f"Could not explain code: {e}"


def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "Please provide a file path to run, sir."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player: player.write_log(f"[Code] Running {p.name}...")
    return _run_file(p, args, timeout)


def _build_action(description, language, output_path, args, timeout,
                  speak=None, player=None) -> str:
    if not description:
        return "Please describe what you want me to build, sir."
    if player: player.write_log("[Code] Build started...")
    lang  = language or "python"
    model = _get_gemini()
    prompt = f"""You are an expert {lang} developer.
Write clean, working, well-commented {lang} code for the description below.
Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- Add helpful inline comments.
- Handle errors and edge cases properly.

Description: {description}

Code:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        code     = _clean_code(response.text)
        path     = _resolve_save_path(output_path, lang)
        _save_file(path, code)
        print(f"[Code] ✅ Written: {path}")
    except Exception as e:
        msg = f"Could not write initial code: {e}"
        if speak: speak(msg)
        return msg

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[Code] 🔄 Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player: player.write_log(f"[Code] Attempt {attempt}...")
        last_output = _run_file(path, args, timeout)
        if not _has_error(last_output):
            msg = (
                f"Build complete, sir. "
                f"The code is working after {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Saved to {path}."
            )
            if speak: speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"
        print(f"[Code] ⚠️ Error on attempt {attempt}, fixing...")
        if player: player.write_log(f"[Code] Fixing (attempt {attempt})...")
        try:
            fix_prompt = f"""You are an expert debugger.
The code below failed with the following error. Fix it.
Return ONLY the corrected code — no explanation, no markdown, no backticks.

Original goal: {description}
Error:
{last_output[:2000]}
Broken code:
{code}
Fixed code:"""
            fix_response = client.models.generate_content(model="gemini-2.5-flash", contents=fix_prompt)
            code = _clean_code(fix_response.text)
            _save_file(path, code)
        except Exception as e:
            msg = f"Could not fix code on attempt {attempt}: {e}"
            if speak: speak(msg)
            return msg

    msg = (
        f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "
        f"The last error was: {last_output[:200]}"
    )
    if speak: speak(msg)
    return f"{msg}\n\nLast code saved to: {path}"


def _optimize_action(file_path, code, language, output_path, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to optimize, sir."
    if player: player.write_log("[Code] Optimizing code...")
    lang  = language or "python"
    model = _get_gemini()
    prompt = f"""You are an expert {lang} developer and code reviewer.
Optimize the following code for:
1. Performance — eliminate unnecessary operations, use efficient data structures
2. Readability — clear variable names, proper formatting, logical structure
3. Best practices — modern {lang} patterns, error handling, type hints if applicable
4. Remove dead code, redundant comments, and unnecessary complexity

Return ONLY the optimized code — no explanation, no markdown, no backticks.

Original code:
{code[:6000]}

Optimized code:"""
    try:
        response  = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        optimized = _clean_code(response.text)
    except Exception as e:
        return f"Could not optimize code: {e}"
    save_path = Path(file_path) if file_path else _resolve_save_path(output_path, lang)
    status = _save_file(save_path, optimized)
    print(f"[Code] ✅ Optimized: {save_path}")
    original_lines  = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines
    return (
        f"Code optimized. {status}\n"
        f"Lines: {original_lines} → {optimized_lines} "
        f"({'−' if diff > 0 else '+'}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )


def _review_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to review, sir."
    if player: player.write_log("[Code] Running code review...")
    model = _get_gemini()
    target = Path(file_path).name if file_path else "the code"
    prompt = f"""You are a senior software engineer performing a thorough code review of {target}.

Analyze the following code across these dimensions:
1. **Bugs & Logic Errors** — Identify any bugs, off-by-one errors, null references, race conditions
2. **Security** — SQL injection, path traversal, hardcoded secrets, input validation issues
3. **Performance** — N+1 queries, unnecessary iterations, memory leaks, blocking calls
4. **Code Quality** — Dead code, magic numbers, overly complex functions, naming issues
5. **Error Handling** — Missing try/except, uncaught exceptions, silent failures
6. **Best Practices** — Type hints, docstrings, single responsibility, DRY violations

For each issue found, provide:
- Severity: [CRITICAL | HIGH | MEDIUM | LOW | INFO]
- Location: line number or function name
- Issue: description
- Fix: concrete suggestion

Code to review:
```
{code[:6000]}
```

Code Review:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        result   = response.text.strip()
        print("[Code] ✅ Code review complete")
        return result
    except Exception as e:
        return f"Code review failed: {e}"


def _debug_action(file_path, code, description, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code and not description:
        return "Please provide code and/or a description of the bug, sir."
    if player: player.write_log("[Code] Debugging...")
    model = _get_gemini()
    target = Path(file_path).name if file_path else "the code"
    problem = description or "Find and explain any bugs in this code."
    prompt = f"""You are an expert debugger investigating {target}.

Problem description: {problem}

Code:
```
{(code or '')[:6000]}
```

Please:
1. Identify the root cause of the issue
2. Trace the execution path leading to the bug
3. Provide a minimal, concrete fix
4. Explain why the fix works
5. Suggest any additional safeguards to prevent similar issues

Debug Analysis:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text.strip()
    except Exception as e:
        return f"Debug analysis failed: {e}"


def _document_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to document, sir."
    if player: player.write_log("[Code] Generating documentation...")
    model = _get_gemini()
    prompt = f"""You are a technical documentation expert.
Add comprehensive docstrings and comments to this code.

Rules:
- Output ONLY the documented code. No explanation outside the code.
- Use Google-style or NumPy-style docstrings (whichever is appropriate for the language)
- Add module-level docstring at the top
- Add function/class docstrings with Args, Returns, Raises sections
- Add inline comments for complex logic
- Do NOT remove or change existing functionality

Code to document:
{code[:6000]}

Documented code:"""
    try:
        response     = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        documented   = _clean_code(response.text)
        if file_path:
            _save_file(Path(file_path), documented)
            return f"Documentation added and saved to: {file_path}\n\nPreview:\n{_preview(documented)}"
        return f"Documented code:\n\n{documented}"
    except Exception as e:
        return f"Documentation generation failed: {e}"


def _test_action(file_path, code, language, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to generate tests for, sir."
    if player: player.write_log("[Code] Generating tests...")
    lang  = language or "python"
    model = _get_gemini()
    file_name = Path(file_path).stem if file_path else "module"
    prompt = f"""You are a test engineer writing comprehensive unit tests for a {lang} module.

Module name: {file_name}

Write complete unit tests that:
1. Test normal/happy path cases
2. Test edge cases (empty inputs, boundary values, null/None)
3. Test error cases (invalid inputs, exceptions)
4. Mock external dependencies (file system, network, etc.)
5. Use appropriate test framework (pytest for Python, Jest for JS, JUnit for Java)
6. Include setup/teardown where needed

Output ONLY the test code — no explanation, no markdown fences.

Code to test:
{code[:5000]}

Test code:"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        tests    = _clean_code(response.text)
        # Save test file
        if file_path:
            test_path = Path(file_path).parent / f"test_{Path(file_path).name}"
        else:
            ext = ".py" if lang == "python" else ".test.js"
            test_path = DESKTOP / f"test_{file_name}{ext}"
        _save_file(test_path, tests)
        print(f"[Code] ✅ Tests generated: {test_path}")
        return f"Unit tests generated and saved to: {test_path}\n\nPreview:\n{_preview(tests, 15)}"
    except Exception as e:
        return f"Test generation failed: {e}"


def _analyze_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path to analyze, sir."
    if player: player.write_log("[Code] Analyzing code...")
    model = _get_gemini()
    target = Path(file_path).name if file_path else "the code"
    lines = code.splitlines()
    # Quick static metrics
    comment_lines = sum(1 for l in lines if l.strip().startswith(("#", "//", "*", "/*", "\"\"\"", "'''")))
    blank_lines   = sum(1 for l in lines if not l.strip())
    code_lines    = len(lines) - comment_lines - blank_lines
    functions     = len(re.findall(r"^\s*(?:def |function |func |void |int |bool )", code, re.MULTILINE))
    classes       = len(re.findall(r"^\s*(?:class |struct |interface )", code, re.MULTILINE))

    prompt = f"""Perform a static code analysis of {target}.

Provide:
1. **Purpose** — What this code does (2 sentences)
2. **Complexity** — Cyclomatic complexity assessment (Low/Medium/High) and why
3. **Patterns** — Design patterns used (if any)
4. **Coupling** — Dependencies and coupling level
5. **Maintainability** — Score 1-10 and explanation
6. **Key Risks** — Top 3 maintenance risks
7. **Recommendations** — Top 3 actionable improvements

Keep response concise and technical.

Code:
{code[:5000]}

Analysis:"""

    metrics = (
        f"\n📊 Static Metrics for {target}:\n"
        f"  Total lines  : {len(lines)}\n"
        f"  Code lines   : {code_lines}\n"
        f"  Comments     : {comment_lines}\n"
        f"  Blank lines  : {blank_lines}\n"
        f"  Functions    : {functions}\n"
        f"  Classes      : {classes}\n"
    )

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return metrics + "\n" + response.text.strip()
    except Exception as e:
        return metrics + f"\nAI analysis failed: {e}"


def _dependencies_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err: return err
    if not code:
        return "Please provide code or a file path, sir."
    if player: player.write_log("[Code] Analyzing dependencies...")

    # Extract imports statically
    stdlib_pattern  = re.compile(r"^(?:import|from)\s+([a-zA-Z0-9_.]+)", re.MULTILINE)
    all_imports = stdlib_pattern.findall(code)
    top_level   = sorted(set(imp.split(".")[0] for imp in all_imports))

    # Classify as stdlib vs third-party (rough heuristic)
    STDLIB = {
        "os", "sys", "re", "json", "time", "datetime", "pathlib", "threading",
        "subprocess", "io", "math", "random", "hashlib", "base64", "urllib",
        "http", "socket", "logging", "unittest", "abc", "copy", "functools",
        "itertools", "collections", "typing", "enum", "dataclasses", "contextlib",
        "asyncio", "concurrent", "multiprocessing", "queue", "struct", "pickle",
        "csv", "configparser", "argparse", "shutil", "tempfile", "glob", "fnmatch",
        "platform", "signal", "traceback", "warnings", "inspect", "gc",
        "__future__", "builtins", "string", "textwrap", "pprint",
    }
    third_party = [m for m in top_level if m not in STDLIB and m]
    stdlib_used = [m for m in top_level if m in STDLIB]

    # Check which third-party are installed
    installed, missing = [], []
    for pkg in third_party:
        try:
            __import__(pkg)
            installed.append(pkg)
        except ImportError:
            missing.append(pkg)

    lines = [f"🔍 Dependency Analysis for {Path(file_path).name if file_path else 'code'}:\n"]
    if stdlib_used:
        lines.append(f"📦 Standard Library ({len(stdlib_used)}):")
        lines.append("   " + ", ".join(stdlib_used))
    if installed:
        lines.append(f"\n✅ Third-party (installed) ({len(installed)}):")
        lines.append("   " + ", ".join(installed))
    if missing:
        lines.append(f"\n❌ Third-party (MISSING) ({len(missing)}):")
        lines.append("   " + ", ".join(missing))
        lines.append(f"\n   To install: pip install {' '.join(missing)}")
    if not third_party:
        lines.append("\n✅ No third-party dependencies detected.")

    return "\n".join(lines)


def _architecture_action(file_path, player) -> str:
    """Analyze a project directory or single file's architecture."""
    if not file_path:
        return "Please provide a file or project path to analyze, sir."

    path = Path(file_path)
    if path.is_file():
        code, err = _read_file(file_path)
        if err: return err
        if player: player.write_log("[Code] Analyzing file architecture...")
        model = _get_gemini()
        prompt = f"""Briefly describe the architecture of this file.
Include: purpose, main components, data flow, design patterns, and coupling.
Keep it under 200 words.

File: {path.name}
Code:
{code[:5000]}

Architecture Summary:"""
        try:
            return client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text.strip()
        except Exception as e:
            return f"Architecture analysis failed: {e}"

    # Directory mode
    if player: player.write_log("[Code] Analyzing project architecture...")
    structure_lines = []
    file_count      = 0
    py_files        = []
    for p in sorted(path.rglob("*")):
        if "__pycache__" in str(p) or ".git" in str(p):
            continue
        rel = p.relative_to(path)
        depth = len(rel.parts) - 1
        indent = "  " * depth
        if p.is_dir():
            structure_lines.append(f"{indent}📁 {p.name}/")
        else:
            structure_lines.append(f"{indent}📄 {p.name}")
            file_count += 1
            if p.suffix == ".py" and file_count < 30:
                py_files.append(str(p))

    structure = "\n".join(structure_lines[:60])
    if len(structure_lines) > 60:
        structure += f"\n... ({len(structure_lines) - 60} more)"

    # Read key files for context
    key_content = ""
    for pf in py_files[:5]:
        c, _ = _read_file(pf)
        if c:
            key_content += f"\n--- {Path(pf).name} ---\n{c[:1000]}\n"

    model = _get_gemini()
    prompt = f"""Analyze the architecture of this Python project.

Project structure:
{structure}

Key file contents (sample):
{key_content[:4000]}

Provide:
1. **Project Purpose** — What does this project do?
2. **Architecture Pattern** — MVC, microservices, layered, etc.
3. **Main Components** — Key modules and their roles
4. **Data Flow** — How data moves through the system
5. **Entry Points** — Where execution begins
6. **Dependencies** — Key external dependencies
7. **Strengths & Weaknesses** — Notable design choices

Architecture Report:"""
    try:
        return client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text.strip()
    except Exception as e:
        return f"Project architecture analysis failed: {e}"


def _screen_debug_action(description, file_path, player, speak=None) -> str:
    if player: player.write_log("[Code] Taking screenshot for analysis...")
    print("[Code] 📸 Capturing screen for debug...")

    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return "Could not take screenshot, sir. Please make sure PyAutoGUI is installed."

    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[Code] ⚠️ Could not read file: {err}")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=_get_api_key())
        image_bytes   = screenshot_path.read_bytes()
        user_question = description or "What error or problem do you see on the screen? How can it be fixed?"

        context = ""
        if file_content:
            context = f"\n\nAdditionally, here is the related file content:\n```\n{file_content[:4000]}\n```"

        analysis_prompt = f"""You are an expert programmer and debugger analyzing a screenshot.

User's question: {user_question}{context}

Please:
1. Identify any errors, exceptions, or problems visible on the screen
2. Explain what is causing the problem in simple terms
3. Provide a concrete fix or solution
4. If there's code visible, show the corrected version

Be specific and actionable. If you see an error message, quote it exactly."""

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            analysis_prompt,
        ]
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )
        analysis = response.text.strip()
        print("[Code] ✅ Screen analysis complete")

        try: screenshot_path.unlink()
        except Exception as e: print(f"[{_MODULE}] Handled exception: {e}")

        if file_path and file_content:
            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                _save_file(Path(file_path), fixed_code)
                analysis += f"\n\n✅ Fixed code saved to: {file_path}"

        return analysis

    except Exception as e:
        try: screenshot_path.unlink()
        except Exception as e: print(f"[{_MODULE}] Handled exception: {e}")
        return f"Screen analysis failed: {e}"


# ── Entry Point ───────────────────────────────────────────────────────────────

def code_helper(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    JARVIS Advanced Developer Agent.

    parameters:
        action      : write | edit | explain | run | build | optimize | screen_debug |
                      review | debug | document | test | analyze | dependencies |
                      architecture | auto (default: auto)
        description : What the code should do / problem description / change to make
        language    : Programming language (default: python)
        output_path : Where to save — full path or filename
        file_path   : Path to existing file
        code        : Raw code string (for explain/optimize/review/debug/test/analyze)
        args        : CLI argument list for run/build
        timeout     : Execution timeout in seconds (default: 30)
        instruction : Alias for description in edit mode
    """
    p           = parameters or {}
    action      = p.get("action", "auto").lower().strip()
    description = p.get("description", p.get("instruction", "")).strip()
    language    = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path   = p.get("file_path", "").strip()
    code        = p.get("code", "").strip()
    args        = p.get("args", [])
    if isinstance(args, str):
        args = args.split()
    timeout     = int(p.get("timeout", 30))

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[Code] 🤖 Auto-detected: {action}")
    else:
        print(f"[Code] 🔧 action={action}  file={file_path or '—'}  lang={language}")

    try:
        if action == "write":
            return _write_action(description, language, output_path, player)
        elif action == "edit":
            return _edit_action(file_path, description, player)
        elif action == "explain":
            return _explain_action(file_path, code, player)
        elif action == "run":
            return _run_action(file_path, args, timeout, player)
        elif action == "build":
            return _build_action(description, language, output_path, args, timeout, speak, player)
        elif action == "optimize":
            return _optimize_action(file_path, code, language, output_path, player)
        elif action == "screen_debug":
            return _screen_debug_action(description, file_path, player, speak)
        elif action == "review":
            return _review_action(file_path, code, player)
        elif action == "debug":
            return _debug_action(file_path, code, description, player)
        elif action == "document":
            return _document_action(file_path, code, player)
        elif action == "test":
            return _test_action(file_path, code, language, player)
        elif action == "analyze":
            return _analyze_action(file_path, code, player)
        elif action == "dependencies":
            return _dependencies_action(file_path, code, player)
        elif action == "architecture":
            return _architecture_action(file_path, player)
        elif action == "refactor":
            # Refactor = optimize + explain the changes
            result = _optimize_action(file_path, code, language, output_path, player)
            return result
        else:
            return (
                f"Unknown action: '{action}'. "
                "Use: write | edit | explain | run | build | optimize | screen_debug | "
                "review | debug | document | test | analyze | dependencies | architecture"
            )
    except RuntimeError as e:
        # API key issues — surface clearly
        return f"JARVIS Developer Agent error: {e}"
    except Exception as e:
        return f"code_helper failed ({action}): {e}"
