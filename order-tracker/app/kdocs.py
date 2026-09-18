"""读取金山文档公开分享链接（只读）。写回需企业开放平台，本工具改为导出 xlsx。"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

SHARE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?kdocs\.cn/(?:l|office/l|p)/([A-Za-z0-9]+)",
    re.I,
)
FILE_ID_RE = re.compile(r"kdocs\.cn/office/[^/]+/([A-Za-z0-9]+)", re.I)


class KdocsError(RuntimeError):
    pass


def parse_share_id(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise KdocsError("请填写金山文档链接")
    match = SHARE_RE.search(text)
    if match:
        return match.group(1)
    # 允许直接填分享码
    if re.fullmatch(r"[A-Za-z0-9]{8,}", text):
        return text
    raise KdocsError("无法识别金山文档链接，需形如 https://www.kdocs.cn/l/xxxxxx")


def download_share(url: str, dest: Path, timeout: float = 30.0) -> Path:
    share_id = parse_share_id(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    api = f"https://www.kdocs.cn/api/office/file/{share_id}/download"
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        meta = client.get(api)
        meta.raise_for_status()
        try:
            payload = meta.json()
        except Exception as exc:  # noqa: BLE001
            raise KdocsError("金山文档下载接口返回了非 JSON") from exc
        download_url = payload.get("download_url") or payload.get("url")
        if not download_url:
            raise KdocsError("该分享链接无法下载（可能未开启访客下载）")
        binary = client.get(download_url)
        binary.raise_for_status()
        dest.write_bytes(binary.content)
    if dest.stat().st_size < 32:
        raise KdocsError("下载到的表格文件过小，可能不是有效 xlsx")
    return dest
