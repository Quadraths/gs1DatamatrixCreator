"""Сверка с эталонным СИ «Честный знак» (out/user_dm.png, 36x36).

Кодовые слова эталона извлечены побитово (перспективное выравнивание по углам
zxing + обратный placement) и подтверждены ECC-проверкой: Reed-Solomon
эталонных 128 кодовых слов сошёлся. Вывод: «Честный знак» использует чистое
ASCII-кодирование; ведущий FNC1 присутствует, а разделители GS кодируются
как обычный ASCII-символ (0x1D + 1 = 30), НЕ как FNC1 (232).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from gs1dm import create

SAMPLE = "(01)04640711961304(21)5;I)DmC:IDt*L(91)EE12(92)4a8GsyItTVweCsj65+Wk5AxvQD6NnNAcmMIKSsLGAek="

#: 86 кодовых слов данных, извлечённых из эталона ЧЗ (ECC-проверка пройдена).
REFERENCE_DATA_CODEWORDS = [
    232, 131, 134, 194, 137, 141, 226, 143, 134, 151, 54, 60, 74, 42, 69, 110,
    68, 59, 74, 69, 117, 43, 77, 30, 221, 70, 70, 142, 30, 222, 53, 98, 57, 72,
    116, 122, 74, 117, 85, 87, 120, 102, 68, 116, 107, 195, 44, 88, 108, 54,
    66, 121, 119, 82, 69, 55, 79, 111, 79, 66, 100, 110, 78, 74, 76, 84, 116,
    77, 72, 66, 102, 108, 62, 129, 173, 68, 218, 113, 9, 159, 54, 204, 99,
    249, 145, 40,
]

REFERENCE_IMAGE = Path(__file__).resolve().parents[1] / "out" / "user_dm.png"


def test_codewords_match_reference() -> None:
    bar = create(SAMPLE)
    assert bar.symbol.size_label == "36x36"
    ours = list(bar.data.codewords)
    assert ours == REFERENCE_DATA_CODEWORDS, (
        "Кодовые слова не совпадают с эталоном ЧЗ; первые отличия: "
        + str(
            [
                (i, a, b)
                for i, (a, b) in enumerate(
                    zip(ours, REFERENCE_DATA_CODEWORDS, strict=False)
                )
                if a != b
            ][:8]
        )
    )


def _reference_grid() -> list[list[bool]]:
    """Сетка 36x36 из фото эталона: выравнивание по углам zxing (PIL QUAD)."""
    import zxingcpp
    from inspect_reference import placement_bits_to_codewords, strip_placement_borders
    from PIL import Image

    img = Image.open(REFERENCE_IMAGE).convert("L")
    res = zxingcpp.read_barcodes(img)[0]
    p = res.position
    pts = (p.top_left.x, p.top_left.y, p.bottom_left.x, p.bottom_left.y,
           p.bottom_right.x, p.bottom_right.y, p.top_right.x, p.top_right.y)
    s = 16
    warped = img.transform((36 * s, 36 * s), Image.QUAD, pts)
    px = warped.load()

    def cell(mx: int, my: int) -> bool:
        vals = [px[mx * s + dx, my * s + dy]
                for dx in (s // 3, s // 2, 2 * s // 3) for dy in (s // 3, s // 2, 2 * s // 3)]
        dark = sum(1 for v in vals if v < 128)
        return dark * 2 >= len(vals)

    from gs1dm import symbols

    sym = next(x for x in symbols.SYMBOLS if x.size_label == "36x36")
    grid = [[cell(mx, my) for mx in range(36)] for my in range(36)]
    pbits = strip_placement_borders(grid, sym)
    raw = placement_bits_to_codewords(pbits, sym)
    from gs1dm import ecc200

    assert list(ecc200.add_error_correction(bytes(raw[:86]), sym)) == list(raw), \
        "ECC-проверка эталонного фото не сошлась"
    return grid


def test_pixels_match_reference_image() -> None:
    if not REFERENCE_IMAGE.exists():
        print("эталонный PNG отсутствует, пиксельная сверка пропущена")
        return
    bar = create(SAMPLE)
    grid = _reference_grid()
    diff = sum(1 for y in range(36) for x in range(36) if bar.matrix[y][x] != grid[y][x])
    assert diff == 0, f"пиксельная разница с эталоном ЧЗ: {diff}/1296"


if __name__ == "__main__":
    test_codewords_match_reference()
    test_pixels_match_reference_image()
    print("OK: кодовые слова и пиксели совпадают с эталоном «Честный знак»")
