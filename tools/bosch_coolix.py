"""Generate IR codes for the Bosch Climate 3200i (Midea / Coolix protocol).

Output is the base64 "key_code" format the ZG-IR01 blaster learns and sends
(Broadlink-style pulse ticks of 1/32768 s), so codes can be sent with
zha.issue_zigbee_cluster_command on cluster 0xE004, command 2.

Usage:
  python3 bosch_coolix.py off
  python3 bosch_coolix.py cool 22 auto
  python3 bosch_coolix.py heat 21 40      # fan as a %, or low/medium/high
  python3 bosch_coolix.py --table      # every mode/temp/fan as YAML
"""

import base64
import sys

# Pulse timings in ticks (1 tick = 1/32768 s), taken from the learned codes.
HDR_MARK, HDR_SPACE = 138, 137  # ~4.2 ms each
BIT_MARK = 16                   # ~490 us
ONE_SPACE, ZERO_SPACE = 50, 16  # ~1.5 ms / ~490 us
FRAME_GAP = 162                 # ~4.9 ms between frames

# Coolix temperature table (4-bit, Gray-code-like), 17-30 °C.
TEMP_CODES = {
    17: 0b0000, 18: 0b0001, 19: 0b0011, 20: 0b0010, 21: 0b0110,
    22: 0b0111, 23: 0b0101, 24: 0b0100, 25: 0b1100, 26: 0b1101,
    27: 0b1001, 28: 0b1000, 29: 0b1010, 30: 0b1011,
}
MODES = {"cool": 0b00, "dry": 0b01, "auto": 0b10, "heat": 0b11}
# Fan: "auto", or a speed in percent (1-100). The exact percentage goes in the
# Midea extended frame; the main frame also carries a legacy fan level.
# Confirmed from captures: auto -> 0b101 (+ 102 in the extended frame),
# 20 % -> 0b111, 40 % -> 0b100, 60 % -> 0b010, 100 % -> 0b001.
FAN_AUTO_BITS, FAN_AUTO_PCT = 0b101, 102
FAN_LEVEL_BANDS = [(20, 0b111), (40, 0b100), (60, 0b010), (100, 0b001)]
FAN_PRESETS = {"low": 20, "medium": 60, "high": 100}
# Dry and auto modes (both confirmed by capture) ignore the
# fan setting: main-frame fan field 0b000, extended-frame value 101 (0x65).
FORCED_FAN_MODES = ("dry", "auto")
FORCED_FAN_BITS, FORCED_FAN_PCT = 0b000, 101
FAN_ONLY_TEMP = 0b1110  # fan-only mode = dry mode with this temp code

OFF_STATE = (0x7B, 0xE0)


def fan_pct(fan) -> int:
    """Normalise a fan setting to Midea's percentage (102 = auto)."""
    if fan in (None, "auto"):
        return FAN_AUTO_PCT
    pct = FAN_PRESETS.get(fan, fan)
    pct = int(pct)
    if not 1 <= pct <= 100:
        raise ValueError("fan must be 'auto', a preset or 1-100 %")
    return pct


def extended_frame(fan, mode: str = "") -> bytes:
    """Midea extended frame: D5, fan %, three feature bytes, sum checksum."""
    pct = FORCED_FAN_PCT if mode in FORCED_FAN_MODES else fan_pct(fan)
    body = bytes([0xD5, pct, 0x00, 0x00, 0x00])
    return body + bytes([sum(body) & 0xFF])


def state_bytes(mode: str, temp: int | None = None, fan="auto") -> tuple[int, int]:
    """Return the two Coolix payload bytes (after 0xB2) for a state."""
    if mode == "off":
        return OFF_STATE
    if mode in FORCED_FAN_MODES:
        fan_bits = FORCED_FAN_BITS
    elif fan_pct(fan) == FAN_AUTO_PCT:
        fan_bits = FAN_AUTO_BITS
    else:
        pct = fan_pct(fan)
        fan_bits = next(
            bits for limit, bits in FAN_LEVEL_BANDS if pct <= limit
        )
    if mode == "fan_only":
        mode_bits, temp_bits = MODES["dry"], FAN_ONLY_TEMP
    else:
        mode_bits = MODES[mode]
        temp_bits = TEMP_CODES[int(temp)]
    b1 = (fan_bits << 5) | 0b11111
    b2 = (temp_bits << 4) | (mode_bits << 2)
    return b1, b2


def coolix_frame(b1: int, b2: int) -> bytes:
    """Six-byte Coolix frame: each byte followed by its inverse."""
    out = bytearray()
    for b in (0xB2, b1, b2):
        out += bytes([b, b ^ 0xFF])
    return bytes(out)


def pulses_for(frames: list[bytes]) -> list[int]:
    ticks: list[int] = []
    for i, frame in enumerate(frames):
        if i:
            ticks.append(FRAME_GAP)  # space after previous stop mark
        ticks += [HDR_MARK, HDR_SPACE]
        for byte in frame:
            for bit in range(7, -1, -1):
                ticks += [BIT_MARK, ONE_SPACE if byte >> bit & 1 else ZERO_SPACE]
        ticks.append(BIT_MARK)  # stop mark
    return ticks


def encode(mode: str, temp: int | None = None, fan="auto") -> str:
    """Return the base64 key_code for the ZG-IR01."""
    frame = coolix_frame(*state_bytes(mode, temp, fan))
    frames = [frame, frame]
    if mode != "off":
        frames.append(extended_frame(fan, mode))
    ticks = pulses_for(frames)
    body = bytearray()
    for t in ticks:
        body += bytes([t]) if t < 256 else bytes([0, t >> 8, t & 0xFF])
    packet = bytes([0x26, 0x00]) + (len(body) + 4).to_bytes(2, "little") + body
    return base64.b64encode(packet).decode()


def decode_frames(b64: str) -> list[str]:
    """Decode a key_code back to hex frames (for checking)."""
    d = base64.b64decode(b64)
    n = int.from_bytes(d[2:4], "little")
    p, i, ticks = d[4:n], 0, []
    while i < len(p):
        v = p[i]; i += 1
        if v == 0:
            v = int.from_bytes(p[i:i + 2], "big"); i += 2
        ticks.append(v)
    frames, cur = [], None
    for j in range(0, len(ticks) - 1, 2):
        m, s = ticks[j], ticks[j + 1]
        if m > 100:
            cur = []; frames.append(cur); continue
        if cur is not None:
            cur.append(1 if s > 33 else 0)
    return [
        bytes(int("".join(map(str, f[k:k + 8])), 2) for k in range(0, 48, 8)).hex(" ").upper()
        for f in frames
    ]


def table() -> str:
    lines = ["# Generated Bosch Climate 3200i codes (Coolix) for ZG-IR01", f'off: "{encode("off")}"']
    fans = ["auto", *FAN_PRESETS]
    for mode in ("cool", "heat"):
        for fan in fans:
            for t in TEMP_CODES:
                lines.append(f'{mode}_{t}_{fan}: "{encode(mode, t, fan)}"')
    for mode in ("auto", "dry"):
        for t in TEMP_CODES:
            lines.append(f'{mode}_{t}: "{encode(mode, t)}"')
    for fan in fans:
        lines.append(f'fan_only_{fan}: "{encode("fan_only", None, fan)}"')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--table"]:
        sys.stdout.write(table())
    elif args:
        mode = args[0]
        temp = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        fan = args[2] if len(args) > 2 else (args[1] if len(args) > 1 and not args[1].isdigit() else "auto")
        fan = int(fan) if str(fan).isdigit() else fan
        print(encode(mode, temp, fan))
    else:
        print(__doc__)
