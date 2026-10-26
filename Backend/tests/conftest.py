"""Payload sintético de dos municipios y dos meses, con cifras fáciles de verificar a mano."""

from array import array

import pytest

from app.services.payload_store import Payload


def hacer_payload(filas: list[tuple[int, int, int]]) -> Payload:
    """Cada fila es (municipio, mes, clase). Municipios: 0 Neiva, 1 Aipe. Meses: 0 2026-01, 1 2026-02."""
    cols = list(zip(*filas))
    n = len(filas)
    mu, mes, e = (array("h", cols[0]), array("b", cols[1]), array("b", cols[2]))
    ceros = lambda: array("h", [0] * n)  # noqa: E731
    return Payload(
        barrios=["Centro | Neiva", "Norte | Aipe"], munis=["Neiva", "Aipe"], zonas=["Centro", "Norte"],
        tecs=["0", "6044"], tec_invalido=[True, False], brigs=["NP · No pagó"],
        tipos=["AP · Alumbrado Público"], causas=["Suspension realizada", "Sin acceso"],
        subs=["PO · Ejecutada en poste"], tarifas=["Estrato 5", "Estrato 5 exento"],
        ciclos=["3 · CARRERAS CENTRO"], brigadas=["MOTO"], tipos_actividad=["Suspensión en poste / con moto"], actividades=["Suspension"],
        b_muni=[0, 1], b_zona=[0, 1], meses=["2026-01", "2026-02"],
        b=array("h", mu), mu=mu, zo=array("h", mu), t=array("h", [1] * n), g=ceros(), o=ceros(),
        c=array("h", [0 if x == 0 else 1 for x in e]), s=ceros(), f=ceros(), ci=ceros(), br=ceros(), ta=ceros(), ac=ceros(),
        e=e, mes=mes, m=array("i", [0] * n),
        fecha_min="2026-01-01", fecha_max="2026-02-28", generado="2026-03-01",
    )


@pytest.fixture
def payload() -> Payload:
    # Neiva: enero 8 órdenes (6 efectivas), febrero 10 (5 efectivas). Aipe: enero 20 (20 efectivas), febrero 20 (10).
    filas = (
        [(0, 0, 0)] * 6 + [(0, 0, 1)] * 2
        + [(0, 1, 0)] * 5 + [(0, 1, 1)] * 5
        + [(1, 0, 0)] * 20
        + [(1, 1, 0)] * 10 + [(1, 1, 1)] * 10
    )
    return hacer_payload(filas)
