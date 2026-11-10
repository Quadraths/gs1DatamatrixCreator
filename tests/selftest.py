"""Самопроверка: генерация символов и обратное декодирование через zxing-cpp.

Критерий корректности — не совпадение пикселей с чужой реализацией (zxing может
выбрать C40/Text вместо ASCII), а полный round-trip: сгенерированный символ
обязан декодироваться обратно в ту же GS1-строку с разделителями GS.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import zxingcpp
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gs1dm
from gs1dm.render import write_png

OUT = Path(__file__).parent / "out"

SAMPLES: list[tuple[str, str]] = [
    # (описание, код маркировки)
    (
        "полная структура (обувь), AI 92 = 44 символа",
        "(01)04811644010685(21)25mpid7gn7wzu(91)FFD0(92)dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgA=",
    ),
    (
        "укороченная структура (вода/молоко), AI 93 = 4 символа",
        "(01)04811289005596(21)5PoVL5(93))H7P",
    ),
    (
        "сырой вид строки, разделитель GS как \\x1d",
        "0104604312345673\x1d215PoVL5\x1d93)H7P",
    ),
    (
        "полная структура, длинный AI 92 (88 символов)",
        "(01)04811644010685(21)25mpid7gn7wzu(91)FFD0(92)"
        "dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgA=dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgA=",
    ),
    (
        "кириллица недопустима — ожидается ошибка",
        "(01)04811644010685(21)25ЖИД?",
    ),
    (
        "неверная контрольная цифра GTIN — ожидается ошибка",
        "(01)04811644010686(21)25mpid7gn7wzu(93)H7PX",
    ),
    (
        "нет крипточасти — ожидается ошибка",
        "(01)00000046209849(21)5000000005NgF",
    ),
]

EXPECT_ERROR = {
    "кириллица недопустима — ожидается ошибка",
    "неверная контрольная цифра GTIN — ожидается ошибка",
    "нет крипточасти — ожидается ошибка",
}


def decode_bytes(png: Path) -> str | None:
    results = zxingcpp.read_barcodes(Image.open(png))
    if not results:
        return None
    return results[0].bytes.decode("latin-1")


def expected_element_string(code: gs1dm.MarkingCode) -> str:
    return code.element_string()


def main() -> int:
    failures = 0
    OUT.mkdir(exist_ok=True)

    for index, (title, sample) in enumerate(SAMPLES):
        print("=" * 78)
        print(f"[{index}] {title}")
        print(f"    вход: {sample!r}")
        try:
            bar = gs1dm.create(sample, allow_missing_crypto=False)
        except gs1dm.ValidationError as exc:
            if title in EXPECT_ERROR:
                print(f"    OK, ошибка отловлена: {exc}")
            else:
                print(f"    FAIL: неожиданная ошибка валидации: {exc}")
                failures += 1
            continue

        if title in EXPECT_ERROR:
            print("    FAIL: ожидалась ошибка валидации, но код принят")
            failures += 1
            continue

        print(bar.summary())
        for warning in bar.code.warnings:
            print(f"    ! {warning}")

        png = OUT / f"sample_{index}.png"
        write_png(bar.matrix, png, scale=8, quiet_zone=2)
        actual = decode_bytes(png)
        expected = expected_element_string(bar.code)
        if actual is None:
            print("    FAIL: символ не декодируется")
            failures += 1
        elif actual != expected:
            print(f"    FAIL: декодировано {actual!r}, ожидалось {expected!r}")
            failures += 1
        else:
            print(f"    OK: round-trip совпал, символ {bar.symbol.size_label}")

    # --- массовая проверка на случайных данных ---------------------------
    print("=" * 78)
    print("Случайные коды (round-trip):")
    rng = random.Random(20261109)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    checked = 0
    for _ in range(12):
        gtin13 = "".join(rng.choice("0123456789") for _ in range(13))
        gtin = gtin13 + _check_digit(gtin13)
        serial = "5" + "".join(rng.choice(alphabet) for _ in range(rng.randint(5, 19)))
        if rng.random() < 0.5:
            crypto = "(93)" + "".join(rng.choice(alphabet) for _ in range(4))
        else:
            ai92 = "".join(rng.choice(alphabet + "+/=") for _ in range(rng.choice((44, 88))))
            crypto = "(91)" + "".join(rng.choice(alphabet) for _ in range(4)) + f"(92){ai92}"
        sample = f"(01){gtin}(21){serial}{crypto}"
        bar = gs1dm.create(sample)
        png = OUT / "random.png"
        write_png(bar.matrix, png, scale=4, quiet_zone=2)
        actual = decode_bytes(png)
        if actual != bar.code.element_string():
            print(f"    FAIL: {sample}")
            print(f"        декодировано {actual!r}")
            failures += 1
        else:
            checked += 1
        print(f"    {bar.symbol.size_label:>6}  GTIN {gtin}  serial {len(serial):>2}  ok")

    print("=" * 78)
    print(f"ИТОГО: успешных случайных {checked}/12, ошибок {failures}")
    return 1 if failures else 0


def _check_digit(gtin13: str) -> str:
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(gtin13)))
    return str((10 - total % 10) % 10)


if __name__ == "__main__":
    raise SystemExit(main())
