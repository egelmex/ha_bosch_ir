# Bosch Climate 3200i IR protocol (Midea "Coolix" + extended frame)

Decoded from nine captures of the Bosch remote and verified on the AC.
`tools/verify_captures.py` checks the encoder against those captures.

## Timing

Pulse durations in the blaster's `key_code` are ticks of 1/32768 s.

| Element | Ticks | Approx. |
|---|---|---|
| Header mark / space | 138 / 137 | 4.2 ms / 4.2 ms |
| Bit mark | 16 | 490 µs |
| `0` space | 16 | 490 µs |
| `1` space | 50 | 1.5 ms |
| Gap between frames | 162 | 4.9 ms |

Bits are sent most-significant first. Every frame ends with a stop mark.

## Message layout

A state command is three frames: the main frame twice, then the extended frame.
**Off** is the main frame twice, with no extended frame.

### Main frame (6 bytes)

```
B2  ~B2  F  ~F  T  ~T          (~x = bitwise inverse of x)
```

**Byte F (fan):** `fff11111`, where `fff` is the fan level:

| Fan setting | `fff` |
|---|---|
| Auto | `101` |
| ≤ 20 % | `111` |
| ≤ 40 % | `100` |
| ≤ 60 % | `010` |
| > 60 % | `001` |
| Dry or Auto mode (fan ignored) | `000` |

**Byte T (temperature + mode):** `tttt mm 00`

| Mode | `mm` |
|---|---|
| Cool | `00` |
| Dry | `01` |
| Auto | `10` |
| Heat | `11` |

Fan-only is dry mode (`01`) with temperature code `1110`.

| °C | `tttt` | °C | `tttt` |
|---|---|---|---|
| 17 | `0000` | 24 | `0100` |
| 18 | `0001` | 25 | `1100` |
| 19 | `0011` | 26 | `1101` |
| 20 | `0010` | 27 | `1001` |
| 21 | `0110` | 28 | `1000` |
| 22 | `0111` | 29 | `1010` |
| 23 | `0101` | 30 | `1011` |

**Off** is the fixed frame `B2 4D 7B 84 E0 1F`.

### Extended frame (6 bytes, no inverses)

```
D5  P  00  00  00  C
```

- `P`: fan speed. 1–100 is the exact percentage, `102` (0x66) is auto, `101` (0x65) means the AC controls the fan (dry and auto modes).
- `C`: checksum, the low byte of the sum of the first five bytes.
- The three `00` bytes are probably feature flags (ionizer, sleep, display…). They were zero in every capture.

## Examples

| State | Main frame | Extended frame |
|---|---|---|
| Off | `B2 4D 7B 84 E0 1F` | — |
| Cool 22 °C, auto fan | `B2 4D BF 40 70 8F` | `D5 66 00 00 00 3B` |
| Cool 17 °C, 20 % | `B2 4D FF 00 00 FF` | `D5 14 00 00 00 E9` |
| Heat 21 °C, 60 % | `B2 4D 5F A0 6C 93` | `D5 3C 00 00 00 11` |
| Heat 23 °C, 60 % *(generated, verified on the AC)* | `B2 4D 5F A0 5C A3` | `D5 3C 00 00 00 11` |
| Fan only, 60 % | `B2 4D 5F A0 E4 1B` | `D5 3C 00 00 00 11` |
| Dry 24 °C | `B2 4D 1F E0 44 BB` | `D5 65 00 00 00 3A` |
| Auto 24 °C | `B2 4D 1F E0 48 B7` | `D5 65 00 00 00 3A` |

## Not yet decoded

Swing, turbo, sleep, ionizer, "follow me", LED display and timers. In standard
Coolix most of these are separate one-off commands (for example swing toggle
`B2 6B E0`), but they haven't been captured from this remote.

## The blaster's `key_code` packet

```
26 00  LL LL  <pulse ticks…>
```

`LL LL` is little-endian: the number of pulse bytes plus 4. A tick of 256 or
more is written as `00 HH LL` (big-endian). The whole packet is base64-encoded.
