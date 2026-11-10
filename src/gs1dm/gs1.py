"""Разбор и проверка кода маркировки «Честный знак» (GS1 Data Matrix).

Поддерживаются два вида входной строки:

* «сырой» вид, как его отдаёт ГИС МТ: ``01046...21Serial\\x1d91ABCD\\x1d92...``
  (разделитель — GS, ASCII 29; допускаются текстовые записи ``\\x1d``,
  ``<GS>``, ``[GS]``);
* «человекочитаемый» вид со скобками: ``(01)046...(21)Serial(93)ABCD``.

В Data Matrix кода маркировки входят только AI 01, 21 и крипточасть
(93 либо 91+92). AI 10 и 17 кодируются на этикетке текстом и здесь не
допускаются.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

GS = "\x1d"

#: Допустимые символы для AI 21 (GS1 CSET 82).
CSET_82 = set("!\"%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz")

#: Допустимые символы крипточасти AI 92 (base64).
_AI92_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")

_ESCAPED_GS = re.compile(r"\\x1[dD]|\\u001[dD]|<GS>|\[GS\]", re.IGNORECASE)

KNOWN_AI = ("01", "21", "91", "92", "93")


class ValidationError(ValueError):
    """Структура кода маркировки не соответствует требованиям."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        self.errors = errors
        self.warnings = warnings or []
        super().__init__("; ".join(errors))


@dataclass
class MarkingCode:
    """Разобранный код маркировки."""

    gtin: str
    serial: str
    ai91: str | None = None
    ai92: str | None = None
    ai93: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        return self.ai93 is not None

    @property
    def has_crypto(self) -> bool:
        return self.ai93 is not None or (self.ai91 is not None and self.ai92 is not None)

    @property
    def structure(self) -> str:
        if self.ai93 is not None:
            return "укороченная (01 + 21 + 93)"
        if self.ai91 is not None and self.ai92 is not None:
            return "полная (01 + 21 + 91 + 92)"
        return "код идентификации (01 + 21, без крипточасти)"

    def element_string(self) -> str:
        """Строка данных GS1 с разделителями GS (без FNC1).

        GS ставится только ПОСЛЕ полей переменной длины. После GTIN (AI 01,
        фиксированные 14 цифр) разделитель не ставится — так формирует код
        сама система «Честный знак» (подтверждено декодированием эталонного
        СИ): 01<GTIN>21<serial><GS>91<..><GS>92<..>.
        """
        parts = [f"01{self.gtin}21{self.serial}"]
        if self.ai91 is not None and self.ai92 is not None:
            parts.append(f"91{self.ai91}")
            parts.append(f"92{self.ai92}")
        elif self.ai93 is not None:
            parts.append(f"93{self.ai93}")
        return GS.join(parts)

    def human_readable(self) -> str:
        parts = [f"(01){self.gtin}", f"(21){self.serial}"]
        if self.ai91 is not None and self.ai92 is not None:
            parts.append(f"(91){self.ai91}")
            parts.append(f"(92){self.ai92}")
        elif self.ai93 is not None:
            parts.append(f"(93){self.ai93}")
        return "".join(parts)

    def describe(self) -> str:
        lines = [
            f"GTIN (01):            {self.gtin}",
            f"Серийный номер (21):  {self.serial}  ({len(self.serial)} симв.)",
        ]
        if self.ai91 is not None:
            lines.append(f"Ключ проверки (91):   {self.ai91}")
        if self.ai92 is not None:
            lines.append(f"Код проверки (92):    {self.ai92}  ({len(self.ai92)} симв.)")
        if self.ai93 is not None:
            lines.append(f"Код проверки (93):    {self.ai93}")
        lines.append(f"Структура:            {self.structure}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Разбор входной строки
# --------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Убирает пробелы/переводы строк и раскрывает текстовые обозначения GS."""
    text = text.strip().lstrip("\ufeff")
    text = _ESCAPED_GS.sub(GS, text)
    # Пробелы внутри кода маркировки недопустимы; AI 21 с пробелами не встречается.
    if "(" not in text:
        text = re.sub(r"[\r\n\t ]+", "", text)
    return text


def _parse_human_readable(text: str) -> list[tuple[str, str]]:
    """Разбирает вид ``(01)...(21)...(93)....``.

    Границы полей определяются по маркерам известных AI, поэтому скобки и другие
    спецсимволы внутри значений (они допустимы в AI 21) не ломают разбор.
    """
    marker = re.compile(r"\((\d{2,4})\)")
    matches = [m for m in marker.finditer(text) if m.group(1) in KNOWN_AI]
    fields: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[start:end].replace(GS, "").strip()
        fields.append((match.group(1), value))
    return fields


def _split_raw(text: str) -> list[tuple[str, str]]:
    """Делит «сырую» строку на пары (AI, значение)."""
    if not text.startswith("01"):
        raise ValidationError(["Строка должна начинаться с AI 01 (GTIN)"])
    if len(text) < 2 + 14 + 2:
        raise ValidationError(["Строка слишком коротка для КМ: нет GTIN или серийного номера"])

    gtin = text[2:16]
    if not (len(gtin) == 14 and gtin.isdigit()):
        raise ValidationError([f"AI 01 должен содержать 14 цифр, получено: {gtin!r}"])

    rest = text[16:]
    # AI 01 имеет фиксированную длину, GS после него не нужен, но некоторые
    # генераторы его всё же вставляют — допускаем.
    rest = rest.lstrip(GS)
    if not rest.startswith("21"):
        raise ValidationError([f"После GTIN ожидался AI 21, получено: {rest[:2]!r}"])
    rest = rest[2:]

    # 1. Разделитель GS есть: серийный номер заканчивается на нём,
    #    дальше каждый сегмент начинается с AI.
    if GS in rest:
        serial, _, tail = rest.partition(GS)
        fields: list[tuple[str, str]] = [("01", gtin), ("21", serial)]
        for segment in tail.split(GS):
            if segment:
                fields.append((segment[:2], segment[2:]))
        return fields

    # 2. GS потерялся: восстанавливаем границы по известным длинам полей.

    # Укороченная структура: <serial><93><4 символа>
    if len(rest) >= 6 and rest[-6:-4] == "93":
        serial, ai93 = rest[:-6], rest[-4:]
        if 6 <= len(serial) <= 20:
            return [("01", gtin), ("21", serial), ("93", ai93)]

    # Полная структура: <serial>91<4 симв.>92<44|88 симв.>
    # Хвост без сериала: "91"(2) + ai91(4) + "92"(2) = 8 символов + длина ai92.
    for crypto_len in (44, 88):
        serial_len = len(rest) - 8 - crypto_len
        if not 6 <= serial_len <= 20:
            continue
        marker = rest[serial_len : serial_len + 2]
        if marker != "91":
            continue
        ai91 = rest[serial_len + 2 : serial_len + 6]
        if rest[serial_len + 6 : serial_len + 8] != "92":
            continue
        ai92 = rest[serial_len + 8 :]
        serial = rest[:serial_len]
        return [("01", gtin), ("21", serial), ("91", ai91), ("92", ai92)]

    raise ValidationError(
        [
            "Не удалось определить границы полей: разделитель GS (ASCII 29) отсутствует, "
            "и строка не совпадает ни с полной (91+92), ни с укороченной (93) структурой",
        ]
    )


# --------------------------------------------------------------------------
# Проверка полей
# --------------------------------------------------------------------------
def gtin_check_digit(gtin13: str) -> str:
    """Контрольная цифра GTIN по алгоритму GS1 (mod 10)."""
    digits = [int(c) for c in gtin13]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        total += digit * (3 if index % 2 == 0 else 1)
    return str((10 - total % 10) % 10)


def validate_gtin(gtin: str) -> list[str]:
    errors: list[str] = []
    if len(gtin) != 14 or not gtin.isdigit():
        errors.append(
            f"AI 01 (GTIN) должен содержать ровно 14 цифр, получено {len(gtin)}: {gtin!r}"
        )
        return errors
    expected = gtin_check_digit(gtin[:13])
    if gtin[13] != expected:
        errors.append(
            f"Неверная контрольная цифра GTIN: последняя цифра {gtin[13]}, "
            f"ожидается {expected} (GTIN {gtin})"
        )
    return errors


def _check_charset(value: str, allowed: set[str], field_name: str) -> list[str]:
    bad = sorted({c for c in value if c not in allowed})
    if bad:
        shown = ", ".join(repr(c) for c in bad)
        return [f"Недопустимые символы в {field_name}: {shown}"]
    return []


def parse_marking_code(text: str, *, allow_missing_crypto: bool = False) -> MarkingCode:
    """Разбирает строку КМ и проверяет её структуру.

    Raises:
        ValidationError: если структура не соответствует требованиям.
    """
    if not text or not text.strip():
        raise ValidationError(["Пустая строка кода маркировки"])

    normalized = normalize(text)
    errors: list[str] = []
    warnings: list[str] = []

    if "(" in normalized:
        fields = _parse_human_readable(normalized)
        if not fields:
            raise ValidationError(["Не удалось разобрать код в формате со скобками (01)...(21)..."])
    else:
        fields = _split_raw(normalized)

    seen: dict[str, str] = {}
    order: list[str] = []
    for ai, value in fields:
        if ai not in KNOWN_AI:
            errors.append(
                f"AI {ai} не входит в код маркировки «Честный знак» (допустимы 01, 21, 91, 92, 93)"
            )
            continue
        if ai in seen:
            errors.append(f"AI {ai} встречается в строке более одного раза")
            continue
        if not value:
            errors.append(f"Пустое значение для AI {ai}")
            continue
        seen[ai] = value
        order.append(ai)

    expected_order = [ai for ai in ("01", "21", "91", "92", "93") if ai in seen]
    if order != expected_order:
        errors.append(
            "Неверный порядок AI: ожидается 01 → 21 → (91 → 92) либо 01 → 21 → 93, "
            f"получено {' → '.join(order) if order else 'ничего'}"
        )

    if "01" not in seen:
        errors.append("В коде отсутствует AI 01 (GTIN)")
    if "21" not in seen:
        errors.append("В коде отсутствует AI 21 (серийный номер)")

    if errors:
        raise ValidationError(errors, warnings)

    gtin = seen["01"]
    serial = seen["21"]
    ai91 = seen.get("91")
    ai92 = seen.get("92")
    ai93 = seen.get("93")

    errors.extend(validate_gtin(gtin))

    # --- серийный номер ---------------------------------------------------
    if not 6 <= len(serial) <= 20:
        errors.append(
            f"AI 21 (серийный номер) должен быть длиной 6–20 символов, получено {len(serial)}: {serial!r}"
        )
    errors.extend(_check_charset(serial, CSET_82, "AI 21 (серийный номер)"))
    if serial and serial[0] not in "12345":
        warnings.append(
            f"Первый символ серийного номера {serial[0]!r} не является кодом страны ЕАЭС "
            "(1 — Армения, 2 — Беларусь, 3 — Казахстан, 4 — Кыргызстан, 5 — Россия)"
        )

    # --- крипточасть ------------------------------------------------------
    if ai93 is not None:
        if ai91 is not None or ai92 is not None:
            errors.append("Нельзя одновременно использовать AI 93 и AI 91/92")
        if len(ai93) != 4:
            errors.append(f"AI 93 должен содержать ровно 4 символа, получено {len(ai93)}: {ai93!r}")
        errors.extend(_check_charset(ai93, CSET_82, "AI 93 (код проверки)"))
    elif ai91 is not None or ai92 is not None:
        if ai91 is None:
            errors.append("Присутствует AI 92 без AI 91 — полная структура требует оба поля")
        if ai92 is None:
            errors.append("Присутствует AI 91 без AI 92 — полная структура требует оба поля")
        if ai91 is not None and len(ai91) != 4:
            errors.append(f"AI 91 должен содержать ровно 4 символа, получено {len(ai91)}: {ai91!r}")
        if ai91 is not None:
            errors.extend(_check_charset(ai91, CSET_82, "AI 91 (ключ проверки)"))
        if ai92 is not None:
            if len(ai92) not in (44, 88):
                errors.append(
                    f"AI 92 должен содержать 44 или 88 символов, получено {len(ai92)}: {ai92!r}"
                )
            errors.extend(_check_charset(ai92, _AI92_CHARS, "AI 92 (код проверки)"))
    else:
        if allow_missing_crypto:
            warnings.append(
                "В коде нет крипточасти (AI 93 или 91+92): это код идентификации (КИ), "
                "а не полный код маркировки — печатать его на товаре нельзя"
            )
        else:
            errors.append("В коде отсутствует крипточасть: нужен AI 93 либо пара AI 91 + AI 92")

    if errors:
        raise ValidationError(errors, warnings)

    return MarkingCode(
        gtin=gtin,
        serial=serial,
        ai91=ai91,
        ai92=ai92,
        ai93=ai93,
        warnings=warnings,
    )
