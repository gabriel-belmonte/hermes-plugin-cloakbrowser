"""Hermes plugin: CloakBrowser stealth Chromium backend.

This plugin adds a ``cloak_browser`` tool that drives a local CloakBrowser
instance (https://github.com/CloakHQ/CloakBrowser) over the Chrome DevTools
Protocol (CDP). CloakBrowser is a real Chromium binary with 71 fingerprint
patches at the C++ source level, so anti-bot systems score it as a normal
browser.

It is intentionally a *complementary* backend, not a core patch:
  - Hermes' built-in browser tools (browser_navigate, browser_click, ...) keep
    using Camofox / local Chromium / Browserbase as configured.
  - ``cloak_browser`` is a separate tool that talks straight to CloakBrowser's
    CDP endpoint (default http://127.0.0.1:9222) via Playwright-core.

You can ALSO make Hermes' built-in browser tools use CloakBrowser by pointing
the existing CDP path at it:  set  BROWSER_CDP_URL=http://127.0.0.1:9222
(and CLOAKBROWSER is running).  The built-in tools then drive the stealth
Chromium automatically — no code change needed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CDP = "http://127.0.0.1:9222"


def _cdp_url() -> str:
    return os.getenv("CLOAKBROWSER_URL", "").rstrip("/") or _DEFAULT_CDP


def _headless() -> bool:
    val = os.getenv("CLOAKBROWSER_HEADLESS", "true").strip().lower()
    return val not in ("false", "0", "no")


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["sudo", "docker", "info"],
            capture_output=True, timeout=10, check=False,
        )
        return True
    except Exception:
        return False


def _ensure_playwright() -> None:
    """Make sure playwright-core is importable; install lazily if missing."""
    try:
        import playwright  # noqa: F401
    except Exception:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "playwright-core"],
            check=False,
        )


def _browser():
    """Return a connected Playwright Chromium browser over CDP."""
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(_cdp_url())
    return pw, browser


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _navigate(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    url = params.get("url")
    if not url:
        return json.dumps({"success": False, "error": "missing url"})
    try:
        pw, browser = _browser()
        page = browser.contexts[0].new_page() if browser.contexts else browser.new_context().new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = page.title()
        body = page.inner_text()
        out = {
            "success": True,
            "url": page.url,
            "title": title,
            "text": body[:8000],
        }
        page.close()
        browser.close()
        pw.stop()
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _screenshot(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    url = params.get("url")
    if not url:
        return json.dumps({"success": False, "error": "missing url"})
    try:
        pw, browser = _browser()
        page = browser.new_context().new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        fd, path = tempfile.mkstemp(suffix=".png", prefix="cloak_")
        os.close(fd)
        page.screenshot(path=path, full_page=bool(params.get("full_page", False)))
        page.close()
        browser.close()
        pw.stop()
        return json.dumps({"success": True, "path": path})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _extract(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    # Alias of navigate that returns clean text (markdown-friendly).
    return _navigate(params)


def _status(params: Dict[str, Any], **kwargs: Any) -> str:
    del params, kwargs
    try:
        import requests

        r = requests.get(_cdp_url() + "/json/version", timeout=5)
        return json.dumps({
            "success": r.status_code == 200,
            "cdp": _cdp_url(),
            "browser": r.json().get("Browser", "?") if r.status_code == 200 else None,
            "headless": _headless(),
        })
    except Exception as e:
        return json.dumps({"success": False, "cdp": _cdp_url(), "error": str(e)})


# ---------------------------------------------------------------------------
# CLI / slash command: /cloak
# ---------------------------------------------------------------------------

def _cmd_handler(args: str) -> str:
    """Handle `/cloak up|down|status|logs`."""
    sub = (args or "status").strip().split()[0] if args else "status"
    if sub == "status":
        return _status({})
    if sub in ("up", "start"):
        if not _docker_available():
            return "Docker not available (need sudo docker)."
        cmd = [
            "sudo", "docker", "run", "-d", "--name", "cloakbrowser",
            "--restart", "unless-stopped",
            "-p", "127.0.0.1:9222:9222",
            "cloakhq/cloakbrowser", "cloakserve",
            "--headless" if _headless() else "",
        ]
        cmd = [c for c in cmd if c]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return f"started: {res.stdout.strip() or res.stderr.strip()}"
    if sub in ("down", "stop"):
        res = subprocess.run(
            ["sudo", "docker", "rm", "-f", "cloakbrowser"],
            capture_output=True, text=True, timeout=60,
        )
        return f"stopped: {res.stdout.strip() or res.stderr.strip()}"
    if sub == "logs":
        res = subprocess.run(
            ["sudo", "docker", "logs", "--tail", "40", "cloakbrowser"],
            capture_output=True, text=True, timeout=30,
        )
        return res.stdout or res.stderr
    return "usage: /cloak [up|down|status|logs]"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx):
    # --- Tool: cloak_browser (navigate / screenshot / extract / status) ---
    schema = {
        "name": "cloak_browser",
        "description": (
            "Drive the local CloakBrowser stealth Chromium (fingerprint-patched, "
            "passes Cloudflare/recaptcha). Use for sites that block normal "
            "headless browsers. Actions: navigate, screenshot, extract, status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "screenshot", "extract", "status"],
                    "description": "What to do",
                },
                "url": {"type": "string", "description": "Target URL"},
                "full_page": {
                    "type": "boolean",
                    "description": "screenshot full page (default false)",
                },
            },
            "required": ["action"],
        },
    }

    def _dispatch(params, **kwargs):
        action = params.get("action", "status")
        if action == "navigate":
            return _navigate(params, **kwargs)
        if action == "extract":
            return _extract(params, **kwargs)
        if action == "screenshot":
            return _screenshot(params, **kwargs)
        return _status(params, **kwargs)

    ctx.register_tool(
        name="cloak_browser",
        toolset="cloakbrowser",
        schema=schema,
        handler=_dispatch,
        description="Drive the local CloakBrowser stealth Chromium via CDP.",
    )

    # --- Slash command: /cloak up|down|status|logs ---
    ctx.register_command(
        "cloak",
        _cmd_handler,
        "Manage the CloakBrowser Docker container (up/down/status/logs).",
    )

    # --- Hook: log lifecycle ---
    def _on_call(tool_name, params, result):
        if tool_name == "cloak_browser":
            print(f"[cloakbrowser] {params.get('action')} -> {result[:80]}")

    ctx.register_hook("post_tool_call", _on_call)
