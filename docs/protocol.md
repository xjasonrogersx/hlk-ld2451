# HLK-LD2451 Protocol Notes

This document summarizes the serial protocol from `HLK-LD2451_serial_protocol.pdf` and the assumptions used in the application.

## Serial Settings

- Default baud: `115200`
- Data format: binary, little-endian
- Stop bits: `1`
- Parity: none
- Electrical level: TTL on the module side

## Command Frame Format

Configuration and query commands use this envelope:

- Header: `FD FC FB FA`
- Length: 2 bytes, little-endian
- Command word: 2 bytes, little-endian
- Command value: `N` bytes
- Footer: `04 03 02 01`

ACK frames use the same header/footer, with the command word returned as `sent_command | 0x0100`.

Examples from the PDF:

- Enable configuration command word: `0x00FF`
- End configuration command word: `0x00FE`
- Read firmware version: `0x00A0`
- Set baud rate: `0x00A1`

## Reporting Frame Format

Radar detection output uses a different binary frame envelope:

- Header: `F4 F3 F2 F1`
- Length: 2 bytes, little-endian
- Payload: variable length
- Footer: `F8 F7 F6 F5`

If no target is detected, the module can emit a frame with only header, length, and footer.

### Reporting Payload Layout

The PDF's Table 9 describes the payload as:

1. `target_count` - 1 byte
2. `alarm` - 1 byte
3. `target_info` repeated, 5 bytes per target

Each `target_info` block is interpreted in this project as:

1. `angle_raw` - 1 byte
2. `distance_m` - 1 byte
3. `speed_direction_raw` - 1 byte
4. `speed_kmh` - 1 byte
5. `snr` - 1 byte

Derived values:

- `angle_deg = angle_raw - 0x80`
- `x_mm = distance_m * 1000 * sin(angle_deg)`
- `y_mm = distance_m * 1000 * cos(angle_deg)`

## Known Ambiguity

The translated PDF appears inconsistent about the meaning of `speed_direction_raw`:

- Table text suggests `01 = approach`, `00 = move away`
- The worked example appears to imply the opposite

The current code preserves the raw direction byte and does not rely on it for plotting.

## Example Reporting Frame

From the PDF:

```text
F4 F3 F2 F1 11 00 03 01 8A 28 00 3C 15 8A 1E 01 3C 0F 76 5F 00 3C 0F F8 F7 F6 F5
```

Interpreted as:

- payload length `0x0011` = 17 bytes
- `target_count = 3`
- `alarm = 1`
- target 1: angle `10 deg`, distance `40 m`, speed `60 km/h`, snr `0x15`
- target 2: angle `10 deg`, distance `30 m`, speed `60 km/h`, snr `0x0F`
- target 3: angle `-10 deg`, distance `95 m`, speed `60 km/h`, snr `0x0F`

## What The App Implements

The application now parses binary reporting frames using the `F4 F3 F2 F1` / `F8 F7 F6 F5` envelope and little-endian length field.

Files:

- `app/parser.py`
- `app/serial_reader.py`

The app does not yet send configuration commands to the module. It currently reads and visualizes report frames only.
