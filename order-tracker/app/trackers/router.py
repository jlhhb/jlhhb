"""查询链路：先免费 API，没有接口或失败/人机验证再走 AI。"""

from __future__ import annotations

import re

from . import eight_dt
from .ai import track_with_ai
from .models import TrackResult

EIGHT_DT_RE = re.compile(r"^EWS[A-Z0-9]+YQ$", re.I)
UPS_RE = re.compile(r"^1Z[A-Z0-9]{16}$", re.I)
USPS_RE = re.compile(r"^9[234]\d{18,24}$")
FEDEX_RE = re.compile(r"^87\d{10,14}$")
DPD_LINE_RE = re.compile(r"^8412\d+$")
TGX_RE = re.compile(r"^81600\d+$")
CANADA_RE = re.compile(r"^\d{16}$")

SHEET_CARRIER = {
    "usps": "usps",
    "ups": "ups",
    "fedex": "fedex",
    "canada post": "canada_post",
    "canadapost": "canada_post",
    "dpd": "dpd",
    "8dt": "8dt",
    "永利": "8dt",
    "tgx": "tgx",
    "team global": "tgx",
}


def normalize_carrier(number: str, sheet_carrier: str = "") -> str:
    token = (number or "").strip()
    hinted = SHEET_CARRIER.get((sheet_carrier or "").strip().lower())
    if not hinted and sheet_carrier:
        lowered = sheet_carrier.strip().lower()
        for key, value in SHEET_CARRIER.items():
            if key in lowered:
                hinted = value
                break
    if EIGHT_DT_RE.match(token):
        return "8dt"
    if UPS_RE.match(token):
        return "ups"
    if USPS_RE.match(token):
        return "usps"
    if FEDEX_RE.match(token):
        return "fedex"
    if DPD_LINE_RE.match(token):
        return "dpd"
    if TGX_RE.match(token):
        return "tgx"
    if hinted == "canada_post" or (CANADA_RE.match(token) and not hinted):
        return "canada_post"
    return hinted or "aftership"


async def try_free_api(number: str, sheet_carrier: str = "") -> TrackResult | None:
    carrier = normalize_carrier(number, sheet_carrier)
    if carrier == "8dt":
        batch = await eight_dt.track_many([number])
        return batch[number]
    return None


def _api_success(result: TrackResult | None) -> bool:
    if result is None:
        return False
    if not result.ok:
        return False
    if result.code in {"blocked", "unknown"}:
        return False
    if result.source.endswith("api"):
        return True
    return result.code not in {"not_found"} or bool(result.latest)


async def track_one(number: str, sheet_carrier: str = "", use_ai: bool = True) -> TrackResult:
    api_result = await try_free_api(number, sheet_carrier)
    if _api_success(api_result):
        return api_result  # type: ignore[return-value]
    if not use_ai:
        return api_result or TrackResult(
            number=number,
            carrier=normalize_carrier(number, sheet_carrier),
            code="unknown",
            status_text="未查询",
            latest="无免费 API，已跳过 AI",
            source="skipped",
            ok=False,
            error="ai disabled",
        )
    carrier = normalize_carrier(number, sheet_carrier)
    return await track_with_ai(number, carrier)


async def track_group(
    numbers: list[str],
    sheet_carrier_by_number: dict[str, str] | None = None,
    use_ai: bool = True,
    use_browser: bool | None = None,
) -> dict[str, TrackResult]:
    if use_browser is not None:
        use_ai = use_browser
    mapping = sheet_carrier_by_number or {}
    unique = [n for n in dict.fromkeys(numbers) if n]
    results: dict[str, TrackResult] = {}
    eight = [n for n in unique if normalize_carrier(n, mapping.get(n, "")) == "8dt"]
    rest = [n for n in unique if n not in eight]
    if eight:
        results.update(await eight_dt.track_many(eight))
    for number in rest:
        results[number] = await track_one(number, mapping.get(number, ""), use_ai=use_ai)
    return results
