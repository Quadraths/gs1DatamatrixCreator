# ПЕРЕДАЧА СЕССИИ: совпадение с эталоном «Честный знак» достигнуто; добавлен FastAPI (2026-11-09)

## FastAPI-интерфейс (новое в этой сессии)

БАГФИКС (важно): `_split_raw` в gs1.py — fallback-разбор строки БЕЗ GS считал
хвост как 12 симв. (`len(rest) - 12 - crypto_len`), а надо 8 (`91`(2)+ai91(4)+`92`(2));
также добавлено присваивание `serial = rest[:serial_len]` (был UnboundLocalError —
переменная существовала только в GS-ветке). RAW-коды из БД теперь разбираются.
Пример: `0104650263540384215STKT-RxIXtao91EE1292AhXa+...=` → serial `5STKT-RxIXtao`
(13 симв., «5»=Россия — принадлежит сериалу!), ai91 EE12, ai92 44 симв., 36x36, 86/86 cw.
Тест `test_raw_code_from_db` в tests/test_web.py.

`src/gs1dm/web.py` — HTTP-сервис над генератором:
- `POST /api/create` — поля КМ + base64 PNG + SVG;
- `POST /api/png` — PNG (image/png); `POST /api/svg` — SVG (image/svg+xml);
- `POST /api/validate` — проверка без генерации (всегда 200, `valid`/`errors`);
- `GET /health` и `GET /` — дашборд тестирования API (src/gs1dm/dashboard.html,
отдаётся через importlib.resources).

Вход: либо `code` (строка КМ), либо `gtin`+`serial`+крипта (`ai91`+`ai92` или
`ai93`) — строка собирается автоматически; конфликт/нехватка → 422.
Ошибки валидации → 422 `detail.errors`. Параметры рендера: `scale` (1..100),
`quiet_zone` (0..20), `dpi` (72..2400), `allow_missing_crypto`,
`allow_rectangular`. Сетевые настройки: `.env` в корне (GS1DM_HOST=0.0.0.0 —
доступ с любого IP, GS1DM_PORT=8000); CLI --host/--port имеют приоритет;
CORS `allow_origins=["*"]`. Читалка .env — `_read_env_file()` в web.py,
без сторонних зависимостей. Запуск: `uv run gs1dm-web` (консольная команда
gs1dm-web = gs1dm.web:main добавлена в pyproject.toml; python -m gs1dm.web
тоже работает; сырой uvicorn .env НЕ читает и слушает 127.0.0.1 — не
использовать для внешнего доступа).
Тесты: `tests/test_web.py` (9 тестов через
TestClient, включая round-trip PNG через zxing-cpp, дашборд и сверку `code` vs полей).

Зависимости: fastapi, uvicorn, httpx установлены в venv; в pyproject.toml
добавлены extras `web` и продублированы в dependency-groups dev.
`render.py`: добавлены `png_bytes()` и `svg_string()` (bytes/str в память);
`write_png`/`write_svg` теперь обёртки над ними (поведение не изменилось).

## Итог предыдущего этапа — ГЛАВНОЕ

Задача m00493 («перейти на C40/Text high-level кодирование») ЗАКРЫТА БЕЗ РЕАЛИЗАЦИИ:
гипотеза оказалась неверной. Побитовая сверка с эталоном ЧЗ показала:

**«Честный знак» использует чистое ASCII-кодирование** (Annex P). Отличие от нашей
прежней реализации было только в одном: разделители GS (\x1d) внутри строки ЧЗ
кодирует как **обычный ASCII-символ** (0x1D + 1 = 30), а НЕ как FNC1 (232).
Ведущий FNC1 (232) перед данными при этом присутствует.

Доказательство: кодовые слова эталона извлечены из фото побитово
(перспективное выравнивание по 4 углам zxing + обратный placement Annex M.1),
**ECC-проверка (Reed-Solomon, 128 кодовых слов) сошлась** — извлечение достоверно.
Наши кодовые слова совпали с эталонными 1:1, пиксельная разница **0/1296 (0.00%)**.

## Изменённые файлы

- `src/gs1dm/encoder.py` — `encode_ascii(text, *, gs1, separator="ascii")`:
  новый параметр `separator` со значениями `"ascii"` (по умолчанию, как ЧЗ:
  GS → 0x1D+1) и `"fnc1"` (GS → FNC1 232, прежнее поведение по рекомендации GS1).
  FNC1 первым кодовым словом при gs1=True сохранён.
- `tools/inspect_reference.py` — ИСПРАВЛЕН БАГ `strip_placement_borders`:
  старый маппинг учитывал только ОДНУ разделительную колонку/строку между
  областями данных, а `build_matrix` вставляет кромки с ОБОИХ сторон каждой
  области (две подряд). Из-за этого все данные после 16-го столбца читались
  со сдвигом и ECC-проверка эталона «падала». Новый маппинг (`col_of`/`row_of`)
  зеркалит build_matrix. Round-trip проверен: `tools/roundtrip_check.py`.
- `tools/extract_reference.py` — НОВЫЙ: точное извлечение кодовых слов из
  `out/user_dm.png` (PIL QUAD-трансформация по углам zxing, порядок точек
  UL, LL, LR, UR; выборка 3x3 точки на модуль; ECC-верификация).
- `tools/roundtrip_check.py` — НОВЫЙ: round-trip тест placement↔extraction.
- `tests/test_chz_reference.py` — НОВЫЙ золотой тест: кодовые слова эталона ЧЗ
  захардкожены (86 шт.), проверка `create(...) == эталон` + пиксельная сверка
  с фото (0 расхождений) + ECC-проверка извлечения.
- README.md — раздел «Кодирование» переписан (см. ниже).

Зависимости `__init__.py` не изменялись: `encode_ascii` по-прежнему вызывается
с дефолтным separator="ascii", поэтому поведение `create()` теперь СОВПАДАЕТ с ЧЗ.

## Проверки (все зелёные)

- selftest 12/12 (round-trip через zxing), test_all_sizes 24/24,
  test_rectangular 6/6, test_gs1_conformance 3/3, test_chz_reference OK.
- `ruff check src tests tools` — чисто (uv tool run с env
  UV_CACHE_DIR=$PWD\.uv-cache, UV_TOOL_DIR=$PWD\.uv-tools, UV_TOOL_BIN_DIR=$PWD\.uv-bin;
  глобальные UV-каталоги залочены os error 5).

## Почему НЕ C40/Text (история вопроса)

Прежняя сессия предположила C40 по ошибочному разбору: старый
`strip_placement_borders` читал биты со сдвигом, из-за чего «структурный разбор»
показывал ложный LATCH_C40(230) на индексе ~41 и ~14% пиксельной разницы.
После исправления маппинга и перспективного выравнивания разбор показывает
чистый ASCII-поток (232, пары цифр 130..229, c+1, GS→30).

High-level Annex S (zxing) портировать НЕ нужно. Если когда-нибудь понадобится
(например, для не-ЧЗ применений), эталонные исходники: zxing Java
HighLevelEncoder/C40Encoder/TextEncoder/ASCIIEncoder/EncoderContext (Annex S) —
детально разобраны в предыдущем HANDOVER, но реализация отменена.

## Верификационный инструментарий

- `tools/extract_reference.py` — канонический способ свериться с фото эталона.
- Декодер: `zxingcpp.read_barcodes(Image.open(...).convert('L'))[0].bytes`.
- Оракул-генератор: `zxingcpp.create_barcode(es, BarcodeFormat.DataMatrix,
  symbology_identifier=']d2', force_square=True)` (путь zint, minimal encoding) —
  ПОЛЕЗНО ТОЛЬКО для сравнения с zint; ЧЗ кодирует НЕ как zint minimal
  (пиксельная разница 21.2%), а как чистый ASCII (совпадение 100%).

## Эталонные данные

- Эталон ЧЗ: `out/user_dm.png`, 36x36, 85 байт:
  `0104640711961304215;I)DmC:IDt*L\x1d91EE12\x1d924a8GsyItTVweCsj65+Wk5AxvQD6NnNAcmMIKSsLGAek=`
- 86 кодовых слов данных эталона (см. REFERENCE_DATA_CODEWORDS в
  `tests/test_chz_reference.py`); первые 24 показывают структуру:
  232 (FNC1), затем ASCII: пары цифр 01 04 64 07 ... → 131 134 194 137,
  '5'→54, ';'→60, 'I'→74, ')'→42, ..., GS→30, ..., 91→~, 92→...

## Среда (кратко)

- Запуск: `.\.venv\Scripts\python.exe`, `$env:PYTHONIOENCODING='utf-8'`,
  UV_CACHE_DIR=$PWD\.uv-cache обязательно (глобальный залочен os error 5),
  UV_TOOL_DIR=$PWD\.uv-tools, UV_TOOL_BIN_DIR=$PWD\.uv-bin для uv tool run ruff.
- Зависимости: pillow, zxing-cpp (декодирование, оракул, сравнение).
- ruff-конфиг в pyproject.toml (line-length 100, select E,F,W,I,UP,B,SIM,RUF;
  tests/* ignore E402).
