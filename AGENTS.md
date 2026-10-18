# Anti-Bot Web Scraping & Headless Browser Toolkit

This repository is pre-configured with a multi-tier anti-detect browser and scraping stack so webpage fetching works across WAFs, TLS fingerprinting, SPA rendering, and CAPTCHA/Turnstile challenges.

## Quick CLI Usage (`scraper.py`)

```bash
# Automatic 5-tier fallback (curl_cffi -> Patchright -> Camoufox+Xvfb+ClickSolver -> Jina Reader -> Tavily)
python3 scraper.py fetch "https://example.com"

# Force a specific tier:
python3 scraper.py fetch "https://example.com" --tier camoufox
python3 scraper.py fetch "https://example.com" --tier patchright
python3 scraper.py fetch "https://example.com" --tier tavily

# Solve local image CAPTCHA via ddddocr:
python3 scraper.py ocr path/to/captcha.png

# Generate 6-digit 2FA TOTP code for a saved account or secret (compatible with https://2fa.show):
python3 scraper.py 2fa <username_or_secret>
```

## Authenticated Scraping & GitHub OAuth Fallback
- Fallback GitHub accounts (with username, password, 2FA secret, and mailbox API URL) are stored locally in `.secrets/accounts.json` (`chmod 600`, git-ignored).
- When a target website requires login / GitHub OAuth:
  1. Load credentials via `scraper.load_saved_accounts()`.
  2. Sign in with `username` and `password`.
  3. Generate the 6-digit 2FA code via `scraper.generate_totp(secret)` / `scraper.fetch_totp_from_2fa_show(secret)` (or `https://2fa.show`), or fetch email verification codes from `mailbox_url` if prompted.
  4. Persist browser `storage_state` under `.auth_state/` (git-ignored) to reuse sessions across requests.

## Installed Components
- **TLS Fingerprint Impersonation**: `curl_cffi`, `scrapling` (`Fetcher`, `StealthyFetcher`)
- **Undetected Chromium**: `patchright` (patched CDP leak), `DrissionPage`, `agent-browser`
- **C++ Anti-Detect Firefox + Virtual Display**: `camoufox[geoip]` + `xvfb` (`headless="virtual"`, `humanize=True`)
- **Automated CAPTCHA Solvers**: `playwright-captcha` (Cloudflare Interstitial / Turnstile / reCAPTCHA ClickSolver), `ddddocr` (offline OCR/slider CAPTCHA)
- **Cloud Extraction Fallback**: `tavily-python` (`TAVILY_API_KEY` configured in environment) & Jina Reader (`https://r.jina.ai/<url>`)
