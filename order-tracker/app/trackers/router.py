"""根据单号形态和表格承运商列选择适配器。"""

from __future__ import annotations

import re

from . import eight_dt
from .browser import track_on_site
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
    "tgx": "tgx",
    "team global": "tgx",
}


def normalize_carrier(number: str, sheet_carrier: str = "") -> str:
    token = (number or "").strip()
    hinted = SHEET_CARRIER.get((sheet_carrier or "").strip().lower())
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
    if hinted == "canada_post" or (CANADA_RE.match(token) and hinted != "fedex"):
        if hinted == "canada_post" or (CANADA_RE.match(token) and not hinted):
            return "canada_post"
    return hinted or "aftership"


async def track_one(number: str, sheet_carrier: str = "", use_browser: bool = True) -> TrackResult:
    carrier = normalize_carrier(number, sheet_carrier)
    if carrier == "8dt":
        batch = await eight_dt.track_many([number])
        return batch[number]
    if carrier == "dpd":
        # 8412 多为国内专线号，末端 DPD 经常查无，仍走官网以便确认。
        if not use_browser:
            return TrackResult(
                number=number,
                carrier="dpd",
                code="not_found",
                status_text="官网查无",
                latest="DPD 专线号通常不是末端查询号",
                source="dpd-heuristic",
            )
        return await track_on_site("dpd", number)
    if not use_browser:
        return TrackResult(
            number=number,
            carrier=carrier,
            code="unknown",
            status_text="未查询",
            latest="已跳过浏览器查询",
            source="skipped",
            ok=False,
            error="browser disabled",
        )
    site = carrier if carrier in {"usps", "ups", "fedex", "canada_post", "tgx"} else "aftership"
    return await track_on_site(site, number)


async def track_group(
    numbers: list[str],
    sheet_carrier_by_number: dict[str, str] | None = None,
    use_browser: bool = True,
) -> dict[str, TrackResult]:
    mapping = sheet_carrier_by_number or {}
    unique = [n for n in dict.fromkeys(numbers) if n]
    results: dict[str, TrackResult] = {}
    eight = [n for n in unique if normalize_carrier(n, mapping.get(n, "")) == "8dt"]
    rest = [n for n in unique if n not in eight]
    if eight:
        results.update(await eight_dt.track_many(eight))
    for number in rest:
        results[number] = await track_one(number, mapping.get(number, ""), use_browser=use_browser)
    return results
