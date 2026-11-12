"""Correcciones tras las pruebas de QA del chat: cada caso es un fallo que se vio con el modelo real."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, Message, VistaTablero
from app.services import metrics, tools
from app.services.openai_service import OpenAIService, _unir_acciones


# --- mes en curso incompleto ---------------------------------------------------------------------


def test_un_mes_que_no_llega_a_su_ultimo_dia_avisa_que_esta_incompleto(payload):
    corto = replace(payload, fecha_max="2026-02-10")
    r = metrics.efectividad(corto, {}, "2026-02")
    assert "INCOMPLETO" in r["base"]["aviso"] and "2026-02-10" in r["base"]["aviso"]
    assert r["base"]["datos_hasta"] == "2026-02-10"


def test_un_mes_cerrado_no_lleva_aviso(payload):
    assert "aviso" not in metrics.efectividad(payload, {}, "2026-01")["base"]
    assert "aviso" not in metrics.efectividad(payload, {}, "2026-02")["base"]  # el 28 es el último de febrero


def test_la_fecha_de_corte_llega_al_prompt_de_sistema(payload):
    req = ChatRequest(messages=[Message(role="user", content="hola")])
    sistema = OpenAIService(None, "m", "PROMPT")._mensajes(req)[0]["content"]
    assert "LOS DATOS LLEGAN HASTA EL" in sistema


# --- ranking: el extremo es literal ---------------------------------------------------------------


def test_extremo_mayor_con_fallidas_trae_los_que_mas_fallan(payload):
    mas = metrics.ranking(payload, "municipio", {}, ordenar_por="fallidas", extremo="mayor", min_ordenes=1)
    menos = metrics.ranking(payload, "municipio", {}, ordenar_por="fallidas", extremo="menor", min_ordenes=1)
    assert mas["filas"][0]["nombre"] == "Aipe" and menos["filas"][0]["nombre"] == "Neiva"
    assert mas["extremo"] == "mayor"


def test_un_extremo_invalido_no_se_acepta(payload):
    assert "error" in tools.ejecutar("ranking", {"dimension": "municipio", "extremo": "peores"}, payload)


# --- resumen: las cuentas que el modelo hacía de cabeza ------------------------------------------


def test_resumen_da_promedios_y_cuenta_solo_tecnicos_reales(payload):
    r = metrics.resumen(payload, {})
    assert r["ordenes"] == 58 and r["meses_con_datos"] == 2
    assert r["promedio_ordenes_por_mes"] == 29.0 and r["promedio_fallidas_por_mes"] == 8.5
    assert r["tecnicos_con_ordenes"] == 1  # el «0» no es una persona
    assert r["ordenes_por_tecnico"]["promedio"] == 58.0
    assert r["municipios_con_ordenes"] == 2


def test_resumen_respeta_el_recorte(payload):
    r = metrics.resumen(payload, {"municipio": "Neiva"}, "2026-01")
    assert (r["ordenes"], r["meses_con_datos"], r["promedio_ordenes_por_mes"]) == (8, 1, 8.0)


# --- valores_de con filtros: dónde queda cada cosa --------------------------------------------------


def test_los_municipios_de_una_zona_salen_de_los_datos(payload):
    r = metrics.valores_de(payload, "municipio", filtros={"zona": "Norte"})
    assert r["valores"] == ["Aipe"]


def test_la_zona_de_un_municipio_sale_de_los_datos(payload):
    assert metrics.valores_de(payload, "zona", filtros={"municipio": "Neiva"})["valores"] == ["Centro"]


def test_valores_de_sin_filtros_sigue_listando_el_catalogo(payload):
    assert metrics.valores_de(payload, "municipio")["valores"] == ["Neiva", "Aipe"]


# --- filtrar_mapa: no se mueve a un mapa vacío ------------------------------------------------------


def test_un_municipio_con_una_zona_que_no_es_la_suya_se_rechaza(payload):
    r = tools.ejecutar("filtrar_mapa", {"municipio": "Aipe", "zona": "Centro"}, payload)
    assert "sin órdenes" in r["error"] and "accion" not in r
    assert set(r["quitando_uno_de_estos_si_hay_ordenes"]) == {"municipio", "zona"}


def test_municipio_sin_zona_suelta_la_zona_de_la_pantalla(payload):
    # Con la zona Centro puesta, «muéstrame Aipe» no es un conflicto: el tablero suelta la zona.
    r = tools.ejecutar("filtrar_mapa", {"municipio": "Aipe"}, payload, VistaTablero(zona="Centro"))
    assert "error" not in r and r["accion"]["municipios"] == ["Aipe"]


def test_una_zona_nueva_suelta_el_municipio_de_la_pantalla(payload):
    r = tools.ejecutar("filtrar_mapa", {"zona": "Norte"}, payload, VistaTablero(municipios=["Neiva"]))
    assert "error" not in r and r["accion"]["zona"] == "Norte"


def test_un_ciclo_o_tecnico_sin_ordenes_en_la_pantalla_actual_se_rechaza(payload):
    # El técnico «0» es de nadie: ninguna orden lo trae.
    r = tools.ejecutar("filtrar_mapa", {"tecnico": "0"}, payload)
    assert "sin órdenes" in r["error"]


def test_lo_que_el_mapa_no_filtra_se_avisa_como_no_aplicado(payload):
    r = tools.ejecutar("filtrar_mapa", {"municipio": "Aipe", "estrato": "Estrato 5"}, payload)
    assert r["no_aplicado"] == {"estrato": "el mapa no filtra por esto"}
    assert r["aplicado"] == {"municipio": "Aipe"}


def test_quitar_filtros_va_en_la_accion(payload):
    r = tools.ejecutar("filtrar_mapa", {"quitar": ["zona"]}, payload, VistaTablero(zona="Norte"))
    assert r["accion"]["quitar"] == ["zona"] and r["aplicado"] == {"quitar": ["zona"]}
    todos = tools.ejecutar("filtrar_mapa", {"quitar": ["todos"]}, payload, VistaTablero(zona="Norte", municipios=["Aipe"]))
    assert todos["accion"]["quitar"] == ["todos"]


def test_quitar_con_nada_valido_sigue_pidiendo_que_diga_cual(payload):
    assert "No dijiste" in tools.ejecutar("filtrar_mapa", {"quitar": ["estrato"]}, payload)["error"]


def test_las_acciones_de_un_mismo_turno_se_juntan():
    a = {"tipo": "filtrar_mapa", "municipios": ["Neiva"], "zona": None, "meses": [], "tecnicos": [], "quitar": []}
    b = {"tipo": "filtrar_mapa", "municipios": [], "zona": "Sur", "meses": ["2026-09"], "tecnicos": [], "quitar": []}
    unida = _unir_acciones(a, b)
    assert unida["municipios"] == ["Neiva"] and unida["zona"] == "Sur" and unida["meses"] == ["2026-09"]
    assert _unir_acciones(None, b) == b and _unir_acciones(a, None) == a


# --- la pantalla manda sobre el historial ----------------------------------------------------------


def test_la_pantalla_va_al_final_de_los_mensajes():
    req = ChatRequest(
        messages=[Message(role="user", content="Muéstrame Neiva"), Message(role="assistant", content="Listo"),
                  Message(role="user", content="¿Cuántas órdenes veo?")],
        vista=VistaTablero(),
    )
    msgs = OpenAIService(None, "m", "PROMPT")._mensajes(req)
    assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "system"
    assert "YA NO están en su pantalla" in msgs[-1]["content"]


def test_los_estados_ocultos_se_le_dicen_al_modelo():
    req = ChatRequest(messages=[Message(role="user", content="hola")], vista=VistaTablero(ocultas=["efectivas"]))
    pantalla = OpenAIService(None, "m", "PROMPT")._mensajes(req)[-1]["content"]
    assert "OCULTAS las órdenes efectivas" in pantalla
    assert VistaTablero(ocultas=["efectivas"]).filtros() == {}  # no es un filtro de datos


# --- contrato de entrada --------------------------------------------------------------------------


def test_los_limites_de_la_peticion():
    with pytest.raises(ValidationError):
        VistaTablero(meses=["2026-13"])
    with pytest.raises(ValidationError):
        VistaTablero(meses=["2026-01"] * 49)
    with pytest.raises(ValidationError):
        ChatRequest(messages=[Message(role="user", content="x")], temperature=2.0)
    with pytest.raises(ValidationError):
        ChatRequest(messages=[Message(role="user", content="x")], max_tokens=5)


def test_el_cliente_no_elige_el_modelo():
    from types import SimpleNamespace

    llamadas = []

    async def create(**kw):
        llamadas.append(kw["model"])

        async def vacio():
            return
            yield

        return vacio()

    import asyncio

    cliente = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    req = ChatRequest(messages=[Message(role="user", content="hola")], model="gpt-carisimo")

    async def correr():
        return [e async for e in OpenAIService(cliente, "modelo-del-servidor", "P").stream_chat(req)]

    asyncio.run(correr())
    assert llamadas == ["modelo-del-servidor"]
