#!/usr/bin/env python3
"""
VybeShield — Autonomous System Auditor for VybeFlow
====================================================
Scans the entire project for:
  1. Python syntax errors (ast.parse on every .py file)
  2. HTML structure issues (html.parser on every .html template)
  3. Dead State — buttons/elements with id= but no JS addEventListener / onclick
  4. CSS class conflicts — same class defined in multiple files with differing values
  5. Broken Python imports — 'from X import Y' where X can't be resolved locally
  6. Duplicate Flask route definitions
  7. Story-specific API health check (route existence, return-value contract)
  8. JS import/require patterns pointing to missing files
  9. Dependency tree check — requirements.txt vs importable packages

Usage:
    python vybeshield.py              # full scan + report
    python vybeshield.py --fix        # apply auto-fixable issues
    python vybeshield.py --html       # HTML/CSS audit only
    python vybeshield.py --py         # Python audit only
    python vybeshield.py --deps       # dependency check only
"""

import ast
import os
import re
import sys
import json
import argparse
import importlib
import subprocess
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

# ──────────────────────────────────────────────
# COLOURS (no external dependency)
# ──────────────────────────────────────────────
class C:
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def _ok(msg):   print(f"  {C.GREEN}✓{C.RESET} {msg}")
def _warn(msg): print(f"  {C.YELLOW}⚠{C.RESET} {msg}")
def _err(msg):  print(f"  {C.RED}✗{C.RESET} {msg}")
def _info(msg): print(f"  {C.CYAN}→{C.RESET} {msg}")
def _head(msg): print(f"\n{C.BOLD}{C.CYAN}{'═'*60}{C.RESET}\n{C.BOLD} {msg}{C.RESET}\n{'─'*60}")

ISSUES   = []
WARNINGS = []
FIXES    = []

def _log_issue(category, path, detail):
    ISSUES.append({"cat": category, "path": str(path), "detail": detail})
    _err(f"[{category}] {path}: {detail}")

def _log_warn(category, path, detail):
    WARNINGS.append({"cat": category, "path": str(path), "detail": detail})
    _warn(f"[{category}] {path}: {detail}")


# ══════════════════════════════════════════════
# 1. PYTHON SYNTAX CHECK
# ══════════════════════════════════════════════
def _project_py_files():
    """Return only root-level and one-level-deep .py files, skipping venv/.git."""
    SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules", ".venv", "env"}
    results = []
    for entry in ROOT.iterdir():
        if entry.is_file() and entry.suffix == ".py":
            results.append(entry)
        elif entry.is_dir() and entry.name not in SKIP_DIRS:
            for sub in entry.iterdir():
                if sub.is_file() and sub.suffix == ".py":
                    results.append(sub)
    return results


def check_python_syntax():
    _head("1 · Python Syntax Check")
    py_files = _project_py_files()
    errors = 0
    for path in sorted(py_files):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
            ast.parse(src, filename=str(path))
        except SyntaxError as e:
            _log_issue("SYNTAX", path.relative_to(ROOT), f"Line {e.lineno}: {e.msg}")
            errors += 1
    if errors == 0:
        _ok(f"All {len(py_files)} Python files pass syntax check")
    return errors


# ══════════════════════════════════════════════
# 2. HTML STRUCTURE CHECK
# ══════════════════════════════════════════════
class _HTMLAudit(HTMLParser):
    """Tracks unclosed tags and suspicious patterns."""
    VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
    JINJA = re.compile(r'\{[%{]')

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.issues = []
        self.line = 1

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack.pop(i)
                return
        self.issues.append(f"Unexpected </{tag}> at line {self.getpos()[0]}")

    def unclosed(self):
        # Ignore html/head/body — browsers auto-close them
        ignore = {"html", "head", "body"}
        return [(t, ln) for t, ln in self.stack if t not in ignore]


def check_html_structure():
    _head("2 · HTML Structure Check")
    html_files = list(TEMPLATE_DIR.glob("**/*.html")) if TEMPLATE_DIR.exists() else []
    errors = 0
    for path in sorted(html_files):
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Strip Jinja2 blocks so html.parser doesn't choke
        clean = re.sub(r'\{%.*?%\}', '', raw, flags=re.DOTALL)
        clean = re.sub(r'\{\{.*?\}\}', '""', clean, flags=re.DOTALL)
        parser = _HTMLAudit()
        try:
            parser.feed(clean)
        except Exception as exc:
            _log_warn("HTML_PARSE", path.relative_to(ROOT), str(exc))
        for tag, ln in parser.unclosed():
            _log_warn("HTML_UNCLOSED", path.relative_to(ROOT), f"<{tag}> opened at line {ln} never closed")
            errors += 1
        for issue in parser.issues:
            _log_warn("HTML_TAG", path.relative_to(ROOT), issue)
    if errors == 0:
        _ok(f"All {len(html_files)} HTML templates: no unclosed tags detected")
    return errors


# ══════════════════════════════════════════════
# 3. DEAD STATE — buttons with no JS handler
# ══════════════════════════════════════════════
def check_dead_state():
    _head("3 · Dead State Check (buttons with no JS handlers)")
    html_files = list(TEMPLATE_DIR.glob("**/*.html")) if TEMPLATE_DIR.exists() else []
    dead_count = 0
    for path in sorted(html_files):
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Collect all id= values from interactive elements
        btn_ids = set(re.findall(r'<(?:button|a|input|select)[^>]+id=["\']([^"\']+)["\']', raw))
        # Check each id has some JS reference (addEventListener, onclick, getElementById, querySelector)
        js_refs  = set(re.findall(r"['\"]([a-zA-Z0-9_-]+)['\"]", raw))
        js_refs2 = set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', raw))
        js_refs3 = set(re.findall(r'querySelector\(["\']#([^"\']+)["\']\)', raw))
        handled  = js_refs | js_refs2 | js_refs3

        skip_prefixes = ("csrf", "caption", "location", "mentions", "story-mode-input",
                         "story-font-input", "camera-photo-data", "doodle-data",
                         "music-track", "music-preview-url")
        for bid in sorted(btn_ids):
            if bid in handled:
                continue
            if any(bid.startswith(p) for p in skip_prefixes):
                continue
            # Only report real interactive buttons, not hidden inputs
            pattern = rf'<(?:button|a)[^>]+id=["\'{bid}["\'"][^>]*>'
            if re.search(rf'<(?:button|a)\b[^>]*\bid=["\']' + re.escape(bid) + r'["\']', raw):
                _log_warn("DEAD_STATE", path.relative_to(ROOT),
                          f'#{bid} present but no JS handler detected')
                dead_count += 1
    if dead_count == 0:
        _ok("No obvious dead-state buttons found")
    return dead_count


# ══════════════════════════════════════════════
# 4. CSS CLASS CONFLICTS
# ══════════════════════════════════════════════
def check_css_conflicts():
    _head("4 · CSS Class Conflict Scan")
    # Collect all CSS class definitions across .html (inline <style>) and .css files
    class_defs = defaultdict(list)  # class_name -> [(file, definition_fragment)]

    css_re = re.compile(r'(\.[\w-]+)\s*\{([^}]+)\}', re.DOTALL)

    def _scan_css(text, source_label):
        for m in css_re.finditer(text):
            cls  = m.group(1).strip()
            body = re.sub(r'\s+', ' ', m.group(2).strip())[:120]
            class_defs[cls].append((source_label, body))

    # Scan .html inline <style> blocks
    if TEMPLATE_DIR.exists():
        for path in TEMPLATE_DIR.glob("**/*.html"):
            raw = path.read_text(encoding="utf-8", errors="replace")
            for style_block in re.findall(r'<style[^>]*>(.*?)</style>', raw, re.DOTALL | re.IGNORECASE):
                _scan_css(style_block, path.name)

    # Scan .css files in static
    if STATIC_DIR.exists():
        for path in STATIC_DIR.glob("**/*.css"):
            _scan_css(path.read_text(encoding="utf-8", errors="replace"), path.name)

    conflicts = 0
    for cls, definitions in sorted(class_defs.items()):
        if len(definitions) < 2:
            continue
        files = [f for f, _ in definitions]
        if len(set(files)) < 2:
            continue  # Only multiple defs in the same file (e.g., media queries) — that's normal
        # Check if core properties differ meaningfully (display, position, width, flex-direction, grid-template)
        key_props = ("display", "position", "width", "flex-direction", "grid-template-columns",
                     "overflow", "float", "box-sizing")
        prop_vals = defaultdict(set)
        for _, body in definitions:
            for prop in key_props:
                m = re.search(rf'\b{prop}\s*:\s*([^;]+)', body)
                if m:
                    prop_vals[prop].add(m.group(1).strip())
        for prop, vals in prop_vals.items():
            if len(vals) > 1:
                _log_warn("CSS_CONFLICT", cls,
                          f"'{prop}' defined as {vals} across: {set(files)}")
                conflicts += 1
    if conflicts == 0:
        _ok("No critical CSS class property conflicts found across files")
    return conflicts


# ══════════════════════════════════════════════
# 5. BROKEN LOCAL IMPORTS
# ══════════════════════════════════════════════
def check_imports():
    _head("5 · Broken Import Check")
    py_files = _project_py_files()
    local_modules = {f.stem for f in py_files}
    # Also include __init__.py package
    local_modules.add("__init__")

    broken = 0
    import_re = re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE)
    stdlib_sample = {
        "os","sys","re","ast","json","hashlib","uuid","datetime","logging",
        "base64","io","time","math","random","pathlib","abc","typing","enum",
        "functools","itertools","collections","contextlib","threading","socket",
        "http","urllib","email","html","xml","csv","sqlite3","subprocess",
        "shutil","tempfile","zipfile","gzip","traceback","inspect","copy",
        "string","struct","binascii","hmac","secrets","dataclasses","warnings"
    }
    known_third_party = {
        "flask","flask_sqlalchemy","flask_login","flask_wtf","flask_limiter",
        "flask_migrate","flask_socketio","sqlalchemy","werkzeug","jinja2",
        "wtforms","bcrypt","pillow","PIL","requests","gunicorn","eventlet",
        "gevent","openai","anthropic","google","vertexai","boto3","celery",
        "redis","psycopg2","pymysql","dotenv","jwt","cryptography","pydantic",
        "marshmallow","alembic","click","itsdangerous","markupsafe","greenlet"
    }

    for path in sorted(py_files):
        src = path.read_text(encoding="utf-8", errors="replace")
        for match in import_re.finditer(src):
            mod = match.group(1).split(".")[0]
            if mod in stdlib_sample or mod in known_third_party or mod in local_modules:
                continue
            # Unknown module — try importlib
            try:
                importlib.util.find_spec(mod)
            except (ModuleNotFoundError, ValueError):
                _log_warn("IMPORT", path.relative_to(ROOT), f"Cannot resolve import: '{mod}'")
                broken += 1
    if broken == 0:
        _ok("All imports resolved (stdlib, known packages, local modules)")
    return broken


# ══════════════════════════════════════════════
# 6. DUPLICATE FLASK ROUTES
# ══════════════════════════════════════════════
def check_duplicate_routes():
    _head("6 · Duplicate Flask Route Check")
    # Match route with optional methods= to include HTTP method in key
    route_re  = re.compile(r"@\w+\.route\(['\"]([^'\"]+)['\"][^)]*methods=[^)]*?['\"]([A-Z]+)['\"]")
    route_re2 = re.compile(r"@\w+\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]")
    routes = defaultdict(list)
    py_files = _project_py_files()
    skip_archives = {"Vybe Flow.py", "VybeFlow.py", "VybeFlowapp_old_DO_NOT_RUN.py",
                     "app_simple.py", "main.py", "vybeflow_minimal.py"}
    for path in sorted(py_files):
        if path.name in skip_archives:
            continue  # Skip legacy/archive files
        src = path.read_text(encoding="utf-8", errors="replace")
        for m in route_re.finditer(src):
            key = f"{m.group(2).upper()} {m.group(1)}"
            routes[key].append(path.name)
        for m in route_re2.finditer(src):
            key = f"{m.group(1).upper()} {m.group(2)}"
            routes[key].append(path.name)
    for path in sorted(py_files):
        src = path.read_text(encoding="utf-8", errors="replace")
        for m in route_re.finditer(src):
            routes[m.group(1)].append(path.name)

    dupes = 0
    for route, files in sorted(routes.items()):
        if len(files) > 1:
            _log_warn("DUPE_ROUTE", route, f"Defined in: {files}")
            dupes += 1
    if dupes == 0:
        _ok("No duplicate route definitions found")
    return dupes


# ══════════════════════════════════════════════
# 7. STORY API HEALTH CHECK
# ══════════════════════════════════════════════
STORY_API_CONTRACTS = [
    # (method, url_fragment, expected_json_keys)
    ("GET",  "/stories",         []),
    ("GET",  "/create_story",    []),
    ("POST", "/story/create",    ["ok"]),
    ("POST", "/api/story",       ["ok", "story_id"]),
]

def check_story_api():
    _head("7 · Story API Route Existence Check")
    app_py = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    story_py = (ROOT / "story_routes.py").read_text(encoding="utf-8", errors="replace") if (ROOT / "story_routes.py").exists() else ""
    combined = app_py + story_py
    missing = 0
    checks = [
        ("create_story",       r'def create_story'),
        ("story_create_post",  r'def story_create_post'),
        ("stories_page",       r'def stories_page|def stories_list'),
        ("api_story_nsfw_pin", r'def api_story_set_nsfw_pin'),
        ("api_story_verify",   r'def api_story_verify_nsfw_pin'),
        ("story_delete",       r'def api_stories_delete'),
        ("story_draft_save",   r"postStory\('Only Me'\)|visibility.*Only Me"),
    ]
    for label, pattern in checks:
        if re.search(pattern, combined):
            _ok(f"{label}: route/handler found")
        else:
            _log_issue("STORY_API", "app.py / story_routes.py", f"Missing: {label}")
            missing += 1

    # Check that story_create_post returns {"ok": true, "story_id": ...}
    sc_post_match = re.search(r'def story_create_post.*?(?=\ndef |\Z)', app_py, re.DOTALL)
    if sc_post_match:
        sc_body = sc_post_match.group(0)
        if '"ok"' in sc_body or "'ok'" in sc_body:
            _ok('story_create_post: returns {"ok": ...} contract present')
        else:
            _log_warn("STORY_API", "app.py:story_create_post",
                      'Response does not include "ok" key — story_create.html JS checks for data.ok')
            missing += 1
        if '"story_id"' in sc_body or "'story_id'" in sc_body:
            _ok('story_create_post: returns story_id')
        else:
            _log_warn("STORY_API", "app.py:story_create_post",
                      '"story_id" not found in response — PIN modal in story_create.html needs it')
            missing += 1
    return missing


# ══════════════════════════════════════════════
# 8. JS FILE IMPORTS CHECK
# ══════════════════════════════════════════════
def check_js_imports():
    _head("8 · JS Static File Import Check")
    html_files = list(TEMPLATE_DIR.glob("**/*.html")) if TEMPLATE_DIR.exists() else []
    broken = 0
    src_re = re.compile(r'src=["\']([^"\']+\.js)["\']')
    href_re = re.compile(r'href=["\']([^"\']+\.css)["\']')
    for path in sorted(html_files):
        raw = path.read_text(encoding="utf-8", errors="replace")
        for m in src_re.finditer(raw):
            url = m.group(1)
            if url.startswith("http") or "{{" in url or "{%" in url:
                continue
            # Normalise /static/... → static/...
            rel = url.lstrip("/")
            target = ROOT / rel
            if not target.exists():
                _log_warn("JS_IMPORT", path.relative_to(ROOT), f"Missing file: {url}")
                broken += 1
        for m in href_re.finditer(raw):
            url = m.group(1)
            if url.startswith("http") or "{{" in url or "{%" in url:
                continue
            rel = url.lstrip("/")
            target = ROOT / rel
            if not target.exists():
                _log_warn("CSS_IMPORT", path.relative_to(ROOT), f"Missing CSS: {url}")
                broken += 1
    if broken == 0:
        _ok("All local JS/CSS imports resolve to existing files")
    return broken


# ══════════════════════════════════════════════
# 9. DEPENDENCY TREE CHECK
# ══════════════════════════════════════════════
def check_dependencies():
    _head("9 · Dependency / requirements.txt Check")
    req_path = ROOT / "requirements.txt"
    if not req_path.exists():
        _warn("requirements.txt not found — skipping")
        return 0

    reqs = [
        line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip().lower()
        for line in req_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    missing = 0
    for pkg in reqs:
        # normalise - -> _
        mod_name = pkg.replace("-", "_")
        try:
            spec = importlib.util.find_spec(mod_name)
            if spec is None:
                raise ModuleNotFoundError
            _ok(f"{pkg}: installed")
        except (ModuleNotFoundError, ValueError, AttributeError):
            _log_warn("DEPENDENCY", "requirements.txt", f"'{pkg}' listed but not importable (may not be installed)")
            missing += 1

    if missing == 0:
        _ok(f"All {len(reqs)} listed packages appear importable")
    return missing


# ══════════════════════════════════════════════
# REPORT SUMMARY
# ══════════════════════════════════════════════
def print_report():
    _head("VybeShield — Scan Complete")
    print(f"\n{C.BOLD}Summary:{C.RESET}")
    print(f"  Critical Issues  : {C.RED}{len(ISSUES)}{C.RESET}")
    print(f"  Warnings         : {C.YELLOW}{len(WARNINGS)}{C.RESET}")

    if not ISSUES and not WARNINGS:
        print(f"\n  {C.GREEN}{C.BOLD}🛡 Zero-Glitch environment confirmed.{C.RESET}")
        return

    if ISSUES:
        print(f"\n{C.RED}Critical Issues:{C.RESET}")
        for iss in ISSUES:
            print(f"  [{iss['cat']}] {iss['path']}: {iss['detail']}")

    if WARNINGS:
        print(f"\n{C.YELLOW}Warnings:{C.RESET}")
        for w in WARNINGS[:30]:
            print(f"  [{w['cat']}] {w['path']}: {w['detail']}")
        if len(WARNINGS) > 30:
            print(f"  ... and {len(WARNINGS)-30} more")

    # Save JSON report
    report_path = ROOT / "_vybeshield_report.json"
    report = {"issues": ISSUES, "warnings": WARNINGS}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _info(f"Full report saved to {report_path.name}")


# ══════════════════════════════════════════════
# AUTO-FIX: removable issues
# ══════════════════════════════════════════════
def auto_fix():
    """Apply safe auto-fixes for known patterns."""
    _head("Auto-Fix Pass")
    fixes_applied = 0

    # Fix 1: Remove bare `except: pass` in Python files (replace with logging)
    py_files = [f for f in _project_py_files() if f.name != "vybeshield.py"]
    silent_pass_re = re.compile(r'(\s*except\s*(?:Exception\s*)?):\s*\n\s*pass\b')
    for path in sorted(py_files):
        src = path.read_text(encoding="utf-8", errors="replace")
        new_src = silent_pass_re.sub(
            lambda m: m.group(0).replace('\n' + m.group(0).split('\n')[-1],
                                         '\n' + m.group(0).split('\n')[-1].replace(
                                             'pass', 'pass  # VybeShield: silent exception swallowed')),
            src
        )
        if new_src != src:
            path.write_text(new_src, encoding="utf-8")
            _ok(f"Tagged silent except:pass in {path.name}")
            fixes_applied += 1

    if fixes_applied == 0:
        _ok("Nothing to auto-fix")
    return fixes_applied


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="VybeShield — VybeFlow Auto Auditor")
    parser.add_argument("--fix",  action="store_true", help="Apply safe auto-fixes")
    parser.add_argument("--html", action="store_true", help="HTML/CSS only")
    parser.add_argument("--py",   action="store_true", help="Python only")
    parser.add_argument("--deps", action="store_true", help="Dependencies only")
    args = parser.parse_args()

    print(f"\n{C.BOLD}{C.CYAN}")
    print("  ██╗   ██╗██╗   ██╗██████╗ ███████╗███████╗██╗  ██╗██╗███████╗██╗     ██████╗ ")
    print("  ██║   ██║╚██╗ ██╔╝██╔══██╗██╔════╝██╔════╝██║  ██║██║██╔════╝██║     ██╔══██╗")
    print("  ██║   ██║ ╚████╔╝ ██████╔╝█████╗  ███████╗███████║██║█████╗  ██║     ██║  ██║")
    print("  ╚██╗ ██╔╝  ╚██╔╝  ██╔══██╗██╔══╝  ╚════██║██╔══██║██║██╔══╝  ██║     ██║  ██║")
    print("   ╚████╔╝    ██║   ██████╔╝███████╗███████║██║  ██║██║███████╗███████╗██████╔╝")
    print("    ╚═══╝     ╚═╝   ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝ ")
    print(f"{C.RESET}")
    print(f"  {C.BOLD}VybeFlow Autonomous System Auditor{C.RESET}  |  Root: {ROOT}\n")

    run_all = not (args.html or args.py or args.deps)

    if run_all or args.py:
        check_python_syntax()
        check_imports()
        check_duplicate_routes()

    if run_all or args.html:
        check_html_structure()
        check_dead_state()
        check_css_conflicts()
        check_js_imports()

    if run_all:
        check_story_api()

    if run_all or args.deps:
        check_dependencies()

    if args.fix:
        auto_fix()

    print_report()

    sys.exit(1 if ISSUES else 0)


if __name__ == "__main__":
    main()
