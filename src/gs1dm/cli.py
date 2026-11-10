"""Командная строка: создание GS1 Data Matrix по коду маркировки «Честный знак»."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from . import create, parse_marking_code, render_png, render_svg
from .gs1 import ValidationError
from .render import to_ascii

_DEFAULT_DPI = 300


def _sanitize(name: str) -> str:
    """Безопасное имя файла из GTIN + серийного номера."""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", name).strip("._")
    return cleaned or "code"


def _iter_file(path: Path, column: str | None) -> list[tuple[int, str]]:
    """Читает коды из текстового файла или CSV. Возвращает (номер строки, код)."""
    raw = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()

    if suffix == ".json":
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = payload[column] if column and column in payload else list(payload.values())
        if not isinstance(payload, list):
            raise SystemExit("JSON должен содержать массив строк или объект с массивом")
        return [(i + 1, str(item)) for i, item in enumerate(payload)]

    lines = raw.splitlines()
    result: list[tuple[int, str]] = []
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.reader(lines, delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return []
        header = [cell.strip().lower() for cell in rows[0]]
        start = 0
        index = None
        if column:
            try:
                index = header.index(column.strip().lower())
            except ValueError:
                raise SystemExit(
                    f"В CSV нет столбца {column!r}. Доступные: {', '.join(header)}"
                ) from None
            start = 1
        elif any(cell in header for cell in ("км", "код", "code", "km", "marking_code")):
            for candidate in ("км", "код", "code", "km", "marking_code"):
                if candidate in header:
                    index = header.index(candidate)
                    break
            start = 1
        for offset, row in enumerate(rows[start:], start=start + 1):
            if index is not None:
                value = row[index] if index < len(row) else ""
            else:
                value = row[0] if row else ""
            if value.strip():
                result.append((offset, value.strip()))
        return result

    for number, line in enumerate(lines, start=1):
        if line.strip() and not line.lstrip().startswith("#"):
            result.append((number, line.strip()))
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gs1dm",
        description=(
            "Генерация GS1 Data Matrix (ECC 200) по коду маркировки «Честный знак». "
            "Поддерживается полная структура (01+21+91+92) и укороченная (01+21+93)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  gs1dm create '(01)04811644010685(21)25mpid7gn7wzu(91)FFD0(92)dGVzdDk5...'\n"
            "  gs1dm create --input codes.csv --outdir labels --png --svg\n"
            "  gs1dm validate --input codes.txt\n"
            "  gs1dm show '(01)04811289005596(21)5PoVL5(93))H7P' --ascii\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "code",
            nargs="?",
            help="Код маркировки одной строкой (или используйте --input)",
        )
        target.add_argument(
            "-i",
            "--input",
            type=Path,
            help="Файл с кодами: .txt (по одному в строке), .csv/.tsv, .json",
        )
        target.add_argument(
            "-c",
            "--column",
            help="Имя столбца в CSV/JSON с кодом маркировки",
        )
        target.add_argument(
            "--allow-missing-crypto",
            action="store_true",
            help="Разрешить код идентификации без крипточасти (AI 93 или 91+92)",
        )
        target.add_argument(
            "--allow-rectangular",
            action="store_true",
            help="Разрешить прямоугольные символы Data Matrix",
        )
        target.add_argument("-q", "--quiet", action="store_true", help="Не печатать сводку")

    create_parser = sub.add_parser("create", help="Создать изображения Data Matrix")
    add_common(create_parser)
    create_parser.add_argument(
        "-o", "--outdir", type=Path, default=Path("out"), help="Каталог для файлов"
    )
    create_parser.add_argument(
        "-n", "--name", help="Имя файла без расширения (для одиночного кода)"
    )
    create_parser.add_argument(
        "--png", action="store_true", help="Сохранить PNG (по умолчанию, если не задан формат)"
    )
    create_parser.add_argument("--svg", action="store_true", help="Сохранить SVG")
    create_parser.add_argument(
        "--scale", type=int, default=10, help="Пикселей на модуль для PNG (по умолчанию 10)"
    )
    create_parser.add_argument(
        "--dpi", type=int, default=_DEFAULT_DPI, help="DPI в метаданных PNG (по умолчанию 300)"
    )
    create_parser.add_argument(
        "--quiet-zone",
        type=int,
        default=2,
        help="Ширина свободного поля в модулях (по умолчанию 2)",
    )
    create_parser.add_argument(
        "--module-mm", type=float, default=0.5, help="Размер модуля в мм для SVG (по умолчанию 0.5)"
    )
    create_parser.add_argument("--ascii", action="store_true", help="Показать символ в терминале")

    validate_parser = sub.add_parser("validate", help="Проверить коды без генерации")
    add_common(validate_parser)

    show_parser = sub.add_parser("show", help="Разобрать код и показать структуру")
    add_common(show_parser)
    show_parser.add_argument("--ascii", action="store_true", help="Показать символ в терминале")

    return parser


def _collect(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if args.code:
        items.append(("аргумент", args.code))
    if args.input:
        if not args.input.exists():
            raise SystemExit(f"Файл не найден: {args.input}")
        for number, value in _iter_file(args.input, getattr(args, "column", None)):
            items.append((f"{args.input.name}:{number}", value))
    if not items:
        parser.error("укажите код аргументом или через --input")
    return items


def _cmd_validate(args: argparse.Namespace, items: list[tuple[str, str]]) -> int:
    ok = 0
    failed = 0
    for source, value in items:
        try:
            code = parse_marking_code(value, allow_missing_crypto=args.allow_missing_crypto)
        except ValidationError as exc:
            failed += 1
            print(f"[FAIL] {source}: {value}")
            for error in exc.errors:
                print(f"       - {error}")
            continue
        ok += 1
        print(f"[ OK ] {source}: {code.human_readable()} — {code.structure}")
        for warning in code.warnings:
            print(f"       ! {warning}")
    print(f"\nПроверено {len(items)}: корректных {ok}, с ошибками {failed}")
    return 1 if failed else 0


def _cmd_show(args: argparse.Namespace, items: list[tuple[str, str]]) -> int:
    status = 0
    for source, value in items:
        try:
            bar = create(
                value,
                allow_missing_crypto=args.allow_missing_crypto,
                square_only=not args.allow_rectangular,
            )
        except ValidationError as exc:
            status = 1
            print(f"[FAIL] {source}".ljust(40))
            for error in exc.errors:
                print(f"       - {error}")
            continue
        print(f"=== {source}")
        print(bar.summary())
        for warning in bar.code.warnings:
            print(f"  ! {warning}")
        if args.ascii:
            print()
            print(to_ascii(bar.matrix))
    return status


def _cmd_create(args: argparse.Namespace, items: list[tuple[str, str]]) -> int:
    want_png = args.png or not args.svg
    want_svg = args.svg

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    created = 0
    failed = 0
    for source, value in items:
        try:
            bar = create(
                value,
                allow_missing_crypto=args.allow_missing_crypto,
                square_only=not args.allow_rectangular,
            )
        except ValidationError as exc:
            failed += 1
            print(f"[FAIL] {source}: {value}")
            for error in exc.errors:
                print(f"       - {error}")
            continue

        base = args.name if (args.name and len(items) == 1) else _sanitize(bar.code.serial)
        if (outdir / f"{base}.png").exists() and len(items) > 1:
            base = f"{base}_{bar.code.gtin}"

        if not args.quiet:
            print(f"[ OK ] {source}: {base} — {bar.symbol.size_label}")
            for warning in bar.code.warnings:
                print(f"       ! {warning}")

        if want_png:
            width, height = render_png(
                bar,
                outdir / f"{base}.png",
                scale=args.scale,
                quiet_zone=args.quiet_zone,
                dpi=args.dpi,
            )
            if not args.quiet:
                print(f"       PNG: {width}x{height} px")
        if want_svg:
            w_mm, h_mm = render_svg(
                bar,
                outdir / f"{base}.svg",
                quiet_zone=args.quiet_zone,
                module_size_mm=args.module_mm,
            )
            if not args.quiet:
                print(f"       SVG: {w_mm:.2f}x{h_mm:.2f} мм")

        if args.ascii:
            print()
            print(to_ascii(bar.matrix))
        created += 1

    if len(items) > 1:
        print(f"\nГотово: {created} из {len(items)}, ошибок {failed}. Каталог: {outdir.resolve()}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    items = _collect(parser, args)

    if getattr(args, "command", None) == "validate":
        return _cmd_validate(args, items)
    if args.command == "show":
        return _cmd_show(args, items)
    return _cmd_create(args, items)


if __name__ == "__main__":
    sys.exit(main())
