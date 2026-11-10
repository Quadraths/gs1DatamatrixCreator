"""HTTP-интерфейс (FastAPI) к генератору GS1 Data Matrix.

Эндпоинты:
- POST /api/create    — разобрать КМ, вернуть структуру + base64 PNG/SVG;
- POST /api/png       — вернуть PNG-изображение символа;
- POST /api/svg       — вернуть SVG-документ символа;
- POST /api/validate  — только проверка без генерации;
- GET  /health        — проверка живости.

Запуск: `uvicorn gs1dm.web:app --host 127.0.0.1 --port 8000` или
`python -m gs1dm.web --port 8000`. Все операции чисто локальные: крипточасть
не вычисляется, на вход подаётся уже полученная строка КМ (см. README).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import create
from .gs1 import ValidationError, parse_marking_code
from .render import png_bytes, svg_string

app = FastAPI(
    title="GS1 Data Matrix Creator",
    description=(
        "Генерация GS1 Data Matrix (ECC 200) по коду маркировки «Честный знак». "
        "Крипточасть (AI 91/92 или 93) должна быть получена из ГИС МТ заранее — "
        "сервис только кодирует готовую строку в символ."
    ),
    version="0.1.0",
)

# Дашборд и Swagger могут открываться с любой машины — разрешаем междоменные
# запросы, чтобы страницу можно было открыть и вне origin самого API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRequest(BaseModel):
    """Запрос на генерацию символа.

    Задайте либо `code` (полная строка КМ), либо отдельные поля `gtin`,
    `serial` и крипто-часть — строка соберётся автоматически.
    """

    code: str | None = Field(
        default=None,
        description=(
            "Код маркировки одной строкой: '(01)...(21)...(91)...(92)...' "
            "или сырой вид '0104...215...\\x1d91...'."
        ),
    )
    gtin: str | None = Field(
        default=None,
        description="GTIN-14 (AI 01), если code не задан.",
    )
    serial: str | None = Field(
        default=None,
        description="Серийный номер (AI 21), если code не задан.",
    )
    ai91: str | None = Field(default=None, description="Ключ проверки (AI 91).")
    ai92: str | None = Field(default=None, description="Код проверки (AI 92), base64, 44/88 симв.")
    ai93: str | None = Field(default=None, description="Код проверки (AI 93), 4 символа.")
    allow_missing_crypto: bool = Field(
        default=False,
        description="Разрешить код идентификации без крипточасти (не для печати на товаре).",
    )
    allow_rectangular: bool = Field(
        default=False,
        description="Разрешить прямоугольные символы Data Matrix.",
    )
    scale: int = Field(default=10, ge=1, le=100, description="Пикселей на модуль (PNG).")
    quiet_zone: int = Field(default=2, ge=0, le=20, description="Свободное поле, в модулях.")
    dpi: int = Field(default=300, ge=72, le=2400, description="DPI в метаданных PNG.")


class CreateResponse(BaseModel):
    """Ответ генерации: разобранные поля, символ и изображения."""

    gtin: str
    serial: str
    ai91: str | None = None
    ai92: str | None = None
    ai93: str | None = None
    structure: str
    warnings: list[str] = []
    element_string: str = Field(description="Строка данных GS1 с разделителями GS (ASCII 29).")
    symbol: str = Field(description="Размер символа, например '36x36'.")
    data_capacity: int
    error_codewords: int
    codewords_used: int
    png_base64: str | None = Field(default=None, description="PNG-изображение в base64.")
    svg: str | None = Field(default=None, description="SVG-документ.")


class ValidateResponse(BaseModel):
    """Ответ проверки строки КМ без генерации символа."""

    valid: bool
    gtin: str | None = None
    serial: str | None = None
    structure: str | None = None
    warnings: list[str] = []
    errors: list[str] = []


@dataclass(frozen=True)
class _Options:
    """Опции рендера, извлечённые из CreateRequest."""

    allow_missing_crypto: bool
    square_only: bool
    scale: int
    quiet_zone: int
    dpi: int


def _resolve_code(req: CreateRequest) -> str:
    """Собирает входную строку КМ: из code либо из отдельных полей."""
    has_code = req.code is not None and req.code.strip() != ""
    has_fields = bool(req.gtin or req.serial or req.ai91 or req.ai92 or req.ai93)
    if has_code and has_fields:
        raise HTTPException(
            status_code=422,
            detail="Укажите либо 'code', либо отдельные поля (gtin/serial/...), но не оба",
        )
    if has_code:
        return req.code
    if req.gtin and req.serial:
        if req.ai93 and (req.ai91 or req.ai92):
            raise HTTPException(
                status_code=422,
                detail="Нельзя одновременно передавать ai93 и ai91/ai92",
            )
        parts = [f"01{req.gtin}21{req.serial}"]
        if req.ai91 or req.ai92:
            parts.append(f"91{req.ai91 or ''}")
            parts.append(f"92{req.ai92 or ''}")
        elif req.ai93:
            parts.append(f"93{req.ai93}")
        return "\x1d".join(parts)
    raise HTTPException(
        status_code=422,
        detail="Не передан код маркировки: задайте 'code' или 'gtin'+'serial' (+ крипто-часть)",
    )


def _build(req: CreateRequest):
    """Разбирает строку КМ и строит символ; ошибки валидации → HTTP 422."""
    text = _resolve_code(req)
    try:
        return create(
            text,
            allow_missing_crypto=req.allow_missing_crypto,
            square_only=not req.allow_rectangular,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc


@app.post(
    "/api/create",
    response_model=CreateResponse,
    response_model_exclude_none=True,
    summary="Сгенерировать символ и вернуть данные + base64 PNG/SVG",
)
def api_create(req: CreateRequest) -> CreateResponse:
    bar = _build(req)
    return CreateResponse(
        gtin=bar.code.gtin,
        serial=bar.code.serial,
        ai91=bar.code.ai91,
        ai92=bar.code.ai92,
        ai93=bar.code.ai93,
        structure=bar.code.structure,
        warnings=list(bar.code.warnings),
        element_string=bar.element_string,
        symbol=bar.symbol.size_label,
        data_capacity=bar.symbol.data_capacity,
        error_codewords=bar.symbol.error_codewords,
        codewords_used=len(bar.data.codewords),
        png_base64=base64.b64encode(
            png_bytes(
                bar.matrix,
                scale=req.scale,
                quiet_zone=req.quiet_zone,
                dpi=req.dpi,
            )
        ).decode("ascii"),
        svg=svg_string(
            bar.matrix,
            quiet_zone=req.quiet_zone,
            title=f"GS1 DataMatrix {bar.code.gtin}",
        ),
    )


@app.post("/api/png", response_class=Response, summary="Вернуть PNG-изображение символа")
def api_png(req: CreateRequest) -> Response:
    bar = _build(req)
    data = png_bytes(
        bar.matrix,
        scale=req.scale,
        quiet_zone=req.quiet_zone,
        dpi=req.dpi,
    )
    return Response(content=data, media_type="image/png")


@app.post("/api/svg", response_class=Response, summary="Вернуть SVG-документ символа")
def api_svg(req: CreateRequest) -> Response:
    bar = _build(req)
    svg = svg_string(
        bar.matrix,
        quiet_zone=req.quiet_zone,
        title=f"GS1 DataMatrix {bar.code.gtin}",
    )
    return Response(content=svg, media_type="image/svg+xml")


@app.post(
    "/api/validate",
    response_model=ValidateResponse,
    summary="Проверить код маркировки без генерации",
)
def api_validate(req: CreateRequest) -> ValidateResponse:
    text = _resolve_code(req)
    try:
        code = parse_marking_code(text, allow_missing_crypto=req.allow_missing_crypto)
    except ValidationError as exc:
        return ValidateResponse(valid=False, errors=list(exc.errors))
    return ValidateResponse(
        valid=True,
        gtin=code.gtin,
        serial=code.serial,
        structure=code.structure,
        warnings=list(code.warnings),
    )


@app.get("/health", summary="Проверка живости сервиса")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
    summary="Дашборд тестирования API",
)
def dashboard() -> str:
    return resources.files(__package__).joinpath("dashboard.html").read_text(encoding="utf-8")


def main() -> None:  # pragma: no cover - ручной запуск
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="HTTP-сервер GS1 Data Matrix")
    parser.add_argument("--host", default=None, help="по умолчанию из .env (GS1DM_HOST)")
    parser.add_argument("--port", type=int, default=None, help="по умолчанию из .env (GS1DM_PORT)")
    args = parser.parse_args()
    host, port = server_settings(host=args.host, port=args.port)
    uvicorn.run(app, host=host, port=port)


def _read_env_file() -> dict[str, str]:
    """Читает .env из корня проекта (KEY=VALUE, без сторонних зависимостей)."""
    path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def server_settings(host: str | None = None, port: int | None = None) -> tuple[str, int]:
    """Итоговые host/port: аргументы CLI > .env > значения по умолчанию.

    По умолчанию слушаем все интерфейсы (0.0.0.0) — доступ с любого IP.
    """
    env = _read_env_file()
    if host is None:
        host = env.get("GS1DM_HOST", "0.0.0.0")
    if port is None:
        port = int(env.get("GS1DM_PORT", "8000"))
    return host, port


if __name__ == "__main__":  # pragma: no cover
    main()
