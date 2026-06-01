from __future__ import annotations

import json
import math
import re
from typing import Any

from .models import SensorPacket, Target, utc_now_iso

KEY_VALUE_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(-?\d+(?:\.\d+)?)")
COORD_PATTERN = re.compile(
    r"(?:x\s*[:=]\s*(-?\d+(?:\.\d+)?)).{0,16}?(?:y\s*[:=]\s*(-?\d+(?:\.\d+)?))",
    re.IGNORECASE,
)
PAIR_PATTERN = re.compile(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
DIST_ANGLE_PATTERN = re.compile(
    r"(?:d(?:ist(?:ance)?)?\s*[:=]\s*(\d+(?:\.\d+)?)).{0,16}?(?:a(?:ngle)?\s*[:=]\s*(-?\d+(?:\.\d+)?))",
    re.IGNORECASE,
)


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _presence_from_text(text: str) -> bool | None:
    lowered = text.lower()
    if any(k in lowered for k in ["no target", "empty", "idle", "absence"]):
        return False
    if any(k in lowered for k in ["presence", "occupied", "motion", "human", "target"]):
        return True
    return None


def _targets_from_json(obj: dict[str, Any]) -> list[Target]:
    targets: list[Target] = []
    maybe_targets = obj.get("targets") or obj.get("points") or obj.get("tracks")
    if not isinstance(maybe_targets, list):
        return targets

    for item in maybe_targets:
        if not isinstance(item, dict):
            continue
        x = _coerce_float(item.get("x") or item.get("x_mm"))
        y = _coerce_float(item.get("y") or item.get("y_mm"))
        if x is None or y is None:
            continue
        speed = _coerce_float(item.get("speed") or item.get("speed_mps"))
        conf = _coerce_float(item.get("confidence") or item.get("conf"))
        targets.append(Target(x_mm=x, y_mm=y, speed_mps=speed, confidence=conf))
    return targets


def _targets_from_text(raw_text: str) -> list[Target]:
    targets: list[Target] = []

    for m in COORD_PATTERN.finditer(raw_text):
        x = _coerce_float(m.group(1))
        y = _coerce_float(m.group(2))
        if x is not None and y is not None:
            targets.append(Target(x_mm=x, y_mm=y))

    for m in PAIR_PATTERN.finditer(raw_text):
        x = _coerce_float(m.group(1))
        y = _coerce_float(m.group(2))
        if x is not None and y is not None:
            targets.append(Target(x_mm=x, y_mm=y))

    if targets:
        return targets

    for m in DIST_ANGLE_PATTERN.finditer(raw_text):
        dist = _coerce_float(m.group(1))
        angle = _coerce_float(m.group(2))
        if dist is None or angle is None:
            continue
        radians = math.radians(angle)
        x = dist * math.cos(radians)
        y = dist * math.sin(radians)
        targets.append(Target(x_mm=x, y_mm=y))

    return targets


def parse_packet(raw: bytes) -> SensorPacket:
    raw_hex = raw.hex(" ")
    raw_text = raw.decode("utf-8", errors="ignore").strip() or None

    fields: dict[str, Any] = {}
    targets: list[Target] = []
    presence = False

    if raw_text:
        try:
            parsed_json = json.loads(raw_text)
            if isinstance(parsed_json, dict):
                fields = parsed_json
                targets = _targets_from_json(parsed_json)
                explicit_presence = parsed_json.get("presence")
                if isinstance(explicit_presence, bool):
                    presence = explicit_presence
                else:
                    presence = bool(targets)
        except json.JSONDecodeError:
            fields = {
                match.group(1): float(match.group(2))
                for match in KEY_VALUE_PATTERN.finditer(raw_text)
            }
            targets = _targets_from_text(raw_text)
            presence_from_text = _presence_from_text(raw_text)
            if presence_from_text is None:
                presence = bool(targets)
            else:
                presence = presence_from_text

    return SensorPacket(
        ts=utc_now_iso(),
        raw_hex=raw_hex,
        raw_text=raw_text,
        presence=presence,
        targets=targets,
        fields=fields,
    )
