"""
Builds tests/fixtures/bars.json: deterministic synthetic daily bars for a few
symbols, shared by the Python tests and the JavaScript parity check.

    python tests/make_fixture.py

Symbols:
  QQQ, SMH      benchmarks, 140 sessions each
  ACME          semi-like stock (bench SMH), MISSING one session in the middle
  UPUP          steady riser, no down days in the last 30 sessions (RSI edge)
  FLAT          identical OHLC for the last 25 sessions (zero-range edge)
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path


def sessions(n: int, start: date = date(2026, 4, 1)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def walk(seed: int, n: int, drift: float, vol: float, start_px: float) -> list[dict]:
    rng = random.Random(seed)
    bars, c = [], start_px
    for d in sessions(n):
        o = c * (1 + rng.gauss(0, vol * 0.3))
        c = max(1.0, c * (1 + rng.gauss(drift, vol)))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.4)))
        l = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.4)))
        v = int(rng.uniform(2e6, 4e7))
        bars.append({"d": d, "o": round(o, 4), "h": round(h, 4), "l": round(l, 4), "c": round(c, 4), "v": v})
    return bars


def main() -> None:
    fx = {
        "QQQ": walk(1, 140, 0.0015, 0.010, 500),
        "SMH": walk(2, 140, 0.0010, 0.016, 280),
        "ACME": walk(3, 140, 0.0030, 0.022, 120),
        "UPUP": walk(4, 140, 0.0020, 0.012, 50),
        "FLAT": walk(5, 140, 0.0000, 0.015, 80),
    }
    # ACME skips one session (index 100) so positional and date-aligned maths differ
    fx["ACME"] = fx["ACME"][:100] + fx["ACME"][101:]
    # UPUP: last 30 closes strictly rising, no down day
    px = fx["UPUP"][-31]["c"]
    for b in fx["UPUP"][-30:]:
        px *= 1.004
        b["o"], b["c"] = round(px * 0.998, 4), round(px, 4)
        b["h"], b["l"] = round(px * 1.003, 4), round(px * 0.995, 4)
    # FLAT: last 25 bars identical and flat (ATR -> 0, zero range)
    last = fx["FLAT"][-26]["c"]
    for b in fx["FLAT"][-25:]:
        b["o"] = b["h"] = b["l"] = b["c"] = round(last, 4)

    out = Path(__file__).parent / "fixtures" / "bars.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(fx, indent=0))
    print("wrote", out, {k: len(v) for k, v in fx.items()})


if __name__ == "__main__":
    main()
