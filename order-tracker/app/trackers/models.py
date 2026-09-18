from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackResult:
    number: str
    carrier: str
    code: str
    status_text: str
    latest: str = ""
    source: str = ""
    ok: bool = True
    error: str = ""
    extra: dict = field(default_factory=dict)
