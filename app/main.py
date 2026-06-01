from __future__ import annotations

import asyncio
import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .serial_reader import SerialReaderService, env_serial_config, list_serial_ports

HISTORY_SIZE = int(os.getenv("LD2451_HISTORY_SIZE", "300"))


class AppState:
    def __init__(self) -> None:
        self.latest_packet: dict[str, Any] | None = None
        self.history: deque[dict[str, Any]] = deque(maxlen=HISTORY_SIZE)
        self.errors: deque[str] = deque(maxlen=30)
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.service: SerialReaderService | None = None
        self.port: str | None = None
        self.baud_rate: int = 115200
        self.simulate: bool = False

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self.clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


state = AppState()


def _on_packet(packet: dict[str, Any]) -> None:
    state.latest_packet = packet
    state.history.append(packet)
    if state.loop:
        asyncio.run_coroutine_threadsafe(
            state.broadcast({"type": "sensor_update", "payload": packet}),
            state.loop,
        )


def _on_error(message: str) -> None:
    state.errors.append(message)
    if state.loop:
        asyncio.run_coroutine_threadsafe(
            state.broadcast({"type": "error", "message": message}),
            state.loop,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.loop = asyncio.get_running_loop()
    port, baud, simulate = env_serial_config()
    state.port = port
    state.baud_rate = baud
    state.simulate = simulate
    state.service = SerialReaderService(
        on_packet=_on_packet,
        on_error=_on_error,
        port=port,
        baud_rate=baud,
        simulate=simulate,
    )
    state.service.start()
    try:
        yield
    finally:
        if state.service:
            state.service.stop()


app = FastAPI(title="HLK LD2451 Live Viewer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")


class ConfigUpdate(BaseModel):
    port: str | None = Field(default=None)
    baud_rate: int = Field(default=115200, ge=1200, le=1000000)
    simulate: bool = False


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(static_path / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "running": bool(state.service and state.service.running),
        "port": state.port,
        "baud_rate": state.baud_rate,
        "simulate": state.simulate,
    }


@app.get("/api/ports")
async def ports() -> dict[str, Any]:
    return {"ports": list_serial_ports()}


@app.get("/api/snapshot")
async def snapshot() -> dict[str, Any]:
    service_stats = state.service.stats.to_dict() if state.service else {}
    return {
        "latest": state.latest_packet,
        "history_count": len(state.history),
        "errors": list(state.errors),
        "stats": service_stats,
        "config": {
            "port": state.port,
            "baud_rate": state.baud_rate,
            "simulate": state.simulate,
        },
    }


@app.post("/api/config")
async def update_config(config: ConfigUpdate) -> dict[str, Any]:
    if state.service is None:
        raise HTTPException(status_code=500, detail="Serial service not initialized")
    state.port = config.port
    state.baud_rate = config.baud_rate
    state.simulate = config.simulate
    state.service.reconfigure(config.port, config.baud_rate, config.simulate)
    return {
        "ok": True,
        "config": {
            "port": state.port,
            "baud_rate": state.baud_rate,
            "simulate": state.simulate,
        },
    }


@app.websocket("/ws")
async def ws_updates(ws: WebSocket) -> None:
    await ws.accept()
    state.clients.add(ws)
    try:
        if state.latest_packet:
            await ws.send_json({"type": "sensor_update", "payload": state.latest_packet})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        state.clients.discard(ws)
    except Exception:
        state.clients.discard(ws)
