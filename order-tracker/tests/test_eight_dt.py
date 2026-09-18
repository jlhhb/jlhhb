import asyncio
from unittest.mock import patch

from app.trackers.eight_dt import track_many


def test_eight_dt_parses_payload():
    payload = [
        {
            "status": "成功签收",
            "trackingNo": "CNMEX1057787551",
            "destCode": "MX",
            "trackingInfo": [
                {
                    "trackingDate": "2026-09-12",
                    "trackingTm": "10:00",
                    "place": "Monterrey",
                    "note": "Delivered",
                    "trackingNo": "EWSMM260824000268YQ",
                }
            ],
        }
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResp()

    with patch("app.trackers.eight_dt.httpx.AsyncClient", return_value=FakeClient()):
        results = asyncio.run(track_many(["EWSMM260824000268YQ"]))
    item = results["EWSMM260824000268YQ"]
    assert item.code == "delivered"
    assert item.status_text == "成功签收"
    assert "Monterrey" in item.latest
    assert item.source == "8dt-api"
