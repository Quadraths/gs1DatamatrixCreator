"""Извлечение сырых кодовых слов из PNG-эталона «Честный знак».

Снимаем с изображения битовую матрицу символа 36x36 (по углам zxing),
обратным ходом placement Annex M.1 восстанавливаем кодовые слова
(данные + ECC), проверяем ECC и разбираем структуру high-level режимов.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import zxingcpp
from PIL import Image

from gs1dm import ecc200, placement, symbols

IMG = Path(__file__).resolve().parents[1] / "out" / "user_dm.png"


def strip_placement_borders(grid, symbol):
    """Из полной матрицы символа вырезает placement-биты областей данных.

    Маппинг зеркалит build_matrix: каждая область данных окружена своими
    кромками, поэтому между соседними областями ДВЕ колонки/строки шаблона.
    """
    dw, dh = symbol.data_width, symbol.data_height
    mw, mh = symbol.matrix_width, symbol.matrix_height

    def col_of(x: int) -> int:
        # столбец матрицы, в котором лежит бит данных x (см. build_matrix)
        matrix_x = 0
        for xx in range(x):
            if xx % mw == 0:
                matrix_x += 1
            matrix_x += 1
            if xx % mw == mw - 1:
                matrix_x += 1
        if x % mw == 0:
            matrix_x += 1
        return matrix_x

    def row_of(y: int) -> int:
        matrix_y = 0
        for yy in range(y):
            if yy % mh == 0:
                matrix_y += 1
            matrix_y += 1
            if yy % mh == mh - 1:
                matrix_y += 1
        if y % mh == 0:
            matrix_y += 1
        return matrix_y

    pbits = [[False] * dw for _ in range(dh)]
    for y in range(dh):
        gy = row_of(y)
        for x in range(dw):
            pbits[y][x] = grid[gy][col_of(x)]
    return pbits


def placement_bits_to_codewords(pbits, symbol) -> bytes:
    """Собирает кодовые слова из placement-битов, используя порядок place()."""
    dw, dh = symbol.data_width, symbol.data_height
    assignments: list[tuple[int, int, int, int]] = []  # (row, col, bit, cw_index)

    class Recorder(placement.Placement):
        def _module(self, row, col, pos, bit):
            if row < 0:
                row += self.numrows
                col += 4 - ((self.numrows + 4) % 8)
            if col < 0:
                col += self.numcols
                row += 4 - ((self.numcols + 4) % 8)
            assignments.append((row, col, bit, pos))

        def _set_bit(self, col, row, value):
            pass

    rec = Recorder(b"\0" * symbol.total_codewords, dw, dh)
    rec.place()

    codewords = bytearray(symbol.total_codewords)
    for row, col, bit, cw_index in assignments:
        if pbits[row][col]:
            codewords[cw_index] |= 1 << (8 - bit)
    return bytes(codewords)


def main() -> None:
    img = Image.open(IMG).convert("L")
    px = img.load()
    results = zxingcpp.read_barcodes(img)
    if not results:
        print("zxing не смог декодировать", IMG)
        return
    r = results[0]
    decoded = r.bytes
    print("symbology:", r.symbology_identifier, "len(decoded) =", len(decoded))
    print("decoded:", decoded.decode("latin-1").replace("\x1d", "<GS>"))

    sym = next(s for s in symbols.SYMBOLS if s.size_label == "36x36")
    print(f"symbol {sym.size_label}: data={sym.data_capacity} ecc={sym.error_codewords}")

    # Углы от zxing: top-left / top-right; шаг модуля = (BR-TL)/36 по X.
    x0 = r.position.top_left.x
    y0 = r.position.top_left.y
    mw = (r.position.bottom_right.x - x0) / sym.symbol_width
    mh = mw  # квадратный символ; низ: y0 + 36*mw выходит за последнюю строку,
    # но step по строкам проверим кромками.

    def cell(mx: int, my: int) -> bool:
        cx = x0 + (mx + 0.5) * mw
        cy = y0 + (my + 0.5) * mh
        return px[round(cx), round(cy)] < 128

    # Проверка кромок
    top = "".join("1" if cell(i, 0) else "0" for i in range(36))
    left = "".join("1" if cell(0, i) else "0" for i in range(36))
    bottom = "".join("1" if cell(i, 35) else "0" for i in range(36))
    right = "".join("1" if cell(35, i) else "0" for i in range(36))
    print("top:   ", top)
    print("left:  ", left)
    print("bottom:", bottom)
    print("right: ", right)

    grid = [[cell(mx, my) for mx in range(sym.symbol_width)] for my in range(sym.symbol_height)]
    pbits = strip_placement_borders(grid, sym)
    raw = placement_bits_to_codewords(pbits, sym)

    data = raw[: sym.data_capacity]
    ecc = raw[sym.data_capacity :]
    print("data:", " ".join(f"{b:3d}" for b in data))
    print("ecc: ", " ".join(f"{b:3d}" for b in ecc))

    try:
        rebuilt = ecc200.add_error_correction(data, sym)
        print("ECC-проверка:", "OK" if bytes(rebuilt) == raw else "FAIL")
    except Exception as exc:
        print("ECC-проверка не удалась:", exc)

    print("\n--- high-level разбор ---")
    interpret(data)


def interpret(data: bytes) -> None:
    i = 0
    n = len(data)
    while i < n:
        cw = data[i]
        if cw == 230:
            print(f"[{i:3d}] LATCH_C40(230)")
            i += 1
            while i + 1 < n:
                pair = (data[i], data[i + 1])
                if pair[0] == 254:
                    print(f"[{i:3d}] UNLATCH(254)")
                    i += 1
                    break
                v = pair[0] * 256 + pair[1] - 1
                vals = [v // 1600 % 40, v // 40 % 40, v % 40]
                print(
                    f"[{i:3d}] C40({pair[0]:3d},{pair[1]:3d}) -> {vals} "
                    f"{''.join(_c40_to_char(vals))!r}"
                )
                i += 2
            continue
        if 130 <= cw <= 229:
            print(f"[{i:3d}] digits {cw - 130:02d}")
        elif cw == 232:
            print(f"[{i:3d}] FNC1(232)")
        elif cw == 235:
            print(f"[{i:3d}] UPPER_SHIFT -> {data[i + 1] - 1}")
            i += 1
        else:
            ch = chr(cw - 1) if 1 <= cw <= 127 else f"<{cw}>"
            print(f"[{i:3d}] ASCII {ch!r}")
        i += 1


def _c40_to_char(vals: list[int]) -> str:
    out = []
    for v in vals:
        if v == 0:
            out.append("<S1>")
        elif v == 1:
            out.append("<S2>")
        elif v == 2:
            out.append("<S3>")
        elif v == 3:
            out.append(" ")
        elif 4 <= v <= 13:
            out.append(chr(48 + v - 4))
        elif 14 <= v <= 39:
            out.append(chr(65 + v - 14))
        else:
            out.append(f"<{v}>")
    return "".join(out)


if __name__ == "__main__":
    main()
