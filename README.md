# hermes-plugin-cloakbrowser

A self-hosted **stealth Chromium** browser backend for [Hermes Agent](https://github.com/NousResearch/hermes-agent), powered by [CloakBrowser](https://github.com/CloakHQ/CloakBrowser).

CloakBrowser is a real Chromium binary with **71 fingerprint patches at the C++ source level** — it passes Cloudflare Turnstile, FingerprintJS, and reCAPTCHA v3 (0.9 server-verified score). This plugin lets Hermes drive it without touching core code.

> Complementary to the built-in **Camofox** backend, not a replacement. Use CloakBrowser for sites that challenge Camofox, or as a drop-in Chromium via Hermes' existing CDP path.

## Features

- 🛡️ **`cloak_browser` tool** — navigate / screenshot / extract / status against the local stealth Chromium over CDP.
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

# 3. Verify
curl -s http://127.0.0.1:9222/json/version

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
BROWSER_CDP_URL=http://127.0.0.1:9222
```

Now `browser_navigate`, `browser_click`, `browser_snapshot`, … all run on the stealth Chromium. No code change.

## Config

| Env var | Default | Purpose |
|---------|---------|---------|
| `CLOAKBROWSER_URL` | `http://127.0.0.1:9222` | CDP endpoint |
| `CLOAKBROWSER_HEADLESS` | `true` | headless vs headed |

## How it works

```
Hermes
  ├─ built-in browser_* tools ──► BROWSER_CDP_URL ──► CloakBrowser :9222  (option B)
  └─ cloak_browser tool ────────► CDP ──────────────► CloakBrowser :9222  (option A)
                                         ▲
                              cloakhq/cloakbrowser (Docker, loopback)
```

The plugin talks to CloakBrowser over the **Chrome DevTools Protocol** via `playwright-core` — the same protocol the built-in local browser uses, so behavior matches Hermes' native browser tooling.

## Requirements

- Docker (rootless or `sudo docker`)
- `playwright-core` (auto-installed on first use)
- A running `cloakhq/cloakbrowser` container on `:9222`

## License

MIT — plugin. CloakBrowser itself is MIT (CloakHQ).
