"""Проверка всех размеров символов ECC 200: RS-блоки, размещение, round-trip."""

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

OUT = Path(__file__).parent / "out" / "sizes"


def decode(path: Path) -> bytes | None:
    results = zxingcpp.read_barcodes(Image.open(path))
    return results[0].bytes if results else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures = 0

    for symbol in SYMBOLS:
        if symbol.rectangular:
            continue
        # Подбираем строку так, чтобы кодовые слова заняли максимально возможную
        # часть ёмкости (но не всю — нужен PAD). Для самых маленьких символов
        # (10x10, 12x12, 14x14) GS1-префикс не помещается, поэтому там
        # используется обычный текст без FNC1.
        gs1 = symbol.data_capacity >= 12
        prefix = "0104811644010685215" if gs1 else ""
        target = symbol.data_capacity - 1
        body = ""
        while len(encode_ascii(prefix + body, gs1=gs1)) < target:
            body += "A"
        raw = encode_ascii(prefix + body, gs1=gs1)
        while len(raw) > symbol.data_capacity - 1 and body:
            body = body[:-1]
            raw = encode_ascii(prefix + body, gs1=gs1)
        while len(raw) > symbol.data_capacity and body:
            body = body[:-1]
            raw = encode_ascii(prefix + body, gs1=gs1)
        if len(raw) > symbol.data_capacity:
            print(f"  {symbol.size_label:<7} пропущен: не удалось подогнать длину")
            continue

        padded = pad_to_capacity(raw, symbol.data_capacity)
        full = ecc200.add_error_correction(padded, symbol)
        matrix = build_matrix(full, symbol)
        png = OUT / f"{symbol.size_label}.png"
        write_png(matrix, png, scale=6, quiet_zone=2)

        actual = decode(png)
        expected_text = (prefix + body).encode("latin-1")
        ok = actual == expected_text
        print(
            f"  {symbol.size_label:<7} данные={symbol.data_capacity:<5} "
            f"блоков={symbol.block_count:<3} round-trip={'OK' if ok else 'FAIL'}"
        )
        if not ok:
            failures += 1
            print(f"      ожидалось {expected_text!r}")
            print(f"      получено  {actual!r}")

    print(
        f"\nРазмеров проверено: {sum(1 for s in SYMBOLS if not s.rectangular)}, ошибок: {failures}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
