"""Reglas que el tablero aplica al payload del ETL, replicadas en Python.

Es la traducción de `dashboard/src/lib/adaptar.js`. Si cambia una regla allá hay
que cambiarla aquí: el chat y el mapa deben contar exactamente las mismas órdenes
(un solo cálculo leído dos veces, no dos cálculos).

Cada orden queda en una de dos clases: 0 efectiva, 1 fallida. Lo que el diccionario
clasifica como «no aplica» ni se ejecutó ni falló, así que no entra a ningún total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# La observación dice que la suspensión SÍ se hizo, aunque la base marque FALLIDA.
# Negocio decidió que prima la observación. Quedan fuera a propósito «EE/EN»
# (reconexión), «NI» (sin descripción) y «Se encontró suspendido» (no la hizo la cuadrilla).
CODIGOS_SUSPENDIDO = frozenset({"SY", "SN", "MD", "SM", "ES", "MR", "SO"})

# Nunca se asignaron a una brigada: UC es la baja por pago automática (WEB SERVICE) y
# NI sin texto en Observaciones no dice qué se hizo. Las excepciones (UC con canal CAMPO,
# NI con observación) llegan como conjuntos de documentos.
CODIGOS_EXCLUIDOS = frozenset({"UC"})
CODIGOS_EXCLUIDOS_SIN_OBSERVACION = frozenset({"NI"})

_SIGLAS = frozenset({"AMI"})
_BRIGADA_POR_LUGAR = {"NM": "MOTO", "NC": "CAMIONETA", "ND": "MOTO - DOBLE MOTO"}


def separar_causa(bruta: Any) -> tuple[str, str]:
    """«EP · PERSUASION ESPECIAL» -> («EP», «PERSUASION ESPECIAL»). Sin « · » no hay descripción."""
    txt = str(bruta if bruta is not None else "").strip()
    i = txt.find(" · ")
    if i < 0:
        return txt, ""
    return txt[:i], txt[i + 3:].strip()


def _bajar(texto: str) -> str:
    """Pasa a minúsculas las palabras que vienen enteras en mayúsculas (salvo siglas)."""
    partes = re.split(r"(\s+)", texto)
    s = "".join(
        w.lower() if len(w) > 1 and w == w.upper() and w != w.lower() and w not in _SIGLAS else w
        for w in partes
    )
    return s[:1].upper() + s[1:]


def nombre_causa(bruta: Any) -> tuple[str, str]:
    """(nombre legible, código). Un código corto sin descripción («NI», «00») se dice tal cual."""
    codigo, desc = separar_causa(bruta)
    if not desc:
        if re.fullmatch(r"[A-Z0-9]{1,3}", codigo, re.IGNORECASE):
            return f"Sin descripción en el diccionario ({codigo})", codigo
        return _bajar(codigo), codigo
    return _bajar(desc), codigo


def nombres_causas(brutas: Sequence[Any]) -> list[str]:
    """Nombres sin código; si dos quedan iguales se desambigua con su código."""
    limpias = [nombre_causa(b) for b in brutas]
    veces: dict[str, int] = {}
    for nombre, _ in limpias:
        veces[nombre] = veces.get(nombre, 0) + 1
    return [f"{n} ({c})" if veces[n] > 1 else n for n, c in limpias]


def accion_de_lugar(lugar: Any) -> str:
    """Qué se hizo, según el lugar técnico donde quedó la orden: «Suspensión en gabinete»."""
    t = str(lugar if lugar is not None else "")
    m = re.search(r"ejecutada en (.+)$", t, re.IGNORECASE)
    if m:
        return f"Suspensión en {m.group(1).strip().lower()}"
    if re.search(r"caso aislado", t, re.IGNORECASE):
        return "Suspensión (caso aislado)"
    if re.search(r"no se pudo ejecutar", t, re.IGNORECASE):
        return "Suspensión no ejecutada (se visitó)"
    if re.search(r"no se intent", t, re.IGNORECASE):
        return "Suspensión no intentada"
    return "Suspensión (lugar sin descripción)"


def frase_brigada(nombre: str) -> str:
    n = str(nombre).upper()
    if n == "MOTO":
        return "con moto"
    if n == "CAMIONETA":
        return "con camioneta"
    if n == "MOTO - DOBLE MOTO":
        return "con moto o doble moto"
    if n.startswith("PERSONAL DE PSS"):
        return "con persuasión especial"
    if n == "CUALQUIERA":
        return "sin brigada específica"
    return "sin brigada asignada"  # SIN DATO, NA


def _unir_doble_moto(nombre: str) -> str:
    return "MOTO - DOBLE MOTO" if nombre == "DOBLE MOTO" else nombre


def homologar_brigadas(brigadas: Sequence[str]) -> tuple[list[str], list[int]]:
    """Une «DOBLE MOTO» con «MOTO - DOBLE MOTO». Devuelve (catálogo nuevo, índice viejo -> nuevo)."""
    nuevo = list(dict.fromkeys(_unir_doble_moto(n) for n in brigadas))
    return nuevo, [nuevo.index(_unir_doble_moto(n)) for n in brigadas]


@dataclass(frozen=True, slots=True)
class Reglas:
    """Lo derivable del catálogo, calculado una vez para recorrer cada mes."""

    numerador: list[int]
    denominador: list[int]
    suspendida: list[bool]  # por causa
    excluida: list[bool]
    excluida_sin_observacion: list[bool]
    brigadas: list[str]
    brigada_de: list[int]  # índice del catálogo crudo -> homologado
    na: int  # índice de «NA» en `brigadas`, -1 si no existe
    brigada_por_sub: list[int]  # subacción -> brigada que dice su lugar técnico, -1 si no dice
    accion_de_sub: list[int]  # subacción -> índice de la acción que describe
    tipos_actividad: list[str]  # «acción / con moto»: el filtro «Tipo de actividad» del mapa
    docs_uc_campo: frozenset[int]
    docs_ni_con_observacion: frozenset[int]


def construir_reglas(
    dim: Mapping[str, Any],
    docs_uc_campo: frozenset[int],
    docs_ni_con_observacion: frozenset[int],
) -> Reglas:
    codigos = [separar_causa(c)[0] for c in dim.get("causas", [])]
    brigadas, brigada_de = homologar_brigadas(dim.get("brigadas", []))
    brigada_por_sub: list[int] = []
    for sub in dim.get("subs", []):
        destino = _BRIGADA_POR_LUGAR.get(str(sub)[:2])
        brigada_por_sub.append(brigadas.index(destino) if destino in brigadas else -1)
    # Tipo de actividad = qué se hizo + con qué brigada. El índice es `acción × n_brigadas + brigada`.
    acciones: list[str] = []
    accion_de_sub: list[int] = []
    for sub in dim.get("subs", []):
        a = accion_de_lugar(sub)
        if a not in acciones:
            acciones.append(a)
        accion_de_sub.append(acciones.index(a))
    return Reglas(
        numerador=list(dim.get("grupoNumerador", [])),
        denominador=list(dim.get("grupoDenominador", [])),
        suspendida=[c in CODIGOS_SUSPENDIDO for c in codigos],
        excluida=[c in CODIGOS_EXCLUIDOS for c in codigos],
        excluida_sin_observacion=[c in CODIGOS_EXCLUIDOS_SIN_OBSERVACION for c in codigos],
        brigadas=brigadas,
        brigada_de=brigada_de,
        na=brigadas.index("NA") if "NA" in brigadas else -1,
        brigada_por_sub=brigada_por_sub,
        accion_de_sub=accion_de_sub,
        tipos_actividad=[f"{a} / {frase_brigada(b)}" for a in acciones for b in brigadas],
        docs_uc_campo=docs_uc_campo,
        docs_ni_con_observacion=docs_ni_con_observacion,
    )


def clasificar(
    pts: Mapping[str, Sequence[Any]], reglas: Reglas
) -> tuple[list[int], list[int], list[int], list[int]]:
    """Devuelve (posiciones que cuentan, clase, brigada homologada y tipo de actividad de cada una).

    Las cuatro listas van alineadas. El documento se compara tal cual viene, sin valor
    absoluto, igual que el tablero: las reconexiones traen el documento en negativo y
    por eso nunca coinciden con las listas de excepción.
    """
    n = len(pts["e"])
    gr = pts.get("gr") or [0] * n
    keep: list[int] = []
    for i in range(n):
        if reglas.denominador[gr[i]] != 1:
            continue
        c, doc = pts["c"][i], pts["n"][i]
        if reglas.excluida[c] and doc not in reglas.docs_uc_campo:
            continue
        if reglas.excluida_sin_observacion[c] and doc not in reglas.docs_ni_con_observacion:
            continue
        keep.append(i)

    clase = [
        0 if reglas.numerador[gr[i]] == 1 or reglas.suspendida[pts["c"][i]] else 1
        for i in keep
    ]
    br_crudo = pts.get("br")
    if br_crudo is None:
        return keep, clase, [0] * len(keep), [0] * len(keep)
    brigada = [reglas.brigada_de[br_crudo[i]] for i in keep]
    # «NA» no identifica brigada, pero el lugar técnico de una orden no ejecutada sí la dice.
    if reglas.na >= 0:
        for j, i in enumerate(keep):
            if brigada[j] == reglas.na and reglas.brigada_por_sub[pts["s"][i]] >= 0:
                brigada[j] = reglas.brigada_por_sub[pts["s"][i]]
    n_brigadas = len(reglas.brigadas)
    tipo_actividad = [reglas.accion_de_sub[pts["s"][i]] * n_brigadas + brigada[j] for j, i in enumerate(keep)]
    return keep, clase, brigada, tipo_actividad
