"""Отрисовка матрицы Data Matrix в PNG (Pillow) и SVG (stdlib)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

Matrix = list[list[bool]]


def _dimensions(matrix: Matrix, quiet_zone: int, scale: int) -> tuple[int, int]:
    height = (len(matrix) + 2 * quiet_zone) * scale
    width = (len(matrix[0]) + 2 * quiet_zone) * scale
    return width, height


def png_bytes(
    matrix: Matrix,
    *,
    scale: int = 10,
    quiet_zone: int = 2,
    dpi: int | None = 300,
    foreground: str = "black",
    background: str = "white",
) -> bytes:
    """Рендерит символ в PNG и возвращает байты (для HTTP-ответов и памяти)."""
    from PIL import Image, ImageColor

    if scale < 1:
        raise ValueError("scale должен быть >= 1")
    if quiet_zone < 0:
        raise ValueError("quiet_zone не может быть отрицательным")

    width, height = _dimensions(matrix, quiet_zone, scale)
    image = Image.new("RGB", (width, height), ImageColor.getrgb(background))
    fg = ImageColor.getrgb(foreground)

    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if not filled:
                continue
            left = (x + quiet_zone) * scale
            top = (y + quiet_zone) * scale
            image.paste(fg, (left, top, left + scale, top + scale))

    buffer = BytesIO()
    save_kwargs = {}
    if dpi:
        save_kwargs["dpi"] = (dpi, dpi)
    image.save(buffer, format="PNG", **save_kwargs)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# PNG
# --------------------------------------------------------------------------
def write_png(
    matrix: Matrix,
    path: str | Path,
    *,
    scale: int = 10,
    quiet_zone: int = 2,
    dpi: int | None = 300,
    foreground: str = "black",
    background: str = "white",
) -> tuple[int, int]:
    """Сохраняет символ в PNG. Возвращает размер изображения в пикселях."""
    data = png_bytes(
        matrix,
        scale=scale,
        quiet_zone=quiet_zone,
        dpi=dpi,
        foreground=foreground,
        background=background,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _dimensions(matrix, quiet_zone, scale)


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------
def svg_string(
    matrix: Matrix,
    *,
    quiet_zone: int = 2,
    module_size_mm: float = 0.5,
    foreground: str = "#000000",
    background: str = "#FFFFFF",
    title: str = "GS1 DataMatrix",
) -> str:
    """Строит SVG-документ и возвращает его строкой."""
    if module_size_mm <= 0:
        raise ValueError("module_size_mm должен быть > 0")
    if quiet_zone < 0:
        raise ValueError("quiet_zone не может быть отрицательным")

    rows = len(matrix)
    cols = len(matrix[0])
    total_w = cols + 2 * quiet_zone
    total_h = rows + 2 * quiet_zone

    width_mm = total_w * module_size_mm
    height_mm = total_h * module_size_mm

    # Склеиваем горизонтальные сегменты в один <rect> — файл заметно компактнее.
    rects: list[str] = []
    for y, row in enumerate(matrix):
        start = None
        for x in range(cols + 1):
            filled = x < cols and row[x]
            if filled and start is None:
                start = x
            elif not filled and start is not None:
                rects.append(
                    f'<rect x="{(start + quiet_zone) * module_size_mm:.4f}" '
                    f'y="{(y + quiet_zone) * module_size_mm:.4f}" '
                    f'width="{(x - start) * module_size_mm:.4f}" '
                    f'height="{module_size_mm:.4f}"/>'
                )
                start = None

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{width_mm:.4f}mm" height="{height_mm:.4f}mm" '
            f'viewBox="0 0 {width_mm:.4f} {height_mm:.4f}" '
            f'shape-rendering="crispEdges">'
        ),
        f"<title>{escape(title)}</title>",
        f'<rect width="100%" height="100%" fill="{background}"/>',
        f'<g fill="{foreground}">',
        *rects,
        "</g>",
        "</svg>",
    ]
    return "\n".join(lines) + "\n"


def write_svg(
    matrix: Matrix,
    path: str | Path,
    *,
    quiet_zone: int = 2,
    module_size_mm: float = 0.5,
    foreground: str = "#000000",
    background: str = "#FFFFFF",
    title: str = "GS1 DataMatrix",
) -> tuple[float, float]:
    """Сохраняет символ в SVG. Возвращает размер в миллиметрах."""
    text = svg_string(
        matrix,
        quiet_zone=quiet_zone,
        module_size_mm=module_size_mm,
        foreground=foreground,
        background=background,
        title=title,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    rows = len(matrix)
    cols = len(matrix[0])
    return (cols + 2 * quiet_zone) * module_size_mm, (rows + 2 * quiet_zone) * module_size_mm


# --------------------------------------------------------------------------
# Текстовая и ASCII-визуализация (для отладки в терминале)
# --------------------------------------------------------------------------
def to_ascii(matrix: Matrix, quiet_zone: int = 1) -> str:
    """Двухсимвольное текстовое представление символа."""
    blank = " " * (2 * (len(matrix[0]) + 2 * quiet_zone))
    lines = [blank for _ in range(quiet_zone)]
    for row in matrix:
        line = " " * (2 * quiet_zone)
        line += "".join("██" if cell else "  " for cell in row)
        line += " " * (2 * quiet_zone)
        lines.append(line)
    lines.extend(blank for _ in range(quiet_zone))
    return "\n".join(lines)
