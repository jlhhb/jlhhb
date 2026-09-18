from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import jobs

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="订单跟踪", version="0.2.0")


class PreviewBody(BaseModel):
    url: str = Field(..., min_length=8)


class BindBody(BaseModel):
    sheet_name: str | None = None
    tracking_col: int | None = None
    carrier_col: int | None = None
    status_col: int | None = None


class RefreshBody(BaseModel):
    use_ai: bool = True
    use_browser: bool | None = None
    sheet_name: str | None = None
    tracking_col: int | None = None
    carrier_col: int | None = None
    status_col: int | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/preview")
def preview(body: PreviewBody) -> dict:
    try:
        job = jobs.create_job(source_url=body.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jobs.preview_payload(job)


@app.post("/api/preview-file")
async def preview_file(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail="请上传 xlsx 表格")
    tmp = Path("/tmp") / f"upload-{file.filename}"
    tmp.write_bytes(await file.read())
    try:
        job = jobs.create_job(upload=tmp)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jobs.preview_payload(job)


@app.post("/api/jobs/{job_id}/bind")
def bind(job_id: str, body: BindBody) -> dict:
    if job_id not in jobs.JOBS:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        jobs.bind_job(
            job_id,
            sheet_name=body.sheet_name,
            tracking_col=body.tracking_col,
            carrier_col=body.carrier_col,
            status_col=body.status_col,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return jobs.preview_payload(jobs.JOBS[job_id])


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return jobs.preview_payload(job)


@app.post("/api/jobs/{job_id}/refresh")
async def refresh(job_id: str, body: RefreshBody | None = None) -> dict:
    job = jobs.JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status == "running":
        return jobs.preview_payload(job)
    payload = body or RefreshBody()
    if any(
        value is not None
        for value in (payload.sheet_name, payload.tracking_col, payload.carrier_col, payload.status_col)
    ):
        jobs.bind_job(
            job_id,
            sheet_name=payload.sheet_name,
            tracking_col=payload.tracking_col,
            carrier_col=payload.carrier_col,
            status_col=payload.status_col,
        )
    use_ai = payload.use_ai if payload.use_browser is None else payload.use_browser
    job.status = "running"
    asyncio.create_task(jobs.run_job(job_id, use_ai=use_ai))
    return jobs.preview_payload(job)


@app.get("/api/jobs/{job_id}/xlsx")
def download_xlsx(job_id: str) -> FileResponse:
    job = jobs.JOBS.get(job_id)
    if not job or not job.updated_xlsx or not job.updated_xlsx.exists():
        raise HTTPException(status_code=404, detail="还没有生成更新表")
    return FileResponse(
        job.updated_xlsx,
        filename="发货清单-已更新状态.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
