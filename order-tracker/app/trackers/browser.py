"""公开跟踪页：用系统 Chrome 抽页面文本，再按关键词归类。不经过大模型。"""

from __future__ import annotations

import os
from typing import Callable

from ..status import infer_code_from_text, label_for
from .models import TrackResult

CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome-stable")

URL_BUILDERS: dict[str, Callable[[str], str]] = {
    "usps": lambda n: f"https://tools.usps.com/go/TrackConfirmAction?tLabels={n}",
    "ups": lambda n: f"https://www.ups.com/track?tracknum={n}",
    "fedex": lambda n: f"https://www.fedex.com/fedextrack/?trknbr={n}",
    "canada_post": lambda n: f"https://www.canadapost-postescanada.ca/track-reperage/en#/details/{n}",
    "dpd": lambda n: f"https://tracking.dpd.de/status/en_US/parcel/{n}",
    "tgx": lambda n: f"https://www.aftership.com/track/{n}",
    "aftership": lambda n: f"https://www.aftership.com/track/{n}",
}


async def fetch_page_text(url: str, wait_ms: int = 6000) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 1000},
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(wait_ms)
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            return text or ""
        finally:
            await browser.close()


def _clip_latest(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    useful = [
        line
        for line in lines
        if any(
            key in line.lower()
            for key in (
                "deliver",
                "transit",
                "label",
                "awaiting",
                "arrived",
                "facility",
                "sign",
                "签收",
                "运输",
                "can't find",
                "not found",
                "out for",
            )
        )
    ]
    return " / ".join(useful[:4])[:400]


async def track_on_site(carrier: str, number: str) -> TrackResult:
    builder = URL_BUILDERS.get(carrier)
    if not builder:
        return TrackResult(
            number=number,
            carrier=carrier,
            code="unknown",
            status_text="未知",
            ok=False,
            error="没有对应的公开跟踪页",
        )
    url = builder(number)
    try:
        text = await fetch_page_text(url)
    except Exception as exc:  # noqa: BLE001
        return TrackResult(
            number=number,
            carrier=carrier,
            code="blocked",
            status_text="官网拦截",
            latest=str(exc)[:200],
            source=f"{carrier}-browser",
            ok=False,
            error=str(exc)[:200],
        )
    if not text.strip():
        return TrackResult(
            number=number,
            carrier=carrier,
            code="blocked",
            status_text="官网拦截",
            latest="页面空白（常见于机房 IP 被拒）",
            source=f"{carrier}-browser",
            ok=False,
            error="empty page",
        )
    code = infer_code_from_text(text)
    if "we can't find that tracking number" in text.lower() or "keine daten" in text.lower():
        code = "not_found"
    return TrackResult(
        number=number,
        carrier=carrier,
        code=code,
        status_text=label_for(code),
        latest=_clip_latest(text) or text[:240].replace("\n", " "),
        source=f"{carrier}-browser",
    )
