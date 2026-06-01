from __future__ import annotations

import os
import random
import threading
import time
from typing import Callable

import serial
import serial.tools.list_ports

from .models import SensorStats
from .parser import parse_packet


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
                    while not self._stop_event.is_set():
                        frame = ser.readline()
                        if not frame:
                            continue
                        self.stats.bytes_received += len(frame)
                        packet = parse_packet(frame)
                        self.stats.valid_frames += 1
                        self.on_packet(packet.to_dict())
            except Exception as exc:
                self.stats.parse_errors += 1
                self.stats.serial_disconnects += 1
                self._emit_error(f"Serial error: {exc}")
                time.sleep(1)

    def _run_simulation(self) -> None:
        while not self._stop_event.is_set():
            target_count = random.choice([0, 1, 1, 2])
            targets = []
            for _ in range(target_count):
                targets.append(
                    {
                        "x": random.uniform(-3000, 3000),
                        "y": random.uniform(200, 6000),
                        "speed": random.uniform(-1.5, 1.5),
                    }
                )
            payload = {
                "presence": target_count > 0,
                "targets": targets,
                "source": "simulation",
            }
            raw = (str(payload).replace("'", '"') + "\n").encode("utf-8")
            packet = parse_packet(raw)
            self.stats.valid_frames += 1
            self.stats.bytes_received += len(raw)
            self.on_packet(packet.to_dict())
            time.sleep(0.2)


def env_serial_config() -> tuple[str | None, int, bool]:
    port = os.getenv("LD2451_PORT") or None
    baud = int(os.getenv("LD2451_BAUD", "115200"))
    simulate = os.getenv("LD2451_SIMULATE", "0") == "1"
    return port, baud, simulate
