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
```

## Installed Components
- **TLS Fingerprint Impersonation**: `curl_cffi`, `scrapling` (`Fetcher`, `StealthyFetcher`)
- **Undetected Chromium**: `patchright` (patched CDP leak), `DrissionPage`, `agent-browser`
- **C++ Anti-Detect Firefox + Virtual Display**: `camoufox[geoip]` + `xvfb` (`headless="virtual"`, `humanize=True`)
- **Automated CAPTCHA Solvers**: `playwright-captcha` (Cloudflare Interstitial / Turnstile / reCAPTCHA ClickSolver), `ddddocr` (offline OCR/slider CAPTCHA)
- **Cloud Extraction Fallback**: `tavily-python` (`TAVILY_API_KEY` configured in environment) & Jina Reader (`https://r.jina.ai/<url>`)
