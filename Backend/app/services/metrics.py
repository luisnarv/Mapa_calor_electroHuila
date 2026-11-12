"""Métricas del tablero sobre el payload ya adaptado.

Solo hay dos clases de orden: efectiva (0) y fallida (1). La efectividad es
`efectivas / total de órdenes`, la misma que muestra el mapa; no existe una
ajustada ni «perdidas» en ElectroHuila.

Todo recorre el payload una vez y acumula por grupo, igual que el tablero: no hay
un segundo camino de cálculo que pueda discrepar del mapa.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
import statistics
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
    "tipo_actividad": ("tipos_actividad", "ta"),
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


# Un filtro es un nombre, o varios (los técnicos elegidos a la vez en el tablero).
Filtro = str | Sequence[str] | None


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
    # «ciclo 3» o «3»: se busca por el código que antecede a « · », no por contenido, porque
    # «3» está contenido en «13», «23» y «30» y el usuario quería uno solo.
    buscado = re.sub(r"^ciclo ", "", norm(valor))
    normales = [norm(c) for c in catalogo]
    por_codigo = [i for i, c in enumerate(catalogo) if " · " in c and norm(c.split(" · ")[0]) == buscado]
    if len(por_codigo) == 1:
        return por_codigo[0]
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


def _resolver_filtros(p: Payload, filtros: Mapping[str, Filtro]) -> dict[str, tuple[int, ...]]:
    """Cada filtro a los índices de su catálogo. Una lista (varios técnicos elegidos) suma todos."""
    resueltos: dict[str, tuple[int, ...]] = {}
    for campo, valor in filtros.items():
        if valor in (None, "", [], ()):
            continue
        if campo not in DIMENSIONES:
            raise KeyError(campo)
        catalogo = getattr(p, DIMENSIONES[campo][0])
        pedidos = [valor] if isinstance(valor, str) else list(valor)
        resueltos[campo] = tuple(dict.fromkeys(resolver(catalogo, v, campo) for v in pedidos))
    return resueltos


def agrupar(
    p: Payload,
    filtros: Mapping[str, Filtro],
    meses: Sequence[int],
    por: str | None = None,
) -> dict[int | None, Conteo]:
    """Cuenta las órdenes del recorte, en un solo grupo (`None`) o una por valor de `por`."""
    checks = [(getattr(p, DIMENSIONES[c][1]), frozenset(v)) for c, v in _resolver_filtros(p, filtros).items()]
    # `por='mes'` agrupa por mes (índice en `p.meses`), que no es una dimensión de filtro.
    if por == "dia":  # `p.m` son minutos desde `fecha_min`
        col_por = [v // 1440 for v in p.m]
    else:
        col_por = (p.mes if por == "mes" else getattr(p, DIMENSIONES[por][1])) if por else None
    en_meses = set(meses)
    todos = len(en_meses) == len(p.meses)
    mes, e = p.mes, p.e

    grupos: dict[int | None, Conteo] = {}
    for i in range(len(e)):
        if not todos and mes[i] not in en_meses:
            continue
        if any(col[i] not in v for col, v in checks):
            continue
        g = grupos.setdefault(col_por[i] if col_por is not None else None, Conteo())
        g.tot += 1
        if e[i] == 0:
            g.ef += 1
    return grupos


def _fila(nombre: str, c: Conteo) -> dict[str, Any]:
    return {"nombre": nombre, "ordenes": c.tot, "efectivas": c.ef, "fallidas": c.fa, "ef_pct": _pct(c.ef, c.tot)}


def nombres_filtros(p: Payload, filtros: Mapping[str, Filtro]) -> dict[str, Any]:
    """Los filtros ya resueltos, con el nombre exacto del catálogo (lista si se pidió una lista)."""
    nombres: dict[str, Any] = {}
    for c, idx in _resolver_filtros(p, filtros).items():
        cat = getattr(p, DIMENSIONES[c][0])
        nombres[c] = [cat[i] for i in idx] if isinstance(filtros[c], (list, tuple)) else cat[idx[0]]
    return nombres


# Las órdenes fallidas casi nunca llegan a tener un tipo de brigada: quedan en «CUALQUIERA». Por eso moto y
# camioneta salen cerca del 100 % y comparar solo esas dos engaña. El modelo lo omitía aunque el prompt lo decía.
AVISO_BRIGADA = (
    "Las órdenes fallidas casi siempre quedan con brigada «CUALQUIERA» (no llegaron a tener una asignada), así que la "
    "efectividad de moto y camioneta sale cerca del 100 % y comparar solo esas dos engaña. Consulta también CUALQUIERA "
    "(`ranking` por brigada) y dilo al citar la comparación."
)


# Preguntas de asignación («¿a qué municipio mando más brigadas?») se contestaban con el volumen y un «se enviaron».
NOTA_VOLUMEN = (
    "Ordenar por volumen NO decide dónde mandar brigadas ni qué priorizar. Si la pregunta es de asignación o prioridad, "
    "responde con las fallidas (impacto), el % de fallidas y la efectividad (haz otro `ranking` con ordenar_por='fallidas'), "
    "empieza con «Mi criterio:» y di que es un criterio y no un dato. No escribas «se enviaron»."
)


def _aviso_parcial(p: Payload, meses: Sequence[int]) -> str | None:
    """Aviso si el recorte incluye el mes en curso y los datos no llegan a su último día.

    Sin esto el modelo daba por completo un mes que termina en la fecha de corte, y comparaba su
    volumen con el de meses enteros como si el volumen hubiera caído.
    """
    if not p.fecha_max or not p.meses or (len(p.meses) - 1) not in meses:
        return None
    anio, mes, dia = (int(x) for x in p.fecha_max.split("-"))
    if p.meses[-1] != f"{anio:04d}-{mes:02d}" or dia >= calendar.monthrange(anio, mes)[1]:
        return None
    return (
        f"{p.meses[-1]} está INCOMPLETO: los datos llegan solo hasta el {p.fecha_max}. "
        "No compares su volumen de órdenes con meses completos, y dilo al citarlo."
    )


def _base(p: Payload, filtros: Mapping[str, Filtro], etiqueta: str, meses: Sequence[int] = ()) -> dict[str, Any]:
    """El recorte exacto sobre el que se calculó, para que quien responda lo cite."""
    nombres = nombres_filtros(p, filtros)
    base: dict[str, Any] = {"periodo": etiqueta, "filtros": nombres, "datos_hasta": p.fecha_max}
    aviso = _aviso_parcial(p, meses)
    if aviso:
        base["aviso"] = aviso
    if "brigada" in nombres:
        base["aviso_brigada"] = AVISO_BRIGADA
    return base


def efectividad(p: Payload, filtros: Mapping[str, Filtro], mes: str | Sequence[str] | None = None) -> dict[str, Any]:
    meses, etiqueta = resolver_meses(p, mes)
    c = agrupar(p, filtros, meses).get(None, Conteo())
    return {**_fila("total", c), "base": _base(p, filtros, etiqueta, meses)}


# Sin «perdidas» ni ajustada: en ElectroHuila no existen.
CRITERIOS = ("ef_pct", "ef_pond", "fallidas", "pct_fallidas", "volumen", "efectivas")


def ranking(
    p: Payload,
    dimension: str,
    filtros: Mapping[str, Filtro],
    mes: str | Sequence[str] | None = None,
    ordenar_por: str = "ef_pond",
    extremo: str = "mayor",
    min_ordenes: int = 10,
    limite: int = 10,
) -> dict[str, Any]:
    if dimension not in DIMENSIONES:
        raise KeyError(dimension)
    if ordenar_por not in CRITERIOS:
        raise KeyError(ordenar_por)
    if extremo not in ("mayor", "menor"):
        raise KeyError(extremo)
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
    # `extremo` dice qué valores van primero del criterio elegido, sin interpretar «peor»: con
    # `peores` según el criterio (menos efectividad, pero MÁS fallidas) el modelo lo usaba al revés
    # y «los ciclos más problemáticos» salían con 0 fallidas.
    filas.sort(key=lambda f: (f[clave], f["ordenes"]), reverse=(extremo == "mayor"))

    return {
        "dimension": dimension,
        "ordenado_por": ordenar_por,
        "extremo": extremo,
        **({"aviso_brigada": AVISO_BRIGADA} if dimension == "brigada" else {}),
        **({"nota_uso": NOTA_VOLUMEN} if ordenar_por == "volumen" else {}),
        "filas": filas[:limite],
        "grupos_con_muestra": len(filas),
        "base": {**_base(p, filtros, etiqueta, meses), "min_ordenes": min_ordenes},
    }


def serie_mensual(p: Payload, filtros: Mapping[str, Filtro], min_ordenes: int = 30) -> dict[str, Any]:
    meses, etiqueta = resolver_meses(p, None)
    por_mes = agrupar(p, filtros, meses, por="mes")
    serie = [{**_fila(p.meses[m], c), "mes": p.meses[m]} for m, c in sorted(por_mes.items()) if c.tot]
    out: dict[str, Any] = {"serie": serie}
    # El mejor y el peor mes ya calculados: el modelo elegía mal el máximo de la lista (dio marzo de 2026 como
    # el mejor cuando era enero de 2025). Solo cuentan meses con muestra mínima.
    con_muestra = [f for f in serie if f["ordenes"] >= min_ordenes]
    if con_muestra:
        out["mejor_mes"] = max(con_muestra, key=lambda f: (f["ef_pct"], f["ordenes"]))
        out["peor_mes"] = min(con_muestra, key=lambda f: (f["ef_pct"], -f["ordenes"]))
    out["base"] = _base(p, filtros, etiqueta, meses)
    return out


def comparar_periodos(
    p: Payload,
    mes_a: str | Sequence[str],
    mes_b: str | Sequence[str],
    filtros: Mapping[str, Filtro],
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
        "base": {**_base(p, filtros, f"{et_a} vs {et_b}", [*idx_a, *idx_b]), "min_ordenes": min_ordenes},
    }


def valores_de(
    p: Payload, dimension: str, texto: str | None = None, limite: int = 60, filtros: Mapping[str, Filtro] | None = None
) -> dict[str, Any]:
    """Los nombres que existen en un catálogo, para que se pueda filtrar con uno exacto.

    Con `filtros` solo salen los que tienen órdenes bajo ellos: los municipios de una zona, la zona
    de un municipio, los ciclos de Neiva. Sin esto el modelo respondía de memoria dónde queda cada
    municipio, y se equivocaba.
    """
    if dimension not in DIMENSIONES:
        raise KeyError(dimension)
    catalogo = getattr(p, DIMENSIONES[dimension][0])
    buscado = norm(texto) if texto else ""
    pedidos = {c: v for c, v in (filtros or {}).items() if c != dimension and v not in (None, "", [], ())}
    if not pedidos:
        valores = [c for c in catalogo if not buscado or buscado in norm(c)]
        return {"dimension": dimension, "total": len(valores), "valores": valores[:limite]}
    meses, _ = resolver_meses(p, None)
    grupos = agrupar(p, pedidos, meses, por=dimension)
    filas = sorted(
        ((catalogo[i], c.tot) for i, c in grupos.items() if not buscado or buscado in norm(catalogo[i])),
        key=lambda f: -f[1],
    )
    return {
        "dimension": dimension,
        "total": len(filas),
        "valores": [n for n, _ in filas[:limite]],
        "ordenes_por_valor": {n: o for n, o in filas[:limite]},
        "filtros": nombres_filtros(p, pedidos),
        "nota": "Solo valores con órdenes bajo esos filtros, en todo el histórico.",
    }


DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def por_dia(
    p: Payload,
    filtros: Mapping[str, Filtro],
    mes: str | Sequence[str] | None = None,
    ordenar_por: str = "ordenes",
    extremo: str = "mayor",
    limite: int = 10,
    fecha: str | None = None,
) -> dict[str, Any]:
    """Los días con más (o menos) órdenes o fallidas de un recorte: «¿qué día se hicieron más órdenes?».

    Con `fecha` («2026-09-14») devuelve solo ese día: la cifra de un día que no está entre los de arriba.

    Antes el chat respondía que «los datos solo están por mes», y es falso: cada orden trae su fecha.
    """
    if ordenar_por not in ("ordenes", "fallidas", "efectivas"):
        raise KeyError(ordenar_por)
    if extremo not in ("mayor", "menor"):
        raise KeyError(extremo)
    if fecha:
        try:
            date.fromisoformat(fecha)
        except ValueError as exc:
            raise KeyError(f"fecha={fecha!r} (usa YYYY-MM-DD)") from exc
        mes = mes or fecha[:7]
    meses, etiqueta = resolver_meses(p, mes)
    inicio = date.fromisoformat(p.fecha_min)
    filas = []
    for d, c in agrupar(p, filtros, meses, por="dia").items():
        dia = inicio + timedelta(days=d)
        filas.append({**_fila(dia.isoformat(), c), "fecha": dia.isoformat(), "dia_semana": DIAS_SEMANA[dia.weekday()]})
    clave = {"ordenes": "ordenes", "fallidas": "fallidas", "efectivas": "efectivas"}[ordenar_por]
    if fecha:
        filas = [f for f in filas if f["fecha"] == fecha]
        if not filas:
            return {"fecha": fecha, "filas": [], "nota": "Ese día no tiene órdenes en el recorte (o está fuera de los datos).",
                    "base": _base(p, filtros, etiqueta, meses)}
    filas.sort(key=lambda f: (f[clave], f["fecha"]), reverse=(extremo == "mayor"))
    return {
        "ordenado_por": ordenar_por,
        "extremo": extremo,
        "dias_con_datos": len(filas),
        "filas": filas[:limite],
        "base": _base(p, filtros, etiqueta, meses),
    }


def resumen(p: Payload, filtros: Mapping[str, Filtro], mes: str | Sequence[str] | None = None) -> dict[str, Any]:
    """Cuentas que el modelo hacía de cabeza y erraba: promedios por mes y por técnico, y cuántos hay.

    Un técnico es una persona: los códigos «0» o «SIN DATO» no cuentan. El promedio por técnico es
    sobre los que tuvieron órdenes en el recorte, no sobre los 125 del catálogo histórico.
    """
    meses, etiqueta = resolver_meses(p, mes)
    total = agrupar(p, filtros, meses).get(None, Conteo())
    por_mes = {m: c for m, c in agrupar(p, filtros, meses, por="mes").items() if c.tot}
    cargas = sorted(c.tot for t, c in agrupar(p, filtros, meses, por="tecnico").items() if not p.tec_invalido[t])
    n_meses = len(por_mes)
    out: dict[str, Any] = {
        **_fila("total", total),
        "meses_con_datos": n_meses,
        "promedio_ordenes_por_mes": round(total.tot / n_meses, 1) if n_meses else 0.0,
        "promedio_fallidas_por_mes": round(total.fa / n_meses, 1) if n_meses else 0.0,
        "tecnicos_con_ordenes": len(cargas),
        "municipios_con_ordenes": len(agrupar(p, filtros, meses, por="municipio")),
        "ciclos_con_ordenes": len(agrupar(p, filtros, meses, por="ciclo")),
    }
    if cargas:
        out["ordenes_por_tecnico"] = {
            "promedio": round(sum(cargas) / len(cargas), 1),
            "mediana": statistics.median(cargas),
            "maximo": cargas[-1],
            "minimo": cargas[0],
        }
    out["base"] = _base(p, filtros, etiqueta, meses)
    return out
