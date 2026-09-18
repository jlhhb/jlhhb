"""8DT / 永利八达通：固定 HTTP 接口，可批量。"""

from __future__ import annotations

import httpx

from ..status import infer_code_from_text, label_for
from .models import TrackResult

ENDPOINT = "https://post.8dt.com/apiTrackDedicatedNo/fetchTrackingNo"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://epost.8dt.com",
    "Referer": "https://epost.8dt.com/track.html",
    "User-Agent": "Mozilla/5.0",
}


def _latest_from(item: dict) -> str:
    events = item.get("trackingInfo") or []
    if not events:
        return ""
    first = events[0]
    date = first.get("trackingDate") or ""
    time = first.get("trackingTm") or ""
    place = first.get("place") or first.get("country") or ""
    note = first.get("note") or ""
    local_no = item.get("trackingNo") or ""
    parts = [f"{date} {time}".strip(), place, note]
    text = " · ".join(p for p in parts if p)
    if local_no and local_no != first.get("trackingNo"):
        text = f"{text}（末端 {local_no}）"
    return text


async def track_many(numbers: list[str], timeout: float = 25.0) -> dict[str, TrackResult]:
    unique = [n for n in dict.fromkeys(numbers) if n]
    if not unique:
        return {}
    body = {"trackDedicatedNo": ",".join(unique)}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ENDPOINT, data=body, headers=HEADERS)
        response.raise_for_status()
        payload = response.json()
    results: dict[str, TrackResult] = {}
    if not isinstance(payload, list):
        raise RuntimeError("8DT 接口返回格式异常")
    for number, item in zip(unique, payload):
        status = (item or {}).get("status") or ""
        latest = _latest_from(item or {})
        code = infer_code_from_text(f"{status} {latest}")
        if status == "成功签收":
            code = "delivered"
        elif status == "运往当地":
            code = "in_transit"
        elif status == "已上网":
            code = "info_received"
        elif status == "未上网":
            code = "not_found"
        elif status == "到达待取":
            code = "available_for_pickup"
        results[number] = TrackResult(
            number=number,
            carrier="8dt",
            code=code,
            status_text=status or label_for(code),
            latest=latest or status,
            source="8dt-api",
            extra={"dest": (item or {}).get("destCode"), "local": (item or {}).get("trackingNo")},
        )
    for number in unique:
        results.setdefault(
            number,
            TrackResult(
                number=number,
                carrier="8dt",
                code="unknown",
                status_text="未知",
                source="8dt-api",
                ok=False,
                error="接口未返回该单号",
            ),
        )
    return results
