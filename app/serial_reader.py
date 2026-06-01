from __future__ import annotations

import os
import random
import threading
import time
from typing import Callable

import serial
import serial.tools.list_ports

from .models import SensorPacket, SensorStats, Target, utc_now_iso
from .parser import extract_report_frames, parse_report_frame


def list_serial_ports() -> list[str]:
    return [p.device for p in serial.tools.list_ports.comports()]


class SerialReaderService:
    def __init__(
        self,
        on_packet: Callable[[dict], None],
        on_error: Callable[[str], None] | None = None,
        port: str | None = None,
        baud_rate: int = 115200,
        simulate: bool = False,
    ) -> None:
        self.on_packet = on_packet
        self.on_error = on_error
        self.port = port
        self.baud_rate = baud_rate
        self.simulate = simulate
        self.stats = SensorStats()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def reconfigure(self, port: str | None, baud_rate: int, simulate: bool) -> None:
        with self._lock:
            self.port = port
            self.baud_rate = baud_rate
            self.simulate = simulate
        self.stop()
        self.start()

    def _emit_error(self, message: str) -> None:
        if self.on_error:
            self.on_error(message)

    def _select_port(self) -> str | None:
        ports = list_serial_ports()

        if self.port:
            # If user configured a missing path, fall back to first detected port.
            if self.port in ports or os.path.exists(self.port):
                return self.port
            if ports:
                self._emit_error(
                    f"Configured port {self.port} not found; falling back to {ports[0]}"
                )
                return ports[0]
            return None

        if not ports:
            return None
        return ports[0]

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                simulate = self.simulate
                baud_rate = self.baud_rate

            if simulate:
                self._run_simulation()
                continue

            selected_port = self._select_port()
            if selected_port is None:
                configured = f" Configured: {self.port}." if self.port else ""
                self._emit_error(
                    f"No serial port found.{configured} Connect USB-serial adapter and retry."
                )
                time.sleep(1.5)
                continue

            try:
                with serial.Serial(selected_port, baud_rate, timeout=0.6) as ser:
                    buffer = b""
                    while not self._stop_event.is_set():
                        chunk = ser.read(ser.in_waiting or 64)
                        if not chunk:
                            continue
                        self.stats.bytes_received += len(chunk)
                        buffer += chunk
                        frames, buffer = extract_report_frames(buffer)
                        for frame in frames:
                            try:
                                packet = parse_report_frame(frame)
                            except ValueError:
                                self.stats.parse_errors += 1
                                continue
                            self.stats.valid_frames += 1
                            self.on_packet(packet.to_dict())

                        if len(buffer) > 4096:
                            self.stats.parse_errors += 1
                            buffer = buffer[-64:]
            except Exception as exc:
                self.stats.parse_errors += 1
                self.stats.serial_disconnects += 1
                self._emit_error(f"Serial error: {exc}")
                time.sleep(1)

    def _run_simulation(self) -> None:
        while not self._stop_event.is_set():
            target_count = random.choice([0, 1, 1, 2])
            targets: list[Target] = []
            for _ in range(target_count):
                distance_m = random.uniform(0.5, 6.0)
                angle_deg = random.uniform(-45, 45)
                radians = angle_deg * 3.141592653589793 / 180.0
                x_mm = distance_m * 1000.0 * __import__("math").sin(radians)
                y_mm = distance_m * 1000.0 * __import__("math").cos(radians)
                speed_mps = random.uniform(0.0, 1.5)
                targets.append(
                    Target(
                        x_mm=x_mm,
                        y_mm=y_mm,
                        speed_mps=speed_mps,
                        angle_deg=angle_deg,
                        distance_m=distance_m,
                        speed_kmh=speed_mps * 3.6,
                        speed_direction_raw=random.choice([0, 1]),
                        snr=random.randint(4, 20),
                        confidence=float(random.randint(4, 20)),
                    )
                )
            packet = SensorPacket(
                ts=utc_now_iso(),
                raw_hex="",
                raw_text="simulation",
                presence=target_count > 0,
                targets=targets,
                fields={
                    "frame_type": "simulation",
                    "target_count": target_count,
                    "alarm": 1 if target_count > 0 else 0,
                    "has_approaching_target": target_count > 0,
                },
            )
            self.stats.valid_frames += 1
            self.stats.bytes_received += max(1, target_count * 5)
            self.on_packet(packet.to_dict())
            time.sleep(0.2)


def env_serial_config() -> tuple[str | None, int, bool]:
    port = os.getenv("LD2451_PORT") or None
    baud = int(os.getenv("LD2451_BAUD", "115200"))
    simulate = os.getenv("LD2451_SIMULATE", "0") == "1"
    return port, baud, simulate
