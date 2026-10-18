#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

if ! command -v xvfb-run >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq xvfb xauth dbus-x11 libgtk-3-0 libnotify-dev libnss3 libxss1 libasound2t64 libxtst6 xdg-utils fonts-liberation fonts-noto-cjk >/dev/null
fi

if ! python3 -c "import camoufox, patchright, playwright_captcha, scrapling, curl_cffi, ddddocr, tavily, trafilatura" >/dev/null 2>&1; then
  uv pip install --system --break-system-packages \
    "playwright<1.61" \
    patchright \
    "camoufox[geoip]" \
    playwright-captcha \
    "scrapling[all]" \
    DrissionPage \
    curl_cffi \
    ddddocr \
    tavily-python \
    trafilatura \
    beautifulsoup4 \
    lxml \
    httpx \
    html2text
fi

if [ ! -d "$HOME/.cache/camoufox/browsers/official/135.0.1-beta.24" ]; then
  python3 -m camoufox set official/stable/135.0.1-beta.24
  python3 -m camoufox fetch
fi

if ! patchright --version >/dev/null 2>&1 || [ ! -d "/tmp/hoplite/playwright-browsers" ] && [ ! -d "$HOME/.cache/ms-playwright" ]; then
  patchright install chromium
fi

if [ "$(id -u)" = "0" ] && [ -d "${HOME:-/home/hoplite}" ]; then
  chown root:root "${HOME:-/home/hoplite}" 2>/dev/null || true
fi
