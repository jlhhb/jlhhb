"""把各承运商返回值归一成表格用的中文状态。"""

from __future__ import annotations

DELIVERED_MARKERS = (
    "签收",
    "已签收",
    "成功签收",
    "delivered",
    "delivery successful",
    "successful delivery",
)

SKIP_QUERY_MARKERS = DELIVERED_MARKERS

STATUS_LABELS = {
    "delivered": "签收",
    "in_transit": "运输中",
    "out_for_delivery": "派送中",
    "available_for_pickup": "到达待取",
    "info_received": "已上网",
    "label_created": "仅面单",
    "not_found": "官网查无",
    "awaiting_carrier": "等待交接",
    "exception": "异常",
    "missing_tracking": "未填单号",
    "blocked": "官网拦截",
    "unknown": "未知",
}


def is_delivered_text(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in (m.lower() for m in DELIVERED_MARKERS))


def label_for(code: str) -> str:
    return STATUS_LABELS.get(code, STATUS_LABELS["unknown"])


def infer_code_from_text(text: str) -> str:
    raw = (text or "").lower()
    if not raw.strip():
        return "unknown"
    if any(x in raw for x in ("can't find", "cannot find", "not found", "查无", "no tracking", "no data")):
        return "not_found"
    if any(x in raw for x in ("label created", "shipment info confirmed", "info received", "已上网", "预报")):
        return "label_created" if "label created" in raw else "info_received"
    if any(x in raw for x in ("awaiting item", "waiting for item", "usps awaiting")):
        return "awaiting_carrier"
    if any(x in raw for x in ("notice card left", "available for pickup", "待取", "pick up")):
        return "available_for_pickup"
    if any(x in raw for x in ("out for delivery", "派送")):
        return "out_for_delivery"
    if any(x in raw for x in ("delivered", "签收", "successful delivery", "left at front")):
        return "delivered"
    if any(x in raw for x in ("in transit", "on the way", "运输", "运往当地", "processed", "arrived")):
        return "in_transit"
    if any(x in raw for x in ("exception", "alert", "failed", "异常")):
        return "exception"
    return "unknown"
