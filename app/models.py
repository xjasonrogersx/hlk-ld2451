from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Target:
    x_mm: float
    y_mm: float
    speed_mps: float | None = None
    confidence: float | None = None
    angle_deg: float | None = None
    distance_m: float | None = None
    speed_kmh: float | None = None
    speed_direction_raw: int | None = None
    snr: int | None = None


@dataclass
class SensorPacket:
    ts: str
    raw_hex: str
    raw_text: str | None
    presence: bool
    targets: list[Target] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result


@dataclass
class SensorStats:
    valid_frames: int = 0
    parse_errors: int = 0
    serial_disconnects: int = 0
    bytes_received: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
