"""Check the Coolix encoder against real IR captures.

Each entry in docs/captured_codes.yaml was learned from the physical remote.
This script regenerates every one with the encoder and compares the decoded
frames bit for bit. Run it after changing the encoder, or add your own
captures (name: "base64 key_code") to check a different remote.

    python3 tools/verify_captures.py [path/to/captured_codes.yaml]
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bosch_coolix import decode_frames, encode  # noqa: E402

# Capture name -> encoder arguments (mode, temperature, fan).
EXPECTED = {
    "off": ("off",),
    "cool_22_auto": ("cool", 22, "auto"),
    "cool_17_fan20": ("cool", 17, 20),
    "heat_21_fan60": ("heat", 21, 60),
    "heat_21_fan100": ("heat", 21, 100),
    "heat_21_fan40": ("heat", 21, 40),
    "fan_only_fan60": ("fan_only", None, 60),
    "dry_24": ("dry", 24),
    "auto_24": ("auto", 24),
}


def main() -> int:
    default = Path(__file__).resolve().parent.parent / "docs" / "captured_codes.yaml"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    captures = dict(re.findall(r'^(\w+):\s*"([^"]+)"', path.read_text(), re.M))

    failures = 0
    for name, code in captures.items():
        learned = decode_frames(code)
        if name not in EXPECTED:
            print(f"?  {name:16} {learned}  (no expected state listed)")
            continue
        generated = decode_frames(encode(*EXPECTED[name]))
        if learned == generated:
            print(f"OK {name:16} {' | '.join(learned)}")
        else:
            failures += 1
            print(f"XX {name:16}\n   learned   {learned}\n   generated {generated}")
    print(f"\n{len(captures) - failures}/{len(captures)} captures reproduced")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
