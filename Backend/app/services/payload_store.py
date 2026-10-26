"""Carga en memoria el payload del ETL, con las mismas reglas que aplica el tablero.

Es la misma fuente que lee el mapa (`dashboard/public/*.json`) y pasa por la misma
adaptación (`adaptar.py`), así que las cifras del chat no pueden discrepar de las
de la pantalla.

El payload viene en columnas de enteros: cada orden es una posición `i` en todos los
arrays y los valores son índices dentro de las listas de `dim`. Se conserva ese
formato —en vez de expandirlo a objetos— porque ~500k órdenes en arrays de enteros
ocupan pocos MB y se recorren en decenas de milisegundos.
"""

from __future__ import annotations

import json
import logging
from array import array
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.services.adaptar import Reglas, clasificar, construir_reglas, nombres_causas

logger = logging.getLogger(__name__)


class PayloadNoDisponible(Exception):
    """No se pudo cargar el payload del ETL."""


@dataclass(frozen=True, slots=True)
class Payload:
    """Las órdenes que cuentan para la efectividad, en columnas paralelas."""

    # Catálogos (índice -> nombre)
    barrios: list[str]  # "ZONA | MUNICIPIO"; el municipio es la unidad que muestra el mapa
    munis: list[str]
    zonas: list[str]
    tecs: list[str]
    tec_invalido: list[bool]  # códigos que no son una persona («0», «SIN DATO»)
    brigs: list[str]  # causal de suspensión
    tipos: list[str]  # clase de servicio
    causas: list[str]  # observación de la visita, sin código
    subs: list[str]  # lugar donde quedó la suspensión
    tarifas: list[str]  # estrato
    ciclos: list[str]
    brigadas: list[str]  # tipo de brigada ya homologado
    actividades: list[str]  # Suspension / Reconexion
    b_muni: list[int]  # barrio -> municipio
    b_zona: list[int]  # barrio -> zona
    meses: list[str]  # "YYYY-MM", del más antiguo al más reciente

    # Una posición por orden
    b: array
    mu: array  # municipio, derivado del barrio: es la unidad que muestra el mapa
    zo: array  # zona, derivada del barrio
    t: array
    g: array
    o: array
    c: array
    s: array
    f: array
    ci: array
    br: array
    ac: array
    e: array  # 0 efectiva, 1 fallida
    mes: array  # índice en `meses`
    m: array  # minutos desde fecha_min

    fecha_min: str
    fecha_max: str
    generado: str

    def __len__(self) -> int:
        return len(self.e)


_cache: dict[Path, Payload] = {}
_firmas: dict[Path, tuple] = {}
_lock = Lock()


def _firma_de(directorio: Path) -> tuple:
    """Huella de los archivos, para recargar cuando se copien JSON nuevos."""
    return tuple(
        (p.name, p.stat().st_mtime_ns, p.stat().st_size)
        for p in sorted(directorio.glob("data*.json"))
    )


def obtener(directorio: Path, doc_uc_campo: Path, doc_ni_con_observacion: Path) -> Payload:
    """Devuelve el payload cacheado, recargándolo si los archivos cambiaron."""
    try:
        firma = _firma_de(directorio) + _firma_de_docs(doc_uc_campo, doc_ni_con_observacion)
    except OSError as exc:
        raise PayloadNoDisponible(f"No se pudo leer {directorio}: {exc}") from exc

    with _lock:
        if directorio not in _cache or firma != _firmas.get(directorio):
            _cache[directorio] = _cargar(directorio, doc_uc_campo, doc_ni_con_observacion)
            _firmas[directorio] = firma
        return _cache[directorio]


def _firma_de_docs(*rutas: Path) -> tuple:
    return tuple((r.name, r.stat().st_mtime_ns, r.stat().st_size) for r in rutas)


def _leer_json(ruta: Path) -> dict | list:
    if not ruta.is_file():
        raise PayloadNoDisponible(f"Falta {ruta}. Copia ahí los JSON del ETL.")
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def _documentos(ruta: Path) -> frozenset[int]:
    return frozenset(int(d) for d in _leer_json(ruta))


def _cargar(directorio: Path, doc_uc_campo: Path, doc_ni_con_observacion: Path) -> Payload:
    raiz = _leer_json(directorio / "data.json")
    dim, meta = raiz["dim"], raiz["meta"]
    reglas = construir_reglas(dim, _documentos(doc_uc_campo), _documentos(doc_ni_con_observacion))

    columnas = {
        "b": array("h"), "t": array("h"), "g": array("h"), "o": array("h"),
        "c": array("h"), "s": array("h"), "f": array("h"), "ci": array("h"),
        "br": array("h"), "ac": array("h"),
        "mu": array("h"), "zo": array("h"),
        "e": array("b"), "mes": array("b"),
        "m": array("i"),
    }
    # `br` es la brigada ya homologada; el resto se copia tal cual del payload.
    copiadas = ("b", "t", "g", "o", "c", "s", "f", "ci", "ac", "m")

    manifiesto = sorted(meta.get("months", []), key=lambda x: x["key"])
    if not manifiesto:
        raise PayloadNoDisponible("El payload no trae manifiesto de meses.")

    meses: list[str] = []
    for i, mes in enumerate(manifiesto):
        pts = raiz["pts"] if mes.get("recent") else _leer_json(directorio / mes["file"])["pts"]
        if len(pts["e"]) != mes["n"]:
            logger.warning("El mes %s declara %s órdenes y trae %s.", mes["key"], mes["n"], len(pts["e"]))
        keep, clase, brigada = clasificar(pts, reglas)
        meses.append(mes["key"])
        for clave in copiadas:
            col = pts.get(clave)
            columnas[clave].extend([col[j] for j in keep] if col is not None else [0] * len(keep))
        columnas["br"].extend(brigada)
        columnas["mu"].extend(dim["b_muni"][pts["b"][j]] for j in keep)
        columnas["zo"].extend(dim["b_zona"][pts["b"][j]] for j in keep)
        columnas["e"].extend(clase)
        columnas["mes"].extend([i] * len(keep))

    payload = Payload(
        barrios=dim["barrios"],
        munis=dim["munis"],
        zonas=dim["zonas"],
        tecs=dim["tecs"],
        tec_invalido=[
            t.strip().lower() in ("", "0", "na", "n/a", "sin dato")
            for t in map(str, dim.get("tecCodigos") or dim["tecs"])
        ],
        brigs=dim["brigs"],
        tipos=dim["tipos"],
        causas=nombres_causas(dim["causas"]),
        subs=dim["subs"],
        tarifas=dim["tarifas"],
        ciclos=dim["ciclos"],
        brigadas=reglas.brigadas,
        actividades=dim["actividades"],
        b_muni=dim["b_muni"],
        b_zona=dim["b_zona"],
        meses=meses,
        fecha_min=meta.get("fecha_min", ""),
        fecha_max=meta.get("fecha_max", ""),
        generado=meta.get("generated", ""),
        **columnas,
    )
    logger.info(
        "Payload cargado: %s órdenes que cuentan (de %s en el ETL), %s meses, generado el %s.",
        f"{len(payload):,}", f"{meta.get('total_all', 0):,}", len(meses), payload.generado,
    )
    return payload
