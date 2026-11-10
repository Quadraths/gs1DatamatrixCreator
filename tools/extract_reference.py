"""Точное извлечение кодовых слов из эталона ЧЗ: перспективное выравнивание + исправленный маппинг."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import zxingcpp
from inspect_reference import placement_bits_to_codewords, strip_placement_borders
from PIL import Image

from gs1dm import ecc200, symbols

IMG = Path(__file__).resolve().parents[1] / "out" / "user_dm.png"

ref = Image.open(IMG).convert("L")
res = zxingcpp.read_barcodes(ref)[0]
p = res.position
# PIL QUAD order: UL, LL, LR, UR
pts = (p.top_left.x, p.top_left.y, p.bottom_left.x, p.bottom_left.y,
       p.bottom_right.x, p.bottom_right.y, p.top_right.x, p.top_right.y)
S = 16
warped = ref.transform((36 * S, 36 * S), Image.QUAD, pts)
px = warped.load()


def cell(mx: int, my: int) -> bool:
    vals = [px[mx * S + dx, my * S + dy]
            for dx in (S // 3, S // 2, 2 * S // 3) for dy in (S // 3, S // 2, 2 * S // 3)]
    dark = sum(1 for v in vals if v < 128)
    return dark * 2 >= len(vals)


grid = [[cell(mx, my) for mx in range(36)] for my in range(36)]
sym = next(s for s in symbols.SYMBOLS if s.size_label == "36x36")
pbits = strip_placement_borders(grid, sym)
raw = placement_bits_to_codewords(pbits, sym)
data, ecc = raw[:86], raw[86:]
expected = ecc200.add_error_correction(bytes(data), sym)
match = list(expected) == list(raw)
print("ECC match:", match)
print("data cw:", " ".join(str(b) for b in data))
if not match:
    # показать, какие биты расходятся
    diff_bits = sum(bin(a ^ b).count("1") for a, b in zip(expected, raw, strict=True))
    print("total diff bits:", diff_bits)
