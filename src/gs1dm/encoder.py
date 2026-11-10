"""Кодирование данных в кодовые слова Data Matrix ECC 200.

Реализовано ASCII-кодирование (ISO/IEC 16022, Annex P, таблица 2): оно всегда
допустимо, поддерживает FNC1 и уплотнение цифровых пар, чего достаточно для
кодов маркировки (GS1-строка из латиницы, цифр и нескольких спецсимволов).
"""

from __future__ import annotations

from dataclasses import dataclass

PAD = 129
LATCH_TO_C40 = 230
LATCH_TO_BASE256 = 231
FNC1 = 232
UPPER_SHIFT = 235
LATCH_TO_TEXT = 239

_GS = "\x1d"


def randomized_pad(position: int) -> int:
    """Кодовое слово-заполнитель с учётом псевдослучайного значения (Annex P).

    position — номер позиции кодового слова, начиная с 1.
    """
    pseudo = ((149 * position) % 253) + 1
    value = PAD + pseudo
    return value if value <= 254 else value - 254


@dataclass(frozen=True)
class EncodedData:
    """Кодовые слова данных, дополненные до ёмкости символа."""

    codewords: bytes
    capacity: int
    gs1: bool

    @property
    def utilization(self) -> float:
        return len(self.codewords) / self.capacity if self.capacity else 0.0


def encode_ascii(
    text: str,
    *,
    gs1: bool,
    separator: str = "ascii",
) -> list[int]:
    """ASCII-кодирование строки в кодовые слова (без заполнителей).

    В режиме GS1 первым кодовым словом добавляется FNC1 — так декодер
    возвращает идентификатор символики ]d2.

    Разделители GS (ASCII 29) внутри строки по умолчанию кодируются как
    обычный ASCII-символ (30 = 0x1D + 1) — именно так делает система
    «Честный знак» (подтверждено побитовой сверкой с эталонным СИ:
    извлечённые кодовые слова совпадают с нашими, кроме этих позиций).
    Передайте separator="fnc1", чтобы кодировать их кодовым словом FNC1
    (232), как рекомендует руководство GS1 Data Matrix.
    """
    if separator not in ("ascii", "fnc1"):
        raise ValueError(f"Недопустимый separator: {separator!r} (ascii | fnc1)")
    codewords: list[int] = [FNC1] if gs1 else []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        # Разделитель поля: обычный GS-символ либо FNC1 (эквивалент при чтении).
        if char == _GS:
            if separator == "fnc1" and gs1:
                codewords.append(FNC1)
            else:
                codewords.append(ord(_GS) + 1)
            index += 1
            continue

        # Уплотнение цифровых пар: 00..99 -> 130..229.
        if char.isdigit() and index + 1 < length and text[index + 1].isdigit():
            codewords.append(130 + int(text[index : index + 2]))
            index += 2
            continue

        code = ord(char)
        if code > 255:
            raise ValueError(f"Символ {char!r} вне диапазона ISO 8859-1 — недопустим в Data Matrix")
        if code >= 128:
            codewords.append(UPPER_SHIFT)
            codewords.append(code - 128 + 1)
        else:
            codewords.append(code + 1)
        index += 1

    return codewords


def pad_to_capacity(codewords: list[int], capacity: int) -> bytes:
    """Дополняет кодовые слова до ёмкости символа по правилам Annex P."""
    if len(codewords) > capacity:
        raise ValueError(
            f"Данные не помещаются в символ: {len(codewords)} > {capacity} кодовых слов"
        )
    padded = list(codewords)
    if len(padded) < capacity:
        padded.append(PAD)
    while len(padded) < capacity:
        padded.append(randomized_pad(len(padded) + 1))
    return bytes(padded)
