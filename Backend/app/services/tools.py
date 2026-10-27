"""Herramientas que el modelo puede llamar (formato `tools` de OpenAI) y su despachador.

Cada herramienta es una envoltura delgada sobre `metrics`: aquí no se calcula nada.
Un filtro que no resuelve vuelve como resultado de herramienta (con los candidatos),
no como excepción, para que el modelo pregunte cuál en vez de contestar con otra cifra.
"""

from __future__ import annotations

import re
from typing import Any

from app.services import metrics
from app.schemas.chat import VistaTablero
from app.services.payload_store import Payload

_MES = {
    "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
    "description": (
        "Periodo: un mes 'YYYY-MM', un año entero 'YYYY' (vale por todos sus meses con datos) "
        "o una lista de meses sueltos. Si se omite, se usa todo el histórico y la respuesta "
        "lo dice en `base.periodo`."
    ),
}


_SIN_PANTALLA = {
    "type": "boolean",
    "description": (
        "SOLO si el usuario pide expresamente todo el departamento o que ignores sus filtros. "
        "Nombrar un periodo, un municipio o un ciclo NO es motivo: el `mes` o el filtro que pasas "
        "ya reemplaza al de la pantalla, y el resto de filtros de pantalla se siguen aplicando. "
        "Por defecto no se pasa."
    ),
}


def _filtro(descripcion: str) -> dict[str, Any]:
    return {"type": "string", "description": descripcion}


_FILTROS: dict[str, dict[str, Any]] = {
    "municipio": {
        "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
        "description": (
            "Municipio del Huila, p. ej. 'Neiva', 'Garzón'. Es la unidad del mapa. Varios: pasa una "
            "LISTA y las cifras salen sumadas de todos."
        ),
    },
    "zona": _filtro("Zona: Centro, Norte, Occidente o Sur."),
    "ciclo": _filtro("Ciclo de suspensión, por su número («3») o por parte del nombre. Ver `valores_de`."),
    "tecnico": {
        "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
        "description": (
            "Funcionario, por su nombre (completo o parcial) o por su código si solo lo tiene, p. ej. "
            "'6044'. Varios: pasa una LISTA y las cifras salen sumadas de todos."
        ),
    },
    "brigada": _filtro("Tipo de brigada: MOTO, CAMIONETA, MOTO - DOBLE MOTO, CUALQUIERA, SIN DATO."),
    "tipo_actividad": _filtro(
        "Tipo de actividad del mapa: qué se hizo y con qué brigada, p. ej. «Suspensión en gabinete / con moto». "
        "Ver `valores_de`."
    ),
    "causal": _filtro("Causal de suspensión (p. ej. «No pagó», «Factura pagada»)."),
    "clase_servicio": _filtro("Clase de servicio (p. ej. «Alumbrado Público»)."),
    "estrato": _filtro("Estrato: «Estrato 1» … «Estrato 6»."),
    "actividad": _filtro("Suspension o Reconexion."),
    "causa": _filtro(
        "Observación de la visita: el porqué de la orden. Basta el nombre a medias; "
        "si no estás seguro de cómo se llama, usa `valores_de`."
    ),
    "subaccion": _filtro("Dónde quedó la suspensión (poste, gabinete, cañuela...) o por qué no se hizo."),
}

_DIMENSION = {"type": "string", "enum": list(metrics.DIMENSIONES)}

# Los filtros que tiene el mapa. El resto de dimensiones (causa, subacción, estrato) solo existen
# para consultar: no hay dónde ponerlas en la pantalla.
FILTROS_DEL_MAPA = (
    "municipio", "zona", "ciclo", "tecnico", "brigada", "tipo_actividad", "causal", "clase_servicio", "actividad",
)

_DEFINICIONES = (
    (
        "efectividad",
        "Efectividad (efectivas / total de órdenes) de un recorte: todo el departamento, un municipio, "
        "una zona, un técnico, etc. Devuelve órdenes, efectivas, fallidas y `base`, el recorte exacto "
        "sobre el que se calculó, que debes citar.",
        {**_FILTROS, "mes": _MES, "sin_filtros_de_pantalla": _SIN_PANTALLA},
        [],
    ),
    (
        "ranking",
        "Ordena los valores de una dimensión (municipio, técnico, ciclo, causa...) por efectividad, "
        "fallidas o volumen. Para «el mejor/peor municipio» usa ordenar_por='ef_pond', que pondera por "
        "volumen: ordenar por 'ef_pct' a secas llena el tope de grupos diminutos con 100 %. "
        "La efectividad de cada fila es `ef_pct`; `puntaje_orden` solo sirve para ordenar y no se cita.",
        {
            "dimension": {**_DIMENSION, "description": "Qué se compara."},
            **_FILTROS,
            "mes": _MES,
            "ordenar_por": {
                "type": "string",
                "enum": list(metrics.CRITERIOS),
                "description": (
                    "Por defecto 'ef_pond'. 'fallidas' y 'pct_fallidas' para dónde fallan más "
                    "(número y proporción); 'volumen' para dónde hay más órdenes."
                ),
            },
            "peores": {"type": "boolean", "description": "true para el extremo contrario (menor efectividad, menos fallidas...)."},
            "min_ordenes": {"type": "integer", "description": "Mínimo de órdenes para entrar. Por defecto 10."},
            "limite": {"type": "integer", "description": "Cuántas filas devolver. Por defecto 10."},
            "sin_filtros_de_pantalla": _SIN_PANTALLA,
        },
        ["dimension"],
    ),
    (
        "serie_mensual",
        "Órdenes y efectividad mes a mes de un recorte, para ver la tendencia.",
        {**_FILTROS, "sin_filtros_de_pantalla": _SIN_PANTALLA},
        [],
    ),
    (
        "comparar_periodos",
        "Cambio de efectividad entre dos periodos, en puntos porcentuales; con `dimension` lo desglosa y "
        "deja primero lo que más empeoró.",
        {
            "mes_a": _MES,
            "mes_b": _MES,
            "dimension": {**_DIMENSION, "description": "Opcional: desglosar por esta dimensión."},
            **_FILTROS,
            "min_ordenes": {"type": "integer", "description": "Mínimo de órdenes en AMBOS periodos. Por defecto 10."},
            "limite": {"type": "integer", "description": "Filas a devolver. Por defecto 10."},
            "sin_filtros_de_pantalla": _SIN_PANTALLA,
        },
        ["mes_a", "mes_b"],
    ),
    (
        "filtrar_mapa",
        "Pone filtros en el MAPA del usuario para que lo vea (la pantalla se mueve al terminar tu respuesta). "
        "Úsala SOLO cuando pida ver, mostrar, filtrar o ir a algo («muéstrame Neiva», «filtra el ciclo 3»); "
        "para una pregunta de datos no la uses. Solo cambia los filtros que pases: los demás se quedan como estaban.",
        {
            **{c: _FILTROS[c] for c in FILTROS_DEL_MAPA},
            "mes": _MES,
        },
        [],
    ),
    (
        "valores_de",
        "Lista los nombres que existen en una dimensión (ciclos, causas, causales...) para filtrar con uno exacto "
        "cuando el usuario no lo dice igual.",
        {
            "dimension": {**_DIMENSION, "description": "Qué catálogo consultar."},
            "texto": {"type": "string", "description": "Opcional: solo los que contengan este texto."},
        },
        ["dimension"],
    ),
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {"type": "object", "properties": props, "required": requeridos},
        },
    }
    for nombre, descripcion, props, requeridos in _DEFINICIONES
]


def _filtros(args: dict[str, Any]) -> dict[str, metrics.Filtro]:
    return {c: args.get(c) for c in metrics.DIMENSIONES}


def _lista(v: Any) -> list[str]:
    return [] if not v else [v] if isinstance(v, str) else list(v)


def _filtrar_mapa(p: Payload, a: dict[str, Any]) -> dict[str, Any]:
    """Valida los filtros contra el catálogo y arma la acción que el tablero aplicará.

    La `accion` no es para el modelo: el servicio la saca del resultado y la manda al navegador al
    final del turno, para que el mapa se mueva cuando la respuesta ya está escrita y no a medio camino.
    """
    nombres = metrics.nombres_filtros(p, {c: a.get(c) for c in FILTROS_DEL_MAPA})
    meses = [p.meses[i] for i in metrics.resolver_meses(p, a["mes"])[0]] if a.get("mes") else []
    if not nombres and not meses:
        return {"error": "No dijiste qué filtrar. Pide un municipio, zona, ciclo, técnico, brigada o mes."}
    accion = {
        "tipo": "filtrar_mapa",
        "municipios": _lista(nombres.get("municipio")),
        "tecnicos": _lista(nombres.get("tecnico")),
        "meses": meses,
        **{c: nombres.get(c) for c in FILTROS_DEL_MAPA if c not in ("municipio", "tecnico")},
    }
    return {
        "aplicado": {**nombres, **({"meses": meses} if meses else {})},
        "nota": "El mapa se filtra al terminar tu respuesta; di qué filtraste.",
        "accion": accion,
    }


def _ejecutar(nombre: str, p: Payload, a: dict[str, Any]) -> dict[str, Any]:
    if nombre == "efectividad":
        return metrics.efectividad(p, _filtros(a), a.get("mes"))
    if nombre == "ranking":
        return metrics.ranking(
            p, a["dimension"], _filtros(a), a.get("mes"),
            ordenar_por=a.get("ordenar_por") or "ef_pond",
            peores=bool(a.get("peores")),
            min_ordenes=a.get("min_ordenes") or 10,
            limite=a.get("limite") or 10,
        )
    if nombre == "serie_mensual":
        return metrics.serie_mensual(p, _filtros(a))
    if nombre == "comparar_periodos":
        return metrics.comparar_periodos(
            p, a["mes_a"], a["mes_b"], _filtros(a), a.get("dimension"),
            min_ordenes=a.get("min_ordenes") or 10, limite=a.get("limite") or 10,
        )
    if nombre == "valores_de":
        return metrics.valores_de(p, a["dimension"], a.get("texto"))
    if nombre == "filtrar_mapa":
        return _filtrar_mapa(p, a)
    raise KeyError(nombre)


# Palabras con las que alguien pide salirse de lo que tiene filtrado en pantalla.
_PIDE_TODO = re.compile(
    r"\b(departamento|huila|todos? los municipios|todo el territorio|sin filtros?|ignora\w*|quita\w* (los )?filtros?|"
    r"olvida\w* (los )?filtros?|en general|global(es)?)\b"
)


def pide_ignorar_pantalla(mensaje: str) -> bool:
    """¿El usuario pidió expresamente salirse de sus filtros?

    El modelo marcaba `sin_filtros_de_pantalla` por su cuenta con solo oír un año («en 2026»),
    y respondía sobre todo el departamento mientras la persona miraba una zona; con la misma
    pregunta lo hacía unas veces sí y otras no. La bandera solo vale si el mensaje lo pide.
    """
    return bool(_PIDE_TODO.search(metrics.norm(mensaje)))


def _con_pantalla(nombre: str, args: dict[str, Any], vista: VistaTablero | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Completa con los filtros de pantalla lo que el modelo no pidió. Devuelve (args, aplicados).

    El que el modelo pase algo expresamente manda sobre la pantalla. La dimensión que se
    agrupa tampoco se filtra: un ranking por municipio con «Neiva» en pantalla sería una
    sola fila. `valores_de` no filtra nada, y las comparaciones traen sus propios meses.
    """
    if vista is None or args.get("sin_filtros_de_pantalla") or nombre in ("valores_de", "filtrar_mapa"):
        return args, {}
    completos = dict(args)
    aplicados: dict[str, Any] = {}
    for campo, valor in vista.filtros().items():
        if not args.get(campo) and campo != args.get("dimension"):
            completos[campo] = aplicados[campo] = valor
    if vista.meses and nombre in ("efectividad", "ranking") and not args.get("mes"):
        completos["mes"] = aplicados["meses"] = vista.meses
    return completos, aplicados


def ejecutar(nombre: str, argumentos: dict[str, Any], p: Payload, vista: VistaTablero | None = None) -> dict[str, Any]:
    """Corre una herramienta. Nunca lanza: un fallo vuelve como `{"error": ...}` con qué hacer."""
    try:
        args, aplicados = _con_pantalla(nombre, argumentos, vista)
        resultado = _ejecutar(nombre, p, args)
        if aplicados:
            resultado["filtros_de_pantalla"] = aplicados
        return resultado
    except metrics.FiltroNoResuelto as exc:
        motivo = "no encaja en ninguno" if not exc.candidatos else "encaja en varios"
        return {
            "error": f"{exc.campo}={exc.valor!r} {motivo}. No se aplicó ningún filtro: no contestes con una cifra.",
            "candidatos": exc.candidatos,
            "que_hacer": "Pregúntale al usuario cuál quiso decir, o consulta `valores_de`.",
        }
    except metrics.PeriodoNoResuelto as exc:
        return {"error": f"No hay datos para {exc.valor!r}.", "meses_disponibles": exc.disponibles}
    except (KeyError, TypeError) as exc:
        return {"error": f"Herramienta o parámetro no válido: {exc}. Revisa el nombre y los parámetros."}
