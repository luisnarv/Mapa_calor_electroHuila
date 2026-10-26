"""La API arranca, carga el payload real y es coherente consigo misma.

Contra los JSON de `dashboard/public`, no contra cifras fijas: esos archivos se
reemplazan con cada corrida del ETL y una cifra fija se rompería sola.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.skipif(
    not (settings.DATA_DIR / "data.json").is_file(), reason="No hay payload en DATA_DIR"
)

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_resumen_es_coherente():
    r = client.get("/api/v1/resumen")
    assert r.status_code == 200
    d = r.json()
    assert d["ordenes"] == d["efectivas"] + d["fallidas"] > 0
    assert d["ef_pct"] == round(100 * d["efectivas"] / d["ordenes"], 2)
    assert d["meses"] == sorted(d["meses"])
