"""Таблица символов Data Matrix ECC 200 (ISO/IEC 16022, Annex A / таблица 7).

Данные соответствуют таблице символов ECC 200: число кодовых слов данных,
число кодовых слов коррекции, размеры области данных, количество областей
и параметры чередования блоков Рида — Соломона.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolInfo:
    """Описание одного размера символа ECC 200."""

    rectangular: bool
    data_capacity: int
    error_codewords: int
    matrix_width: int
    matrix_height: int
    data_regions: int
    # Параметры блоков RS. Если rs_block_data <= 0, используется size144-специфика.
    rs_block_data: int
    rs_block_error: int

    # --- геометрия -----------------------------------------------------
    @property
    def horizontal_regions(self) -> int:
        return {1: 1, 2: 2, 4: 2, 16: 4, 36: 6}[self.data_regions]

    @property
    def vertical_regions(self) -> int:
        return {1: 1, 2: 1, 4: 2, 16: 4, 36: 6}[self.data_regions]

    @property
    def data_width(self) -> int:
        return self.horizontal_regions * self.matrix_width

    @property
    def data_height(self) -> int:
        return self.vertical_regions * self.matrix_height

    @property
    def symbol_width(self) -> int:
        return self.data_width + self.horizontal_regions * 2

    @property
    def symbol_height(self) -> int:
        return self.data_height + self.vertical_regions * 2

    @property
    def size_label(self) -> str:
        return f"{self.symbol_width}x{self.symbol_height}"

    # --- блоки Рида — Соломона -----------------------------------------
    @property
    def block_count(self) -> int:
        if self.data_capacity == 1558:  # единственный спецслучай (144x144)
            return 10
        return self.data_capacity // self.rs_block_data

    def data_length_for_block(self, index: int) -> int:
        """index — номер блока, начиная с 1."""
        if self.data_capacity == 1558:
            return 156 if index <= 8 else 155
        return self.rs_block_data

    def error_length_for_block(self, index: int) -> int:
        return self.rs_block_error if self.data_capacity != 1558 else 62

    @property
    def total_codewords(self) -> int:
        return self.data_capacity + self.error_codewords


# (rect, data, ecc, mw, mh, regions, rs_data, rs_err)
_TABLE: tuple[tuple[bool, int, int, int, int, int, int, int], ...] = (
    (False, 3, 5, 8, 8, 1, 3, 5),
    (False, 5, 7, 10, 10, 1, 5, 7),
    (True, 5, 7, 16, 6, 1, 5, 7),
    (False, 8, 10, 12, 12, 1, 8, 10),
    (True, 10, 11, 14, 6, 2, 10, 11),
    (False, 12, 12, 14, 14, 1, 12, 12),
    (True, 16, 14, 24, 10, 1, 16, 14),
    (False, 18, 14, 16, 16, 1, 18, 14),
    (False, 22, 18, 18, 18, 1, 22, 18),
    (True, 22, 18, 16, 10, 2, 22, 18),
    (False, 30, 20, 20, 20, 1, 30, 20),
    (True, 32, 24, 16, 14, 2, 32, 24),
    (False, 36, 24, 22, 22, 1, 36, 24),
    (False, 44, 28, 24, 24, 1, 44, 28),
    (True, 49, 28, 22, 14, 2, 49, 28),
    (False, 62, 36, 14, 14, 4, 62, 36),
    (False, 86, 42, 16, 16, 4, 86, 42),
    (False, 114, 48, 18, 18, 4, 114, 48),
    (False, 144, 56, 20, 20, 4, 144, 56),
    (False, 174, 68, 22, 22, 4, 174, 68),
    (False, 204, 84, 24, 24, 4, 102, 42),
    (False, 280, 112, 14, 14, 16, 140, 56),
    (False, 368, 144, 16, 16, 16, 92, 36),
    (False, 456, 192, 18, 18, 16, 114, 48),
    (False, 576, 224, 20, 20, 16, 144, 56),
    (False, 696, 272, 22, 22, 16, 174, 68),
    (False, 816, 336, 24, 24, 16, 136, 56),
    (False, 1050, 408, 18, 18, 36, 175, 68),
    (False, 1304, 496, 20, 20, 36, 163, 62),
    (False, 1558, 620, 22, 22, 36, -1, 62),
)

SYMBOLS: tuple[SymbolInfo, ...] = tuple(
    SymbolInfo(rect, data, ecc, mw, mh, regions, rs_data, rs_err)
    for rect, data, ecc, mw, mh, regions, rs_data, rs_err in _TABLE
)


def lookup(data_codewords: int, square_only: bool = True) -> SymbolInfo:
    """Наименьший символ, вмещающий указанное количество кодовых слов данных."""
    for symbol in SYMBOLS:
        if square_only and symbol.rectangular:
            continue
        if data_codewords <= symbol.data_capacity:
            return symbol
    raise ValueError(
        f"Данные слишком велики для Data Matrix ECC 200: {data_codewords} кодовых слов"
    )


def max_capacity(square_only: bool = True) -> int:
    return max(s.data_capacity for s in SYMBOLS if not (square_only and s.rectangular))
