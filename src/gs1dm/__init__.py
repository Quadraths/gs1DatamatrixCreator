"""Пакет создания GS1 Data Matrix (ECC 200) по коду маркировки «Честный знак»."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import ecc200
from .encoder import EncodedData, encode_ascii, pad_to_capacity
from .gs1 import GS, MarkingCode, ValidationError, parse_marking_code
from .placement import build_matrix
from .symbols import SymbolInfo, lookup

__all__ = [
    "GS",
    "Barcode",
    "EncodedData",
    "MarkingCode",
    "SymbolInfo",
    "ValidationError",
    "build_codewords",
    "build_matrix",
    "create",
    "parse_marking_code",
    "render_png",
    "render_svg",
]


@dataclass
class Barcode:
    """Готовый символ: разобранный КМ, кодовые слова и матрица."""

    code: MarkingCode
    symbol: SymbolInfo
    data: EncodedData
    matrix: list[list[bool]]

    @property
    def element_string(self) -> str:
        return self.code.element_string()

    def summary(self) -> str:
        return "\n".join(
            [
                self.code.describe(),
                f"Элементная строка:    {self.element_string.replace(GS, '<GS>')}",
                f"Символ ECC 200:       {self.symbol.size_label} "
                f"(данные {self.symbol.data_capacity} + коррекция {self.symbol.error_codewords} кодовых слов)",
                f"Занято кодовых слов:  {len(self.data.codewords)} из {self.symbol.data_capacity}",
            ]
        )


def build_codewords(code: MarkingCode) -> EncodedData:
    """Кодирует элементную строку КМ в кодовые слова данных."""
    raw = encode_ascii(code.element_string(), gs1=True)
    return EncodedData(codewords=bytes(raw), capacity=len(raw), gs1=True)


def create(text: str, *, allow_missing_crypto: bool = False, square_only: bool = True) -> Barcode:
    """Строит символ Data Matrix по строке кода маркировки.

    Raises:
        ValidationError: структура КМ неверна (строгий режим).
    """
    code = parse_marking_code(text, allow_missing_crypto=allow_missing_crypto)
    raw = encode_ascii(code.element_string(), gs1=True)
    symbol = lookup(len(raw), square_only=square_only)
    padded = pad_to_capacity(raw, symbol.data_capacity)
    full = ecc200.add_error_correction(padded, symbol)
    matrix = build_matrix(full, symbol)
    data = EncodedData(codewords=padded, capacity=symbol.data_capacity, gs1=True)
    return Barcode(code=code, symbol=symbol, data=data, matrix=matrix)


def render_png(bar: Barcode, path: str | Path, **kwargs) -> tuple[int, int]:
    from .render import write_png

    return write_png(bar.matrix, path, **kwargs)


def render_svg(bar: Barcode, path: str | Path, **kwargs) -> tuple[float, float]:
    from .render import write_svg

    return write_svg(bar.matrix, path, title=f"GS1 DataMatrix {bar.code.gtin}", **kwargs)
