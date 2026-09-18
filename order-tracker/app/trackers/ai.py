"""AI 兜底：官网没有免费 API、或接口/页面被拦、出现人机验证时使用。

优先把官网页面文本交给大模型抽取；没有配置模型密钥时，用页面关键词抽取（仍不编造轨迹）。
人机验证页无法自动解开，会如实标记。
"""

from __future__ import annotations

import json
import os
import re

import httpx

from ..status import infer_code_from_text, label_for
from .browser import URL_BUILDERS, fetch_page_text
from .models import TrackResult

CAPTCHA_HINTS = (
    "captcha",
    "verify you are human",
    "安全验证",
    "人机验证",
    "fire hydrant",
    "select all images",
    "cloudflare",
)


def _is_captcha(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in CAPTCHA_HINTS)


def _ai_configured() -> bool:
    return bool(os.environ.get("ORDER_TRACKER_AI_API_KEY"))


async def _extract_with_llm(number: str, carrier: str, page_text: str) -> dict | None:
    api_key = os.environ.get("ORDER_TRACKER_AI_API_KEY")
    if not api_key:
        return None
    base = os.environ.get("ORDER_TRACKER_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("ORDER_TRACKER_AI_MODEL", "gpt-4o-mini")
    prompt = (
        "你是物流轨迹抽取器。只根据给定官网页面原文提取状态，禁止编造。"
        "返回 JSON：code(delivered|in_transit|out_for_delivery|available_for_pickup|"
        "info_received|label_created|not_found|awaiting_carrier|exception|captcha|unknown),"
        "status_text(中文短状态), latest(一句最新节点)。"
        f"\n承运商: {carrier}\n运单号: {number}\n页面原文:\n{page_text[:6000]}"
    )
    async with httpx.AsyncClient(timeout=40.0) as client:
        response = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return None
    return json.loads(match.group(0))


async def track_with_ai(number: str, carrier: str) -> TrackResult:
    builder = URL_BUILDERS.get(carrier) or URL_BUILDERS["aftership"]
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
            source="ai",
            ok=False,
            error=str(exc)[:200],
        )
    if _is_captcha(text):
        parsed = None
        if _ai_configured():
            try:
                parsed = await _extract_with_llm(number, carrier, text)
            except Exception:
                parsed = None
        if parsed and parsed.get("code") not in {None, "captcha", "unknown"}:
            code = parsed["code"]
            return TrackResult(
                number=number,
                carrier=carrier,
                code=code,
                status_text=parsed.get("status_text") or label_for(code),
                latest=parsed.get("latest") or "",
                source="ai-llm",
            )
        return TrackResult(
            number=number,
            carrier=carrier,
            code="blocked",
            status_text="人机验证",
            latest="页面出现人机验证，AI 无法自动解开验证码",
            source="ai-captcha",
            ok=False,
            error="captcha",
        )
    if not text.strip():
        return TrackResult(
            number=number,
            carrier=carrier,
            code="blocked",
            status_text="官网拦截",
            latest="页面空白",
            source="ai",
            ok=False,
            error="empty page",
        )
    if _ai_configured():
        try:
            parsed = await _extract_with_llm(number, carrier, text)
            if parsed and parsed.get("code"):
                code = parsed["code"]
                return TrackResult(
                    number=number,
                    carrier=carrier,
                    code=code,
                    status_text=parsed.get("status_text") or label_for(code),
                    latest=(parsed.get("latest") or text[:200]).replace("\n", " ")[:400],
                    source="ai-llm",
                )
        except Exception:
            pass
    code = infer_code_from_text(text)
    return TrackResult(
        number=number,
        carrier=carrier,
        code=code,
        status_text=label_for(code),
        latest=text.replace("\n", " ")[:240],
        source="ai-page",
    )
