"""Тесты HTTP-интерфейса (FastAPI) через TestClient."""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from PIL import Image

from gs1dm.gs1 import GS
from gs1dm.web import app

SAMPLE = (
    "(01)04640711961304(21)5;I)DmC:IDt*L"
    "(91)EE12(92)4a8GsyItTVweCsj65+Wk5AxvQD6NnNAcmMIKSsLGAek="
)
ELEMENT_STRING = (
    "0104640711961304215;I)DmC:IDt*L" + GS + "91EE12" + GS
    + "924a8GsyItTVweCsj65+Wk5AxvQD6NnNAcmMIKSsLGAek="
)

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_validate_ok() -> None:
    body = client.post("/api/validate", json={"code": SAMPLE}).json()
    assert body["valid"] is True
    assert body["gtin"] == "04640711961304"
    assert body["serial"] == "5;I)DmC:IDt*L"
    assert body["errors"] == []


def test_validate_errors() -> None:
    body = client.post("/api/validate", json={"code": "(01)04640711961305(21)bad!!"}).json()
    assert body["valid"] is False
    assert any("контрольная цифра" in e for e in body["errors"])


def test_png_roundtrip_through_zxing() -> None:
    response = client.post("/api/png", json={"code": SAMPLE, "scale": 10})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    image = Image.open(io.BytesIO(response.content))
    import zxingcpp

    results = zxingcpp.read_barcodes(image.convert("L"))
    assert results, "PNG с /api/png должен декодироваться"
    assert results[0].bytes.decode("latin-1") == ELEMENT_STRING


def test_create_fields_match_code() -> None:
    by_code = client.post("/api/create", json={"code": SAMPLE, "scale": 4}).json()
    by_fields = client.post(
        "/api/create",
        json={
            "gtin": "04640711961304",
            "serial": "5;I)DmC:IDt*L",
            "ai91": "EE12",
            "ai92": "4a8GsyItTVweCsj65+Wk5AxvQD6NnNAcmMIKSsLGAek=",
            "scale": 4,
        },
    ).json()
    assert by_code["element_string"] == by_fields["element_string"] == ELEMENT_STRING
    assert by_code["symbol"] == by_fields["symbol"] == "36x36"
    assert by_code["codewords_used"] == by_fields["codewords_used"]
    image = Image.open(io.BytesIO(base64.b64decode(by_code["png_base64"])))
    assert image.size == ((36 + 4) * 4, (36 + 4) * 4)


def test_create_errors_are_422() -> None:
    # Нет ни code, ни полей.
    assert client.post("/api/create", json={}).status_code == 422
    # Конфликт code и полей.
    assert client.post("/api/create", json={"code": SAMPLE, "gtin": "1"}).status_code == 422
    # Нет крипточасти без allow_missing_crypto.
    assert (
        client.post("/api/create", json={"code": "(01)04640711961304(21)5;I)DmC:IDt*L"}).status_code
        == 422
    )
    # Неверный GTIN — в detail.errors.
    response = client.post("/api/create", json={"code": "(01)04640711961305(21)5;I)DmC:IDt*L(93)AB12"})
    assert response.status_code == 422
    assert "контрольная цифра" in str(response.json())


def test_validate_accepts_missing_crypto_with_flag() -> None:
    body = client.post(
        "/api/validate",
        json={"code": "(01)04640711961304(21)5;I)DmC:IDt*L", "allow_missing_crypto": True},
    ).json()
    assert body["valid"] is True
    assert body["warnings"], "должно быть предупреждение о коде идентификации"


def test_svg_document() -> None:
    response = client.post("/api/svg", json={"code": SAMPLE})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    text = response.content.decode("utf-8")
    assert text.startswith("<?xml")
    assert "<rect" in text


def test_dashboard_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    assert "GS1 Data Matrix" in text
    assert "/api/create" in text


def test_raw_code_from_db() -> None:
    """RAW-строка без GS (как в БД): границы полей восстанавливаются по длинам."""
    raw = (
        "0104650263540384"
        "21" "5STKT-RxIXtao"
        "91" "EE12"
        "92" "AhXa+Y9fO9bbvKAP7plAbNMUZn3LkCk4hXSn85XtyBg="
    )
    body = client.post("/api/create", json={"code": raw}).json()
    assert body["gtin"] == "04650263540384"
    assert body["serial"] == "5STKT-RxIXtao"
    assert body["ai91"] == "EE12"
    assert len(body["ai92"]) == 44
    assert body["symbol"] == "36x36"
    assert body["codewords_used"] == 86
    # Та же строка с явными GS даёт идентичную элементную строку.
    with_gs = raw.replace("21" + body["serial"], "21" + body["serial"] + GS) \
                 .replace("91EE12", "91EE12" + GS)
    body2 = client.post("/api/create", json={"code": with_gs}).json()
    assert body2["element_string"] == body["element_string"]


if __name__ == "__main__":
    test_health()
    test_validate_ok()
    test_validate_errors()
    test_png_roundtrip_through_zxing()
    test_create_fields_match_code()
    test_create_errors_are_422()
    test_validate_accepts_missing_crypto_with_flag()
    test_svg_document()
    test_dashboard_served()
    test_raw_code_from_db()
    print("OK: все 10 тестов web-интерфейса прошли")
