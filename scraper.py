#!/usr/bin/env python3
"""Multi-tier anti-bot web scraper and local CAPTCHA solver utility."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

TierName = Literal["auto", "curl", "patchright", "camoufox", "jina", "tavily"]

CHALLENGE_PATTERNS = (
    re.compile(r"<title>\s*(Just a moment\.\.\.|Attention Required! \| Cloudflare|Access Denied|Security Check)", re.I),
    re.compile(r"cf-browser-verification|cf_chl_opt|turnstile|challenge-platform", re.I),
    re.compile(r"Verify you are human|Enable JavaScript and cookies to continue", re.I),
)


@dataclass
class ScrapeResult:
    url: str
    tier: str
    status: int
    title: str
    content: str
    html: str = ""
    challenge_solved: bool = False
    error: str | None = None


def is_blocked_or_challenge(html: str, status: int) -> bool:
    if status in (401, 403, 429, 503):
        return True
    if not html or len(html.strip()) < 120:
        return True
    head = html[:15000]
    return any(pattern.search(head) for pattern in CHALLENGE_PATTERNS)


def extract_clean_text(html: str, output_format: str = "markdown") -> tuple[str, str]:
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()

    if output_format == "html":
        return title, html

    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            output_format="markdown" if output_format == "markdown" else "txt",
            include_links=True,
            include_tables=True,
        )
        if extracted and len(extracted.strip()) > 80:
            return title, extracted.strip()
    except Exception:
        pass

    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.body_width = 0
        return title, converter.handle(html).strip()
    except Exception:
        return title, html


def fetch_tier_curl(url: str, timeout: int = 25, impersonate: str = "chrome") -> ScrapeResult:
    from curl_cffi import requests as cf_requests

    resp = cf_requests.get(url, impersonate=impersonate, timeout=timeout, allow_redirects=True)
    html = resp.text or ""
    title, content = extract_clean_text(html)
    return ScrapeResult(url=str(resp.url), tier="curl_cffi", status=resp.status_code, title=title, content=content, html=html)


async def fetch_tier_patchright(url: str, timeout_ms: int = 30000, wait_sec: float = 2.0) -> ScrapeResult:
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(wait_sec)
            html = await page.content()
            status = resp.status if resp else 200
            title, content = extract_clean_text(html)
            return ScrapeResult(url=page.url, tier="patchright", status=status, title=title, content=content, html=html)
        finally:
            await browser.close()


def _find_camoufox_executable() -> str | None:
    home = Path(os.environ.get("HOME", "/home/hoplite"))
    candidates = [
        home / ".cache/camoufox/browsers/official/135.0.1-beta.24/camoufox-bin",
        Path("/home/hoplite/.cache/camoufox/browsers/official/135.0.1-beta.24/camoufox-bin"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


async def fetch_tier_camoufox(url: str, timeout_ms: int = 45000, wait_sec: float = 3.0) -> ScrapeResult:
    from camoufox.async_api import AsyncCamoufox
    from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

    # Firefox refuses to start if $HOME is not owned by the current effective UID
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        home_dir = os.environ.get("HOME", "/root")
        try:
            if os.stat(home_dir).st_uid != 0:
                os.chown(home_dir, 0, 0)
        except OSError:
            pass

    # Use virtual Xvfb display when available for maximum Cloudflare Turnstile pass rate
    headless_mode: bool | str = "virtual" if os.name == "posix" else True
    solved = False
    exec_path = _find_camoufox_executable()
    launch_kwargs = {"headless": headless_mode, "humanize": True}
    if exec_path:
        launch_kwargs["executable_path"] = exec_path

    async with AsyncCamoufox(**launch_kwargs) as browser:
        page = await browser.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await asyncio.sleep(wait_sec)
        html = await page.content()
        status = resp.status if resp else 200

        if is_blocked_or_challenge(html, status):
            solver = ClickSolver(framework=FrameworkType.CAMOUFOX, page=page, max_attempts=3, attempt_delay=3)
            await solver.prepare()
            for ctype in (CaptchaType.CLOUDFLARE_INTERSTITIAL, CaptchaType.CLOUDFLARE_TURNSTILE):
                try:
                    await solver.solve_captcha(captcha_container=page, captcha_type=ctype)
                    solved = True
                    await asyncio.sleep(3.0)
                    break
                except Exception:
                    continue
            html = await page.content()

        title, content = extract_clean_text(html)
        return ScrapeResult(
            url=page.url,
            tier="camoufox",
            status=status,
            title=title,
            content=content,
            html=html,
            challenge_solved=solved,
        )


def fetch_tier_jina(url: str, timeout: int = 30) -> ScrapeResult:
    import httpx

    headers = {"Accept": "text/plain"}
    if os.environ.get("JINA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['JINA_API_KEY']}"
    resp = httpx.get(f"https://r.jina.ai/{url}", headers=headers, timeout=timeout, follow_redirects=True)
    text = resp.text.strip()
    return ScrapeResult(url=url, tier="jina_reader", status=resp.status_code, title="", content=text)


def fetch_tier_tavily(url: str) -> ScrapeResult:
    from tavily import TavilyClient

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set in environment")
    client = TavilyClient(api_key=api_key)
    res = client.extract(urls=[url])
    results = res.get("results") or []
    if not results:
        raise RuntimeError(f"Tavily extract returned no results: {res}")
    raw = results[0].get("raw_content", "")
    return ScrapeResult(url=url, tier="tavily_extract", status=200, title="", content=raw)


async def smart_scrape(url: str, tier: TierName = "auto", output_format: str = "markdown") -> ScrapeResult:
    if tier == "curl":
        res = fetch_tier_curl(url)
    elif tier == "patchright":
        res = await fetch_tier_patchright(url)
    elif tier == "camoufox":
        res = await fetch_tier_camoufox(url)
    elif tier == "jina":
        return fetch_tier_jina(url)
    elif tier == "tavily":
        return fetch_tier_tavily(url)
    else:
        # Auto fallback pipeline: curl_cffi -> patchright -> camoufox -> jina -> tavily
        last_error: str | None = None
        try:
            res = fetch_tier_curl(url)
            if not is_blocked_or_challenge(res.html, res.status) and len(res.content) > 80:
                if output_format == "html":
                    res.content = res.html
                return res
        except Exception as e:
            last_error = f"curl_cffi: {e}"

        try:
            res = await fetch_tier_patchright(url)
            if not is_blocked_or_challenge(res.html, res.status) and len(res.content) > 80:
                if output_format == "html":
                    res.content = res.html
                return res
        except Exception as e:
            last_error = f"patchright: {e}"

        try:
            res = await fetch_tier_camoufox(url)
            if not is_blocked_or_challenge(res.html, res.status) and len(res.content) > 60:
                if output_format == "html":
                    res.content = res.html
                return res
        except Exception as e:
            last_error = f"camoufox: {e}"

        try:
            res = fetch_tier_jina(url)
            if res.status == 200 and len(res.content) > 80:
                return res
        except Exception as e:
            last_error = f"jina: {e}"

        if os.environ.get("TAVILY_API_KEY"):
            try:
                return fetch_tier_tavily(url)
            except Exception as e:
                last_error = f"tavily: {e}"

        res.error = last_error
        return res

    if output_format == "html" and res.html:
        res.content = res.html
    return res


def solve_image_captcha(image_input: str | bytes | Path) -> str:
    """Offline OCR for image/alphanumeric CAPTCHAs using ddddocr."""
    import ddddocr

    ocr = ddddocr.DdddOcr(show_ad=False)
    if isinstance(image_input, (str, Path)):
        data = Path(image_input).read_bytes()
    else:
        data = image_input
    return ocr.classification(data)


def generate_totp(secret: str, interval: int = 30, digits: int = 6) -> str:
    """Generate 6-digit TOTP code locally (same RFC 6238 algorithm used by https://2fa.show)."""
    cleaned = re.sub(r"\s+", "", secret).upper()
    padding = (8 - len(cleaned) % 8) % 8
    key = base64.b32decode(cleaned + "=" * padding, casefold=True)
    counter = int(time.time()) // interval
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def fetch_totp_from_2fa_show(secret: str, timeout: int = 15) -> str:
    """Fetch 2FA code via 2fa.show or fallback to local RFC 6238 TOTP calculation."""
    cleaned = re.sub(r"\s+", "", secret).upper()
    try:
        from curl_cffi import requests as cf_requests

        resp = cf_requests.get(f"https://2fa.show/{cleaned}", impersonate="chrome", timeout=timeout)
        if resp.status_code == 200:
            m = re.search(r"\b(\d{6})\b", resp.text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return generate_totp(cleaned)


def load_saved_accounts(secrets_path: str = ".secrets/accounts.json") -> list[dict[str, str]]:
    """Load locally stored fallback login accounts (never committed to git)."""
    p = Path(secrets_path)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-tier anti-bot web scraper & CAPTCHA utility")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Fetch a webpage with multi-tier anti-bot fallback")
    p_fetch.add_argument("url", help="Target URL")
    p_fetch.add_argument(
        "--tier",
        choices=["auto", "curl", "patchright", "camoufox", "jina", "tavily"],
        default="auto",
        help="Force a specific scraping tier or use 'auto' cascading fallback",
    )
    p_fetch.add_argument("--format", choices=["markdown", "text", "html", "json"], default="markdown")

    p_ocr = sub.add_parser("ocr", help="Solve an image CAPTCHA file locally using ddddocr")
    p_ocr.add_argument("image_path", help="Path to the CAPTCHA image")

    p_2fa = sub.add_parser("2fa", help="Generate 6-digit 2FA TOTP code for a secret or saved username")
    p_2fa.add_argument("target", help="Base32 2FA secret or saved account username")

    args = parser.parse_args()
    if args.cmd == "ocr":
        print(solve_image_captcha(args.image_path))
        return
    if args.cmd == "2fa":
        secret = args.target
        for acc in load_saved_accounts():
            if acc.get("username") == args.target:
                secret = acc["totp_secret"]
                break
        print(generate_totp(secret))
        return

    result = asyncio.run(smart_scrape(args.url, tier=args.tier, output_format=args.format))
    if args.format == "json":
        payload = asdict(result)
        payload.pop("html", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"# [{result.tier}] {result.title or result.url} (HTTP {result.status})", file=sys.stderr)
        print(result.content)


if __name__ == "__main__":
    main()
