"""Размещение битов в матрице символа (ISO/IEC 16022, Annex M.1)."""

from __future__ import annotations

from .symbols import SymbolInfo


class Placement:
    """Программа размещения кодовых слов по схеме «utah» и угловым шаблонам."""

    def __init__(self, codewords: bytes, numcols: int, numrows: int) -> None:
        self.codewords = codewords
        self.numcols = numcols
        self.numrows = numrows
        self.bits: list[int] = [-1] * (numcols * numrows)

    # --- доступ к битам -------------------------------------------------
    def get_bit(self, col: int, row: int) -> bool:
        return self.bits[row * self.numcols + col] == 1

    def _set_bit(self, col: int, row: int, value: bool) -> None:
        self.bits[row * self.numcols + col] = 1 if value else 0

    def _no_bit(self, col: int, row: int) -> bool:
        return self.bits[row * self.numcols + col] < 0

    # --- основной алгоритм ----------------------------------------------
    def place(self) -> None:
        pos = 0
        row = 4
        col = 0
        numrows, numcols = self.numrows, self.numcols

        while True:
            if row == numrows and col == 0:
                self._corner1(pos)
                pos += 1
            if row == numrows - 2 and col == 0 and numcols % 4 != 0:
                self._corner2(pos)
                pos += 1
            if row == numrows - 2 and col == 0 and numcols % 8 == 4:
                self._corner3(pos)
                pos += 1
            if row == numrows + 4 and col == 2 and numcols % 8 == 0:
                self._corner4(pos)
                pos += 1

            while True:
                if row < numrows and col >= 0 and self._no_bit(col, row):
                    self._utah(row, col, pos)
                    pos += 1
                row -= 2
                col += 2
                if not (row >= 0 and col < numcols):
                    break
            row += 1
            col += 3

            while True:
                if row >= 0 and col < numcols and self._no_bit(col, row):
                    self._utah(row, col, pos)
                    pos += 1
                row += 2
                col -= 2
                if not (row < numrows and col >= 0):
                    break
            row += 3
            col += 1

            if not (row < numrows or col < numcols):
                break

        if self._no_bit(numcols - 1, numrows - 1):
            self._set_bit(numcols - 1, numrows - 1, True)
            self._set_bit(numcols - 2, numrows - 2, True)

    # --- вспомогательные методы -----------------------------------------
    def _module(self, row: int, col: int, pos: int, bit: int) -> None:
        if row < 0:
            row += self.numrows
            col += 4 - ((self.numrows + 4) % 8)
        if col < 0:
            col += self.numcols
            row += 4 - ((self.numcols + 4) % 8)
        value = self.codewords[pos] & (1 << (8 - bit))
        self._set_bit(col, row, value != 0)

    def _utah(self, row: int, col: int, pos: int) -> None:
        self._module(row - 2, col - 2, pos, 1)
        self._module(row - 2, col - 1, pos, 2)
        self._module(row - 1, col - 2, pos, 3)
        self._module(row - 1, col - 1, pos, 4)
        self._module(row - 1, col, pos, 5)
        self._module(row, col - 2, pos, 6)
        self._module(row, col - 1, pos, 7)
        self._module(row, col, pos, 8)

    def _corner1(self, pos: int) -> None:
        self._module(self.numrows - 1, 0, pos, 1)
        self._module(self.numrows - 1, 1, pos, 2)
        self._module(self.numrows - 1, 2, pos, 3)
        self._module(0, self.numcols - 2, pos, 4)
        self._module(0, self.numcols - 1, pos, 5)
        self._module(1, self.numcols - 1, pos, 6)
        self._module(2, self.numcols - 1, pos, 7)
        self._module(3, self.numcols - 1, pos, 8)

    def _corner2(self, pos: int) -> None:
        self._module(self.numrows - 3, 0, pos, 1)
        self._module(self.numrows - 2, 0, pos, 2)
        self._module(self.numrows - 1, 0, pos, 3)
        self._module(0, self.numcols - 4, pos, 4)
        self._module(0, self.numcols - 3, pos, 5)
        self._module(0, self.numcols - 2, pos, 6)
        self._module(0, self.numcols - 1, pos, 7)
        self._module(1, self.numcols - 1, pos, 8)

    def _corner3(self, pos: int) -> None:
        self._module(self.numrows - 3, 0, pos, 1)
        self._module(self.numrows - 2, 0, pos, 2)
        self._module(self.numrows - 1, 0, pos, 3)
        self._module(0, self.numcols - 2, pos, 4)
        self._module(0, self.numcols - 1, pos, 5)
        self._module(1, self.numcols - 1, pos, 6)
        self._module(2, self.numcols - 1, pos, 7)
        self._module(3, self.numcols - 1, pos, 8)

    def _corner4(self, pos: int) -> None:
        self._module(self.numrows - 1, 0, pos, 1)
        self._module(self.numrows - 1, self.numcols - 1, pos, 2)
        self._module(0, self.numcols - 3, pos, 3)
        self._module(0, self.numcols - 2, pos, 4)
        self._module(0, self.numcols - 1, pos, 5)
        self._module(1, self.numcols - 3, pos, 6)
        self._module(1, self.numcols - 2, pos, 7)
        self._module(1, self.numcols - 1, pos, 8)


def build_matrix(codewords: bytes, symbol: SymbolInfo) -> list[list[bool]]:
    """Собирает полную матрицу символа с шаблонами поиска (без полей)."""
    placement = Placement(codewords, symbol.data_width, symbol.data_height)
    placement.place()

    matrix = [[False] * symbol.symbol_width for _ in range(symbol.symbol_height)]
    matrix_y = 0

    for y in range(symbol.data_height):
        if y % symbol.matrix_height == 0:
            for x in range(symbol.symbol_width):
                matrix[matrix_y][x] = x % 2 == 0
            matrix_y += 1

        matrix_x = 0
        for x in range(symbol.data_width):
            if x % symbol.matrix_width == 0:
                matrix[matrix_y][matrix_x] = True
                matrix_x += 1
            matrix[matrix_y][matrix_x] = placement.get_bit(x, y)
            matrix_x += 1
            if x % symbol.matrix_width == symbol.matrix_width - 1:
                matrix[matrix_y][matrix_x] = y % 2 == 0
                matrix_x += 1
        matrix_y += 1

        if y % symbol.matrix_height == symbol.matrix_height - 1:
            for x in range(symbol.symbol_width):
                matrix[matrix_y][x] = True
            matrix_y += 1

    return matrix
