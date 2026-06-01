from __future__ import annotations

import math

from .models import SensorPacket, Target, utc_now_iso

REPORT_HEADER = bytes.fromhex("F4 F3 F2 F1")
REPORT_FOOTER = bytes.fromhex("F8 F7 F6 F5")
TARGET_BLOCK_SIZE = 5


def extract_report_frames(buffer: bytes) -> tuple[list[bytes], bytes]:
    working = bytearray(buffer)
    frames: list[bytes] = []

    while True:
        header_index = working.find(REPORT_HEADER)
        if header_index < 0:
            keep = len(REPORT_HEADER) - 1
            return frames, bytes(working[-keep:]) if working else b""

        if header_index > 0:
            del working[:header_index]

        if len(working) < 10:
            return frames, bytes(working)

        payload_length = int.from_bytes(working[4:6], "little")
        frame_length = 4 + 2 + payload_length + 4
        if len(working) < frame_length:
            return frames, bytes(working)

        footer = working[frame_length - 4 : frame_length]
        if footer != REPORT_FOOTER:
            del working[0]
            continue

        frames.append(bytes(working[:frame_length]))
        del working[:frame_length]


def _polar_to_cartesian(distance_m: int, angle_deg: int) -> tuple[float, float]:
    distance_mm = float(distance_m) * 1000.0
    radians = math.radians(angle_deg)
    x_mm = distance_mm * math.sin(radians)
    y_mm = distance_mm * math.cos(radians)
    return x_mm, y_mm


def _parse_target(block: bytes) -> Target:
    angle_raw = block[0]
    distance_m = block[1]
    speed_direction_raw = block[2]
    speed_kmh = block[3]
    snr = block[4]

    angle_deg = int(angle_raw) - 0x80
    x_mm, y_mm = _polar_to_cartesian(distance_m, angle_deg)

    return Target(
        x_mm=x_mm,
        y_mm=y_mm,
        speed_mps=float(speed_kmh) / 3.6,
        angle_deg=float(angle_deg),
        distance_m=float(distance_m),
        speed_kmh=float(speed_kmh),
        speed_direction_raw=int(speed_direction_raw),
        snr=int(snr),
        confidence=float(snr),
    )


def parse_report_frame(frame: bytes) -> SensorPacket:
    if len(frame) < 10:
        raise ValueError("Frame too short")
    if frame[:4] != REPORT_HEADER:
        raise ValueError("Invalid report frame header")
    if frame[-4:] != REPORT_FOOTER:
        raise ValueError("Invalid report frame footer")

    payload_length = int.from_bytes(frame[4:6], "little")
    payload = frame[6:-4]
    if len(payload) != payload_length:
        raise ValueError("Frame payload length mismatch")

    target_count = 0
    alarm = 0
    targets: list[Target] = []

    if payload:
        if len(payload) < 2:
            raise ValueError("Report payload missing header fields")
        target_count = payload[0]
        alarm = payload[1]
        target_bytes = payload[2:]
        available_targets = len(target_bytes) // TARGET_BLOCK_SIZE
        parsed_targets = min(target_count, available_targets)
        for index in range(parsed_targets):
            start = index * TARGET_BLOCK_SIZE
            block = target_bytes[start : start + TARGET_BLOCK_SIZE]
            targets.append(_parse_target(block))

    fields = {
        "frame_type": "report",
        "payload_length": payload_length,
        "target_count": target_count,
        "alarm": alarm,
        "has_approaching_target": alarm == 1,
    }

    return SensorPacket(
        ts=utc_now_iso(),
        raw_hex=frame.hex(" "),
        raw_text=None,
        presence=bool(targets),
        targets=targets,
        fields=fields,
    )
