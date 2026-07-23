---
name: cloakbrowser-setup
description: >-
  Install and run CloakBrowser (stealth Chromium) as a self-hosted Hermes
  browser backend, and wire it into Hermes as a complementary backend or via
  the built-in CDP path. Use when the user wants anti-bot browsing, wants to
  replace or augment Camofox, or asks about CloakBrowser / stealth Chromium.
---

# CloakBrowser setup for Hermes

CloakBrowser is a stealth Chromium (71 C++ fingerprint patches) that passes
Cloudflare Turnstile, FingerprintJS, and reCAPTCHA v3. This skill installs it
locally and connects it to Hermes.

## Steps

1. **Start the container** (loopback-only, no public exposure):

   ```bash
   sudo docker run -d --name cloakbrowser \
     --restart unless-stopped \
     -p 127.0.0.1:9222:9222 \
     cloakhq/cloakbrowser cloakserve --headless
   ```

   Or via compose: `sudo docker compose -f docker-compose.yml up -d`.

2. **Verify CDP is up**:

   ```bash
   curl -s http://127.0.0.1:9222/json/version
   ```

3. **Two ways to use it from Hermes**:

   a) **Complementary tool (this plugin)** — call `cloak_browser`
      (navigate / screenshot / extract / status). No core change.
      Manage the container with `/cloak up|down|status|logs`.

   b) **Built-in browser tools** — point Hermes' existing CDP path at it so
      `browser_navigate`, `browser_click`, etc. drive the stealth Chromium:

      ```bash
      export BROWSER_CDP_URL=http://127.0.0.1:9222
      ```

      Add that to `~/.hermes/.env`. Restart Hermes. Done — no code change.

## Notes

- Bind to `127.0.0.1` only (never `0.0.0.0`) — the stealth browser must not
  be reachable from the internet.
- For sites that still challenge, add a residential proxy via the
  CloakBrowser `proxy=` launch flag and set `humanize=True`.
- CloakBrowser is MIT-licensed; the binary auto-downloads on first run.

## References

- Repo: https://github.com/CloakHQ/CloakBrowser
- Hermes plugin: https://github.com/gabriel-belmonte/hermes-plugin-cloakbrowser
