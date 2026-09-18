"""内存任务：读表 → 只查未到货 → 写回状态列。"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .kdocs import download_share
from .sheet import SheetTable, apply_results, list_sheets, load_table
from .status import label_for
from .trackers.router import track_group

JOBS: dict[str, "Job"] = {}


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")


@dataclass
class Job:
    id: str
    source_url: str
    workdir: Path
    source_xlsx: Path
    sheets: list[dict] = field(default_factory=list)
    table: SheetTable | None = None
    status: str = "ready"
    logs: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    updated_xlsx: Path | None = None
    error: str = ""
    done: int = 0
    total: int = 0
    use_ai: bool = True

    def log(self, message: str) -> None:
        self.logs.append(f"{_now()}  {message}")


def create_job(source_url: str = "", upload: Path | None = None) -> Job:
    job_id = uuid.uuid4().hex[:12]
    workdir = Path(tempfile.gettempdir()) / "order-tracker-jobs" / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    source_xlsx = workdir / "source.xlsx"
    if upload:
        source_xlsx.write_bytes(upload.read_bytes())
        url = ""
    else:
        url = source_url
        download_share(source_url, source_xlsx)
    sheets = list_sheets(source_xlsx)
    table = load_table(source_xlsx)
    job = Job(
        id=job_id,
        source_url=url,
        workdir=workdir,
        source_xlsx=source_xlsx,
        sheets=sheets,
        table=table,
        total=table.pending_count,
    )
    job.log(
        f"已读取工作表「{table.sheet_name}」：共 {len(table.rows)} 行，未到货 {table.pending_count}，"
        f"已签收 {table.delivered_count}，无单号 {table.missing_count}"
    )
    JOBS[job_id] = job
    return job


def bind_job(
    job_id: str,
    sheet_name: str | None = None,
    tracking_col: int | None = None,
    carrier_col: int | None = None,
    status_col: int | None = None,
) -> Job:
    job = JOBS[job_id]
    table = load_table(
        job.source_xlsx,
        sheet_name=sheet_name,
        tracking_col=tracking_col,
        carrier_col=carrier_col,
        status_col=status_col,
    )
    job.table = table
    job.total = table.pending_count
    job.results = []
    job.updated_xlsx = None
    job.status = "ready"
    job.log(
        f"列映射：表={table.sheet_name} 运单号列={table.columns.tracking} "
        f"运输公司列={table.columns.carrier} 状态列={table.columns.status}；"
        f"未到货 {table.pending_count}，无单号 {table.missing_count}"
    )
    return job


def preview_payload(job: Job) -> dict[str, Any]:
    table = job.table
    assert table is not None
    pending = [
        {
            "excel_row": row.excel_row,
            "recipient": row.recipient,
            "carrier": row.carrier_raw,
            "tracking": row.tracking_raw,
            "numbers": row.tracking_numbers,
            "status": row.status_raw or "未到货",
        }
        for row in table.rows
        if row.needs_query
    ]
    missing = [
        {"excel_row": row.excel_row, "recipient": row.recipient, "status": "未填单号"}
        for row in table.rows
        if row.skip_reason == "missing_tracking"
    ]
    return {
        "job_id": job.id,
        "sheets": job.sheets,
        "sheet_name": table.sheet_name,
        "headers": table.headers,
        "columns": {
            "carrier": table.columns.carrier,
            "tracking": table.columns.tracking,
            "status": table.columns.status,
            "latest": table.columns.latest,
        },
        "counts": {
            "rows": len(table.rows),
            "pending": table.pending_count,
            "delivered": table.delivered_count,
            "missing": table.missing_count,
        },
        "pending": pending,
        "missing": missing,
        "status": job.status,
        "logs": job.logs,
        "results": job.results,
        "download_ready": bool(job.updated_xlsx and job.updated_xlsx.exists()),
        "error": job.error,
        "done": job.done,
        "total": job.total,
    }


def _merge_row_results(parts: list) -> dict[str, str]:
    if not parts:
        return {"status": "未知", "latest": "", "code": "unknown"}
    if all(p.code == "delivered" for p in parts):
        code = "delivered"
    elif any(p.code == "exception" for p in parts):
        code = "exception"
    elif any(p.code in {"in_transit", "out_for_delivery", "available_for_pickup"} for p in parts):
        code = next(
            p.code
            for p in parts
            if p.code in {"out_for_delivery", "available_for_pickup", "in_transit"}
        )
    else:
        code = parts[0].code
    latest = " | ".join(f"{p.number}: {p.status_text} {p.latest}".strip() for p in parts)
    status = "签收" if code == "delivered" else label_for(code)
    if code == "blocked" and any("人机验证" in (p.status_text or "") for p in parts):
        status = "人机验证"
    return {"status": status, "latest": latest[:800], "code": code}


async def run_job(job_id: str, use_ai: bool = True, use_browser: bool | None = None) -> None:
    if use_browser is not None:
        use_ai = use_browser
    job = JOBS[job_id]
    table = job.table
    if table is None:
        job.status = "error"
        job.error = "任务没有表格"
        return
    job.status = "running"
    job.use_ai = use_ai
    job.done = 0
    job.results = []
    updates: dict[int, dict[str, str]] = {}

    for row in table.rows:
        if row.skip_reason == "missing_tracking":
            updates[row.excel_row] = {
                "status": "未填单号",
                "latest": "",
                "queried_at": _now(),
            }
            job.results.append(
                {
                    "excel_row": row.excel_row,
                    "recipient": row.recipient,
                    "tracking": "",
                    "status": "未填单号",
                    "latest": "",
                    "source": "sheet",
                }
            )

    pending_rows = [row for row in table.rows if row.needs_query]
    job.total = len(pending_rows)
    numbers: list[str] = []
    carrier_map: dict[str, str] = {}
    for row in pending_rows:
        for number in row.tracking_numbers:
            numbers.append(number)
            carrier_map[number] = row.carrier_raw
    job.log(f"开始查询 {len(pending_rows)} 行 / {len(set(numbers))} 个运单号（先免费 API，失败再 AI）")

    try:
        tracked = await track_group(numbers, carrier_map, use_ai=use_ai)
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)
        job.log(f"查询失败：{exc}")
        return

    for row in pending_rows:
        parts = [tracked[n] for n in row.tracking_numbers if n in tracked]
        merged = _merge_row_results(parts)
        skipped_only = parts and all(p.source == "skipped" for p in parts)
        status_value = (row.status_raw or "未到货") if skipped_only else merged["status"]
        latest_value = "已跳过 AI 查询" if skipped_only else merged["latest"]
        updates[row.excel_row] = {
            "status": status_value,
            "latest": latest_value,
            "queried_at": _now(),
        }
        job.results.append(
            {
                "excel_row": row.excel_row,
                "recipient": row.recipient,
                "tracking": " / ".join(row.tracking_numbers),
                "status": status_value,
                "latest": latest_value,
                "source": ",".join(sorted({p.source for p in parts if p.source})),
            }
        )
        job.done += 1
        job.log(f"{row.recipient or '未命名'} → {status_value}（{(parts[0].source if parts else '')}）")

    dest = job.workdir / "updated.xlsx"
    apply_results(
        job.source_xlsx,
        dest,
        updates,
        columns=table.columns,
        sheet_name=table.sheet_name,
    )
    job.updated_xlsx = dest
    job.status = "done"
    job.log("已写回状态列，可在本页查看汇总，并下载更新表导入金山文档")
