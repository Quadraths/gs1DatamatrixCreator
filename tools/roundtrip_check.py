"""Проверка: placement -> extraction round-trip на известном полном кадре."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from inspect_reference import placement_bits_to_codewords, strip_placement_borders

from gs1dm import ecc200, placement, symbols

sym = next(s for s in symbols.SYMBOLS if s.size_label == "36x36")
data = bytes(range(86))
full = ecc200.add_error_correction(data, sym)

matrix = placement.build_matrix(full, sym)
pbits = strip_placement_borders(matrix, sym)
raw = placement_bits_to_codewords(pbits, sym)
print("full round-trip match:", raw == full)
if raw != full:
    diffs = [(i, a, b) for i, (a, b) in enumerate(zip(raw, full, strict=True)) if a != b]
    print("mismatch count:", len(diffs), "first:", diffs[:5])

# тот же round-trip через зеркальную сборку: Placement сам по себе
pl = placement.Placement(full, sym.data_width, sym.data_height)
pl.place()
pbits2 = [[pl.get_bit(x, y) for x in range(sym.data_width)] for y in range(sym.data_height)]
raw2 = placement_bits_to_codewords(pbits2, sym)
print("pbits round-trip match:", raw2 == full)
