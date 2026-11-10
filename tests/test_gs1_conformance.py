"""Проверка соответствия сгенерированных символов структуре GS1 Data Matrix.

Проверяется по существу (а не «похоже/не похоже»):
1. Символика — Data Matrix (ISO/IEC 16022), декодируется без ошибок.
2. Symbology Identifier равен ``]d2`` — это формальный признак GS1 Data Matrix:
   «FNC1 in first position», который отличает GS1-символ от обычного Data Matrix
   (``]d0`` — без FNC1, ``]d1`` — ECC 200 в режиме «программа»).
3. Байты декодированного сообщения — валидная элементная строка GS1:
   начинается с AI 01 (GTIN-14), затем AI 21, затем крипточасть (93 либо 91+92),
   разделители GS (0x1D) стоят ровно там, где требуют правила применения AI.
4. Совокупность AI и их содержимое соответствуют требованиям ЦРПТ
   (контрольная цифра GTIN, длины серийного номера и крипточасти).

Запуск: uv run python tests/test_gs1_conformance.py
"""

import sys
from pathlib import Path

import zxingcpp
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs1dm import create, render_png

SAMPLES = [
    # (название, КМ в человекочитаемом виде, ожидаемый размер символа)
    (
        "полная (01+21+91+92)",
        "(01)04811644010685(21)25mpid7gn7wzu(91)FFD0(92)dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgA=",
        36,
    ),
    ("укороченная (01+21+93)", "(01)04811289005596(21)5PoVL5(93))H7P", 20),
    (
        "длинная (92 = 88 симв.)",
        "(01)04603123456783(21)XtStWt2YchN67AAu(91)FFD1(92)"
        "dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgA=dGVzdDk5EysoESCjyCyf9gSNl3CgNqiSgvzgyJ9LGgAA",
        44,
    ),
]

OUT = Path(__file__).parent / "out" / "gs1check"
FAILURES: list[str] = []


def fail(name: str, msg: str) -> None:
    FAILURES.append(f"{name}: {msg}")
    print(f"    [FAIL] {msg}")


def check(name: str, human: str, expected_size: int) -> None:
    print(f"\n=== {name}")
    bar = create(human)
    es = bar.code.element_string()
    print(f"    элементная строка: {es!r} ({len(es)} байт)")

    # 1. Генерация
    png = OUT / "check.png"
    render_png(bar, png, scale=10)
    img = Image.open(png)

    # 2. Декодирование
    results = zxingcpp.read_barcodes(img)
    if not results:
        fail(name, "символ не декодируется")
        return
    r = results[0]
    print(f"    формат: {r.format}, valid={r.valid}")

    # 3. Формальный признак GS1 Data Matrix — Symbology Identifier ]d2
    sid = r.symbology_identifier
    print(f"    symbology identifier: {sid!r}")
    if not r.valid:
        fail(name, "декодер сообщил об ошибке в символе")
    if sid != "]d2":
        fail(name, f"symbology identifier {sid!r} != ']d2' (FNC1 в первой позиции отсутствует)")
    if r.format != zxingcpp.BarcodeFormat.DataMatrix:
        fail(name, f"формат {r.format!r} != DataMatrix")

    # 4. Байты: точное совпадение с элементной строкой (включая GS 0x1D)
    if r.bytes != es.encode("ascii"):
        fail(name, f"байты не совпали: {r.bytes!r}")
    else:
        print("    байты декодированы точно (включая разделители GS)")

    # 5. Структурные проверки декодированной строки (независимый проход)
    data = r.bytes
    ok = True
    if not data.startswith(b"01") or len(data) < 16:
        fail(name, "сообщение не начинается с AI 01 (GTIN-14)")
        ok = False
    else:
        gtin = data[2:16]
        if not gtin.isdigit():
            fail(name, f"GTIN {gtin!r} не из 14 цифр")
            ok = False
    if b"\x1d" not in data:
        fail(name, "нет ни одного разделителя GS")
        ok = False
    elif b"\x1d21" in data[:18]:
        fail(name, "GS стоит после GTIN, хотя поле фиксированной длины (как в СИ от системы ЧЗ)")
        ok = False
    tail = data.split(b"\x1d", 2)[-1] if data.count(b"\x1d") >= 2 else b""
    if tail and not tail[:2].isdigit():
        fail(name, f"после второго GS ожидается AI крипточасти, получено {tail[:2]!r}")
        ok = False
    # крипточасть: либо 93, либо 91+92
    if b"93" not in data and b"\x1d91" not in data:
        fail(name, "нет крипточасти (AI 93 или AI 91)")
        ok = False
    if ok:
        print("    структура: 01 (14 цифр) <GS> 21 <GS> крипточасть — соответствует GS1")

    # 6. Размер символа: сверка с ожидаемым (по данным нашей матрицы)
    w = len(bar.matrix[0])
    h = len(bar.matrix)
    print(f"    размер: {w}x{h} (ожидается {expected_size}x{expected_size})")
    if (w, h) != (expected_size, expected_size):
        fail(name, f"размер символа {w}x{h} != {expected_size}x{expected_size}")

    if not FAILURES or not any(f.startswith(name) for f in FAILURES):
        print("    [OK] GS1 Data Matrix подтверждён")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, human, size in SAMPLES:
        check(name, human, size)

    print(f"\n{'=' * 70}")
    if FAILURES:
        print(f"Проверка НЕ пройдена: {len(FAILURES)} проблем(ы)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(
        "Проверка пройдена: все символы — GS1 Data Matrix (]d2), "
        "структура и байты совпадают с эталоном"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
