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
    CDP endpoint (default http://127.0.0.1:9222) via the ``agent-browser`` CLI
    that Hermes already ships with.

You can ALSO make Hermes' built-in browser tools use CloakBrowser by pointing
the existing CDP path at it:  set  BROWSER_CDP_URL=http://127.0.0.1:9222
(and CloakBrowser is running).  The built-in tools then drive the stealth
Chromium automatically — no code change needed.

Driving strategy
----------------
We shell out to ``agent-browser`` (the same binary Hermes' own browser tools
use) with ``--cdp <port>``. This reuses Hermes' installed browser stack and
avoids pulling a second Playwright into the (often offline-restricted) venv.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Preferred CDP port. CloakBrowser's own default is 9222, but something may
# already answer there (e.g. a stray CDP / local-firecrawl's Lightpanda), so
# /cloak up probes upward and binds the first free port.
_DEFAULT_PORT = int(os.getenv("CLOAKBROWSER_PORT", "9222"))


def _cdp_url() -> str:
    return os.getenv("CLOAKBROWSER_URL", "").rstrip("/") or f"http://127.0.0.1:{_DEFAULT_PORT}"


def _cdp_port() -> int:
    try:
        return int(_cdp_url().rsplit(":", 1)[1].rstrip("/"))
    except Exception:
        return _DEFAULT_PORT


def _headless() -> bool:
    val = os.getenv("CLOAKBROWSER_HEADLESS", "true").strip().lower()
    return val not in ("false", "0", "no")


def _agent_browser() -> Optional[str]:
    """Locate the agent-browser CLI Hermes already ships with."""
    npm_root = subprocess.run(
        ["npm", "root", "-g"], capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    cand = os.path.join(npm_root, "agent-browser", "bin", "agent-browser.js")
    if os.path.exists(cand):
        return cand
    on_path = shutil.which("agent-browser")
    if on_path:
        return on_path
    return None


def _find_free_port(preferred: int, max_tries: int = 20) -> int:
    """Return the first free loopback TCP port at/after ``preferred``."""
    for port in range(preferred, preferred + max_tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            s.close()
            continue
    return preferred


def _docker_available() -> bool:
    try:
        subprocess.run(["sudo", "docker", "info"], capture_output=True, timeout=10, check=False)
        return True
    except Exception:
        return False


def _run_ab(args: list[str], timeout: int = 60) -> Dict[str, Any]:
    """Run agent-browser with --cdp <port> and return a JSON result dict."""
    ab = _agent_browser()
    if not ab:
        return {"success": False, "error": "agent-browser CLI not found (Hermes browser stack missing)"}
    cmd = ["node", ab, "--cdp", str(_cdp_port())] + args
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (res.stdout or res.stderr).strip()
    return {"success": res.returncode == 0, "output": out[:8000]}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _navigate(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    url = params.get("url")
    if not url:
        return json.dumps({"success": False, "error": "missing url"})
    open_res = _run_ab(["open", url])
    if not open_res["success"]:
        return json.dumps(open_res, ensure_ascii=False)
    snap = _run_ab(["snapshot"], timeout=45)
    return json.dumps({
        "success": snap["success"],
        "url": url,
        "snapshot": snap.get("output", ""),
    }, ensure_ascii=False)


def _screenshot(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    url = params.get("url")
    if not url:
        return json.dumps({"success": False, "error": "missing url"})
    open_res = _run_ab(["open", url])
    if not open_res["success"]:
        return json.dumps(open_res, ensure_ascii=False)
    fd, path = tempfile.mkstemp(suffix=".png", prefix="cloak_")
    os.close(fd)
    shot = _run_ab(["screenshot", path], timeout=45)
    if shot["success"]:
        return json.dumps({"success": True, "path": path})
    return json.dumps(shot, ensure_ascii=False)


def _status(params: Dict[str, Any], **kwargs: Any) -> str:
    del params, kwargs
    try:
        import requests

        r = requests.get(_cdp_url() + "/json/version", timeout=5)
        if r.status_code == 200:
            return json.dumps({
                "success": True,
                "cdp": _cdp_url(),
                "browser": r.json().get("Browser", "?"),
                "headless": _headless(),
            })
        return json.dumps({"success": False, "cdp": _cdp_url(), "error": f"HTTP {r.status_code}"})
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
        port = _find_free_port(_DEFAULT_PORT)
        cmd = [
            "sudo", "docker", "run", "-d", "--name", f"cloakbrowser-{port}",
            "--restart", "unless-stopped",
            "-p", f"127.0.0.1:{port}:9222",
            "cloakhq/cloakbrowser", "cloakserve",
            "--headless" if _headless() else "",
        ]
        cmd = [c for c in cmd if c]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            return f"FAILED: {res.stderr.strip() or res.stdout.strip()}"
        os.environ["CLOAKBROWSER_PORT"] = str(port)
        os.environ["CLOAKBROWSER_URL"] = f"http://127.0.0.1:{port}"
        return f"started on port {port}: {res.stdout.strip()}"
    if sub in ("down", "stop"):
        ps = subprocess.run(
            ["sudo", "docker", "ps", "-q", "-f", "name=cloakbrowser"],
            capture_output=True, text=True, timeout=60,
        )
        out = []
        for cid in ps.stdout.split():
            r = subprocess.run(
                ["sudo", "docker", "rm", "-f", cid.strip()],
                capture_output=True, text=True, timeout=60,
            )
            out.append(r.stdout.strip() or r.stderr.strip())
        return "stopped: " + (" ".join(out) if out else "(none running)")
    if sub == "logs":
        res = subprocess.run(
            ["sudo", "docker", "logs", "--tail", "40", f"cloakbrowser-{_DEFAULT_PORT}"],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            ps = subprocess.run(
                ["sudo", "docker", "ps", "-q", "-f", "name=cloakbrowser"],
                capture_output=True, text=True, timeout=30,
            )
            cid = ps.stdout.strip().split()[0] if ps.stdout.strip() else None
            if cid:
                res = subprocess.run(
                    ["sudo", "docker", "logs", "--tail", "40", cid],
                    capture_output=True, text=True, timeout=30,
                )
        return res.stdout or res.stderr
    return "usage: /cloak [up|down|status|logs]"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx):
    schema = {
        "name": "cloak_browser",
        "description": (
            "Drive the local CloakBrowser stealth Chromium (fingerprint-patched, "
            "passes Cloudflare/recaptcha) via CDP using Hermes' agent-browser. "
            "Use for sites that block normal headless browsers. "
            "Actions: navigate, screenshot, status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "screenshot", "status"],
                    "description": "What to do",
                },
                "url": {"type": "string", "description": "Target URL"},
            },
            "required": ["action"],
        },
    }

    def _dispatch(params, **kwargs):
        action = params.get("action", "status")
        if action == "navigate":
            return _navigate(params, **kwargs)
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

    ctx.register_command(
        "cloak",
        _cmd_handler,
        "Manage the CloakBrowser Docker container (up/down/status|logs).",
    )

    def _on_call(tool_name, params, result):
        if tool_name == "cloak_browser":
            print(f"[cloakbrowser] {params.get('action')} -> {result[:80]}")

    ctx.register_hook("post_tool_call", _on_call)
