# hermes-plugin-cloakbrowser

A self-hosted **stealth Chromium** browser backend for [Hermes Agent](https://github.com/NousResearch/hermes-agent), powered by [CloakBrowser](https://github.com/CloakHQ/CloakBrowser).

CloakBrowser is a real Chromium binary with **71 fingerprint patches at the C++ source level** — it passes Cloudflare Turnstile, FingerprintJS, and reCAPTCHA v3 (0.9 server-verified score). This plugin lets Hermes drive it without touching core code.

> Complementary to the built-in **Camofox** backend, not a replacement. Use CloakBrowser for sites that challenge Camofox, or as a drop-in Chromium via Hermes' existing CDP path.

## Features

- 🛡️ **`cloak_browser` tool** — navigate / screenshot / status against the local stealth Chromium over CDP.
- ⌨️ **`/cloak` command** — manage the Docker container (`/cloak up|down|status|logs`).
- 🔌 **Optional built-in integration** — point Hermes' existing `BROWSER_CDP_URL` at CloakBrowser and the native `browser_*` tools drive it automatically.
- 🏠 **100% local** — no cloud, no API key. Loopback-only by default.

## Install

```bash
# 1. Clone into Hermes plugins dir
git clone https://github.com/gabriel-belmonte/hermes-plugin-cloakbrowser \
  ~/.hermes/plugins/hermes-plugin-cloakbrowser

# 2. Start CloakBrowser (loopback-only)
cd ~/.hermes/plugins/hermes-plugin-cloakbrowser
sudo docker compose up -d

# 3. Verify (port is auto-picked from 9222; check the container log for the port)
sudo docker ps --filter name=cloakbrowser
curl -s http://127.0.0.1:$(sudo docker port cloakbrowser-9223 9222/tcp | cut -d: -f2)/json/version

# 4. Restart Hermes
```

## Use it

**As a standalone tool** (no config change):

```
cloak_browser(action="navigate", url="https://example.com")
cloak_browser(action="screenshot", url="https://bot.target.site")
cloak_browser(action="status")
```

Manage the container:

```
/cloak up
/cloak status
/cloak logs
/cloak down
```

**As the built-in browser backend** — add to `~/.hermes/.env`:

```bash
# Use the auto-picked port CloakBrowser actually bound (check: sudo docker ps --filter name=cloakbrowser)
BROWSER_CDP_URL=http://127.0.0.1:9223
```

Now `browser_navigate`, `browser_click`, `browser_snapshot`, … all run on the stealth Chromium. No code change.

## Anti-bot test results (verified 2026-07-23)

| Test | Target | Result |
|------|--------|--------|
| Fingerprint detection | `bot.sannysoft.com` | ✅ **All checks pass** — `WebDriver: missing (passed)`, no Phantom/Selenium flags, real `NVIDIA RTX 3080` WebGL, normal UA `Chrome/146 (Windows 10)` |
| Cloudflare Turnstile | `nowsecure.nl` | ⚠️ Page loads (no 403 block) but the **"Verify you are human" challenge iframe appears** |

**Bottom line:** CloakBrowser defeats fingerprint/automation detection (the part
that normally burns a bot instantly). Active challenges like Cloudflare
Turnstile still need two things this plugin's default setup does not provide:

1. **A residential proxy** — the VPS runs on a datacenter IP, and Cloudflare
   Turnstile blocks those by design regardless of fingerprint quality.
2. **`humanize=True`** — human-like mouse/keyboard/scroll. This is a flag of the
   Python/JS `cloakbrowser.launch()` API, *not* of the `cloakserve` CDP server.
   The server only honours seed/proxy/timezone/locale via the CDP query string
   (`http://host:9222?fingerprint=<seed>&proxy=<residential>&geoip=True`).

To clear Turnstile you must run a CloakBrowser instance launched with a
residential proxy + `humanize=True` (see the CloakBrowser README), then point
`CLOAKBROWSER_URL` at it. This plugin's `cloak_browser` tool then drives it over
CDP like any other target.

## Config

| Env var | Default | Purpose |
|---------|---------|---------|
| `CLOAKBROWSER_URL` | `http://127.0.0.1:9222` | CDP endpoint |
| `CLOAKBROWSER_HEADLESS` | `true` | headless vs headed |

## How it works

```
Hermes
  ├─ built-in browser_* tools ──► BROWSER_CDP_URL ──► CloakBrowser :<auto>  (option B)
  └─ cloak_browser tool ────────► CDP ──────────────► CloakBrowser :<auto>  (option A)
                                         ▲
                              cloakhq/cloakbrowser (Docker, loopback-only)
```

The plugin talks to CloakBrowser over the **Chrome DevTools Protocol** using
Hermes' own `agent-browser` CLI (the same binary Hermes' native `browser_*`
tools use). This reuses Hermes' installed browser stack — no second Playwright
needed, and it works even on the offline-restricted venv.

## Requirements

- Docker (rootless or `sudo docker`)
- `agent-browser` CLI — **already shipped with Hermes** (used as-is, no install needed)
- A running `cloakhq/cloakbrowser` container (defaults to the first free loopback
  port from `9222`; override with `CLOAKBROWSER_PORT`)

## License

MIT — plugin. CloakBrowser itself is MIT (CloakHQ).
