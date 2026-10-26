"""Métricas del tablero sobre el payload ya adaptado.

Solo hay dos clases de orden: efectiva (0) y fallida (1). La efectividad es
`efectivas / total de órdenes`, la misma que muestra el mapa; no existe una
ajustada ni «perdidas» en ElectroHuila.

Todo recorre el payload una vez y acumula por grupo, igual que el tablero: no hay
un segundo camino de cálculo que pueda discrepar del mapa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.payload_store import Payload

# nombre del filtro -> (catálogo del Payload, columna del Payload)
DIMENSIONES: dict[str, tuple[str, str]] = {
    "municipio": ("munis", "mu"),
    "zona": ("zonas", "zo"),
    "ciclo": ("ciclos", "ci"),
    "tecnico": ("tecs", "t"),
    "brigada": ("brigadas", "br"),
    "causal": ("brigs", "g"),
    "clase_servicio": ("tipos", "o"),
    "estrato": ("tarifas", "f"),
    "actividad": ("actividades", "ac"),
    "causa": ("causas", "c"),
    "subaccion": ("subs", "s"),
}

# Órdenes «prestadas» de la media que se le suman a cada grupo al ponderar. Con 50,
# un municipio de 10 órdenes queda dominado por ellas y uno de 400 apenas se mueve:
# justo lo buscado, exigir muestra para creerle a un porcentaje.
PESO_PREVIO = 50


class FiltroNoResuelto(Exception):
    """Un filtro de catálogo no resolvió a un único valor: no existe o encaja en varios.

    Devolver el total sin filtrar —o vaciar el cálculo— haría que el modelo
    responda con una cifra que no es la pedida sin que nadie lo note.
    """

    def __init__(self, campo: str, valor: str, candidatos: Sequence[str]) -> None:
        super().__init__(f"{campo}={valor!r} no resuelve a un único valor")
        self.campo = campo
        self.valor = valor
        self.candidatos = list(candidatos)


class PeriodoNoResuelto(Exception):
    def __init__(self, valor: str, disponibles: Sequence[str]) -> None:
        super().__init__(f"No hay datos para el periodo {valor!r}")
        self.valor = valor
        self.disponibles = list(disponibles)


def norm(texto: Any) -> str:
    """Minúsculas, sin tildes ni signos, espacios colapsados: para comparar nombres."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def resolver(catalogo: Sequence[str], valor: str, campo: str) -> int:
    """Índice del único valor del catálogo que corresponde a `valor`.

    Primero coincidencia exacta; si no, por contenido. Dos que encajan por contenido
    («estrato 5» y «estrato 5 exento») no se resuelven: se pregunta cuál.
    """
    buscado = norm(valor)
    normales = [norm(c) for c in catalogo]
    exactos = [i for i, c in enumerate(normales) if c == buscado]
    if len(exactos) == 1:
        return exactos[0]
    parciales = exactos or [i for i, c in enumerate(normales) if buscado and buscado in c]
    if len(parciales) == 1:
        return parciales[0]
    raise FiltroNoResuelto(campo, valor, [catalogo[i] for i in parciales[:15]])


def resolver_meses(p: Payload, mes: str | Sequence[str] | None) -> tuple[list[int], str]:
    """Índices de mes y una etiqueta legible. Sin dato (o «todo») son todos los meses."""
    if mes is None or mes == "todo":
        return list(range(len(p.meses))), f"{p.meses[0]} a {p.meses[-1]}"
    pedidos = [mes] if isinstance(mes, str) else list(mes)
    idx: list[int] = []
    for pedido in pedidos:
        # «2026» vale por todos sus meses con datos; «2026-07» por uno.
        encontrados = [i for i, m in enumerate(p.meses) if m == pedido or (len(pedido) == 4 and m.startswith(pedido))]
        if not encontrados:
            raise PeriodoNoResuelto(pedido, p.meses)
        idx.extend(i for i in encontrados if i not in idx)
    idx.sort()
    contiguos = idx == list(range(idx[0], idx[-1] + 1))
    if len(idx) > 2 and contiguos:
        return idx, f"{p.meses[idx[0]]} a {p.meses[idx[-1]]}"
    return idx, ", ".join(p.meses[i] for i in idx)


@dataclass(slots=True)
class Conteo:
    tot: int = 0
    ef: int = 0

    @property
    def fa(self) -> int:
        return self.tot - self.ef


def _pct(x: int, y: int) -> float:
    return round(x / y * 100, 1) if y else 0.0


def _ponderada(ef: int, tot: int, media: float) -> float:
    """Acerca el porcentaje a la media según la muestra, para que «el mejor» no sea
    un municipio de diez órdenes que salieron todas bien."""
    return round((ef + PESO_PREVIO * media) / (tot + PESO_PREVIO) * 100, 1)


def _resolver_filtros(p: Payload, filtros: Mapping[str, str | None]) -> dict[str, int]:
    resueltos: dict[str, int] = {}
    for campo, valor in filtros.items():
        if valor in (None, ""):
            continue
        if campo not in DIMENSIONES:
            raise KeyError(campo)
        resueltos[campo] = resolver(getattr(p, DIMENSIONES[campo][0]), valor, campo)
    return resueltos


def agrupar(
    p: Payload,
    filtros: Mapping[str, str | None],
    meses: Sequence[int],
    por: str | None = None,
) -> dict[int | None, Conteo]:
    """Cuenta las órdenes del recorte, en un solo grupo (`None`) o una por valor de `por`."""
    checks = [(getattr(p, DIMENSIONES[c][1]), v) for c, v in _resolver_filtros(p, filtros).items()]
    col_por = getattr(p, DIMENSIONES[por][1]) if por else None
    en_meses = set(meses)
    todos = len(en_meses) == len(p.meses)
    mes, e = p.mes, p.e

    grupos: dict[int | None, Conteo] = {}
    for i in range(len(e)):
        if not todos and mes[i] not in en_meses:
            continue
        if any(col[i] != v for col, v in checks):
            continue
        g = grupos.setdefault(col_por[i] if col_por is not None else None, Conteo())
        g.tot += 1
        if e[i] == 0:
            g.ef += 1
    return grupos


def _fila(nombre: str, c: Conteo) -> dict[str, Any]:
    return {"nombre": nombre, "ordenes": c.tot, "efectivas": c.ef, "fallidas": c.fa, "ef_pct": _pct(c.ef, c.tot)}


def _base(p: Payload, filtros: Mapping[str, str | None], etiqueta: str) -> dict[str, Any]:
    """El recorte exacto sobre el que se calculó, para que quien responda lo cite."""
    nombres = {
        c: getattr(p, DIMENSIONES[c][0])[i] for c, i in _resolver_filtros(p, filtros).items()
    }
    return {"periodo": etiqueta, "filtros": nombres}


def efectividad(p: Payload, filtros: Mapping[str, str | None], mes: str | Sequence[str] | None = None) -> dict[str, Any]:
    meses, etiqueta = resolver_meses(p, mes)
    c = agrupar(p, filtros, meses).get(None, Conteo())
    return {**_fila("total", c), "base": _base(p, filtros, etiqueta)}


# Sin «perdidas» ni ajustada: en ElectroHuila no existen.
CRITERIOS = ("ef_pct", "ef_pond", "fallidas", "pct_fallidas", "volumen", "efectivas")


def ranking(
    p: Payload,
    dimension: str,
    filtros: Mapping[str, str | None],
    mes: str | Sequence[str] | None = None,
    ordenar_por: str = "ef_pond",
    peores: bool = False,
    min_ordenes: int = 10,
    limite: int = 10,
) -> dict[str, Any]:
    if dimension not in DIMENSIONES:
        raise KeyError(dimension)
    if ordenar_por not in CRITERIOS:
        raise KeyError(ordenar_por)
    meses, etiqueta = resolver_meses(p, mes)
    grupos = agrupar(p, filtros, meses, por=dimension)
    total_fa = sum(g.fa for g in grupos.values())
    tot_ef = sum(g.ef for g in grupos.values())
    tot = sum(g.tot for g in grupos.values())
    media = tot_ef / tot if tot else 0.0

    catalogo = getattr(p, DIMENSIONES[dimension][0])
    invalido = p.tec_invalido if dimension == "tecnico" else None
    filas = []
    for idx, c in grupos.items():
        # «0» o «SIN DATO» no son una persona: no se pueden recomendar ni reprochar.
        if c.tot < min_ordenes or (invalido and invalido[idx]):
            continue
        # `puntaje_orden` no es la efectividad: es un puntaje para ordenar, y con otro nombre
        # el modelo lo citaba como si lo fuera (85,2 % en vez del 84,4 % que muestra el mapa).
        fila = _fila(catalogo[idx], c)
        fila["puntaje_orden"] = _ponderada(c.ef, c.tot, media)
        fila["pct_fallidas"] = _pct(c.fa, c.tot)
        fila["pct_de_las_fallidas"] = _pct(c.fa, total_fa)
        filas.append(fila)

    clave = {
        "ef_pct": "ef_pct", "ef_pond": "puntaje_orden", "fallidas": "fallidas",
        "pct_fallidas": "pct_fallidas", "volumen": "ordenes", "efectivas": "efectivas",
    }[ordenar_por]
    # `peores` invierte el extremo: quien tiene menos efectividad, menos fallidas, menos volumen.
    mayor_primero = not peores
    filas.sort(key=lambda f: (f[clave], f["ordenes"]), reverse=mayor_primero)

    return {
        "dimension": dimension,
        "ordenado_por": ordenar_por,
        "filas": filas[:limite],
        "grupos_con_muestra": len(filas),
        "base": {**_base(p, filtros, etiqueta), "min_ordenes": min_ordenes},
    }


def serie_mensual(p: Payload, filtros: Mapping[str, str | None]) -> dict[str, Any]:
    meses, etiqueta = resolver_meses(p, None)
    por_mes = {m: Conteo() for m in meses}
    for m in meses:
        por_mes[m] = agrupar(p, filtros, [m]).get(None, Conteo())
    return {
        "serie": [{**_fila(p.meses[m], c), "mes": p.meses[m]} for m, c in por_mes.items() if c.tot],
        "base": _base(p, filtros, etiqueta),
    }


def comparar_periodos(
    p: Payload,
    mes_a: str | Sequence[str],
    mes_b: str | Sequence[str],
    filtros: Mapping[str, str | None],
    dimension: str | None = None,
    min_ordenes: int = 10,
    limite: int = 10,
) -> dict[str, Any]:
    """Cambio en puntos porcentuales de B respecto a A, en total o por grupo."""
    idx_a, et_a = resolver_meses(p, mes_a)
    idx_b, et_b = resolver_meses(p, mes_b)
    a = agrupar(p, filtros, idx_a, por=dimension)
    b = agrupar(p, filtros, idx_b, por=dimension)
    catalogo = getattr(p, DIMENSIONES[dimension][0]) if dimension else None
    filas = []
    for k in a.keys() & b.keys():
        ca, cb = a[k], b[k]
        if ca.tot < min_ordenes or cb.tot < min_ordenes:
            continue
        pa, pb = _pct(ca.ef, ca.tot), _pct(cb.ef, cb.tot)
        filas.append({
            "nombre": catalogo[k] if catalogo else "total",
            "ordenes_a": ca.tot, "ordenes_b": cb.tot,
            "ef_pct_a": pa, "ef_pct_b": pb, "cambio_pp": round(pb - pa, 1),
        })
    filas.sort(key=lambda f: f["cambio_pp"])  # primero lo que más empeoró
    return {
        "periodo_a": et_a, "periodo_b": et_b, "filas": filas[:limite],
        "base": {**_base(p, filtros, f"{et_a} vs {et_b}"), "min_ordenes": min_ordenes},
    }


def valores_de(p: Payload, dimension: str, texto: str | None = None, limite: int = 60) -> dict[str, Any]:
    """Los nombres que existen en un catálogo, para que se pueda filtrar con uno exacto."""
    if dimension not in DIMENSIONES:
        raise KeyError(dimension)
    catalogo = getattr(p, DIMENSIONES[dimension][0])
    buscado = norm(texto) if texto else ""
    valores = [c for c in catalogo if not buscado or buscado in norm(c)]
    return {"dimension": dimension, "total": len(valores), "valores": valores[:limite]}
