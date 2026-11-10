"""Проверка прямоугольных символов ECC 200 (8x18, 8x32, 12x26, 12x36, 16x36, 16x48)."""

from __future__ import annotations

import sys
from pathlib import Path

import zxingcpp
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gs1dm import ecc200, encode_ascii, pad_to_capacity
from gs1dm.placement import build_matrix
from gs1dm.render import write_png
from gs1dm.symbols import SYMBOLS

OUT = Path(__file__).parent / "out" / "rect"


def decode(path: Path) -> bytes | None:
    results = zxingcpp.read_barcodes(Image.open(path))
    return results[0].bytes if results else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures = 0

    for symbol in SYMBOLS:
        if not symbol.rectangular:
            continue
        target = symbol.data_capacity - 1
        body = ""
        while len(encode_ascii(body, gs1=False)) < target:
            body += "A"
        raw = encode_ascii(body, gs1=False)
        while len(raw) > symbol.data_capacity and body:
            body = body[:-1]
            raw = encode_ascii(body, gs1=False)

        padded = pad_to_capacity(raw, symbol.data_capacity)
        full = ecc200.add_error_correction(padded, symbol)
        matrix = build_matrix(full, symbol)
        png = OUT / f"{symbol.symbol_width}x{symbol.symbol_height}.png"
        write_png(matrix, png, scale=8, quiet_zone=2)

        actual = decode(png)
        expected = body.encode("latin-1")
        ok = actual == expected
        print(
            f"  {symbol.size_label:<7} данные={symbol.data_capacity:<3} "
            f"областей={symbol.data_regions} round-trip={'OK' if ok else 'FAIL'}"
            f" ({len(matrix[0])}x{len(matrix)} модулей)"
        )
        if not ok:
            failures += 1
            print(f"      ожидалось {expected!r}\n      получено  {actual!r}")

    print(f"\nОшибок: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
