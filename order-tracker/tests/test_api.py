import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.jobs import run_job
from app.main import app
from app.sheet import load_table
from app.trackers.models import TrackResult
from tests.test_sheet import _sample


def test_health():
    client = TestClient(app)
    assert client.get("/api/health").json()["ok"] is True


def test_preview_file_and_refresh_without_browser(tmp_path):
    client = TestClient(app)
    xlsx = _sample(tmp_path / "s.xlsx")
    with xlsx.open("rb") as handle:
        res = client.post(
            "/api/preview-file",
            files={"file": ("s.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["counts"]["pending"] == 2
    assert data["counts"]["delivered"] == 1
    job_id = data["job_id"]

    async def fake_group(numbers, mapping=None, use_browser=True):
        out = {}
        for number in numbers:
            if number.startswith("EWS"):
                out[number] = TrackResult(
                    number=number,
                    carrier="8dt",
                    code="delivered",
                    status_text="成功签收",
                    latest="墨西哥签收",
                    source="8dt-api",
                )
            else:
                out[number] = TrackResult(
                    number=number,
                    carrier="ups",
                    code="label_created",
                    status_text="仅面单",
                    latest="Label Created",
                    source="test",
                )
        return out

    with patch("app.jobs.track_group", side_effect=fake_group):
        asyncio.run(run_job(job_id, use_browser=False))

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["status"] == "done"
    assert payload["download_ready"] is True
    dl = client.get(f"/api/jobs/{job_id}/xlsx")
    assert dl.status_code == 200
    out = tmp_path / "updated.xlsx"
    out.write_bytes(dl.content)
    table = load_table(out)
    by_name = {row.recipient: row.status_raw for row in table.rows}
    assert by_name["Axel Medina"] == "签收"
    assert by_name["Archer Rosenkrantz"] == "未填单号"
    assert by_name["Anderson Werner"] == "签收"
    assert by_name["Brenda Vincent"] == "仅面单"
