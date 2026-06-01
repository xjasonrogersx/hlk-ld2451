# HLK LD2451 Live Viewer

NOTE: I NOT MANAGED TO MAKE THS WORK YET

Live USB-serial viewer for HLK LD2451 sensor data with:

- Real-time 2D radar-style target plot
- Presence timeline
- Raw packet stream table

The app runs a Python server that reads serial data and streams updates to a web dashboard.

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies.
3. Start the server.
4. Open the dashboard URL.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Configuration

Environment variables:

- `LD2451_PORT`: serial port path, for example `/dev/ttyUSB0`
- `LD2451_BAUD`: baud rate, default `115200`
- `LD2451_HISTORY_SIZE`: in-memory history size, default `300`
- `LD2451_SIMULATE`: set `1` to generate simulated packets when no sensor is connected

Example:

```bash
LD2451_PORT=/dev/ttyUSB0 LD2451_BAUD=115200 uvicorn app.main:app --reload
```

## API Endpoints

- `GET /api/health`: server status
- `GET /api/ports`: detected serial ports
- `GET /api/snapshot`: current state + recent history summary
- `POST /api/config`: update serial config and reconnect reader
- `GET /ws`: live packet stream WebSocket

## Notes About LD2451 Frames

Different LD2451 tools and firmware can output frames in different formats. This MVP parser handles:

- JSON lines
- Human-readable text lines with coordinate-like values
- Raw bytes fallback as hex

If your module output format differs, update parsing logic in `app/parser.py`.

https://www.laskakit.cz/user/related_files/hlk-ld2451_user_manual_v1-0.pdf
