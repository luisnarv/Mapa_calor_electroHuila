import json

from app.services import payload_store, tools


def test_cada_herramienta_declara_sus_parametros():
    nombres = [t["function"]["name"] for t in tools.TOOLS]
    assert nombres == ["efectividad", "ranking", "por_dia", "serie_mensual", "comparar_periodos", "filtrar_mapa", "valores_de", "resumen"]
    for t in tools.TOOLS:
        f = t["function"]
        assert set(f["parameters"]["required"]) <= set(f["parameters"]["properties"])


def test_ejecutar_devuelve_cifras(payload):
    r = tools.ejecutar("efectividad", {"municipio": "Aipe"}, payload)
    assert (r["ordenes"], r["ef_pct"]) == (40, 75.0)


def test_filtro_no_resuelto_vuelve_como_resultado_no_como_excepcion(payload):
    r = tools.ejecutar("efectividad", {"municipio": "Atlántico"}, payload)
    assert "error" in r and "no contestes con una cifra" in r["error"]
    assert "ef_pct" not in r


def test_periodo_sin_datos_lista_los_meses(payload):
    r = tools.ejecutar("efectividad", {"mes": "2020"}, payload)
    assert r["meses_disponibles"] == ["2026-01", "2026-02"]


def test_herramienta_desconocida_no_lanza(payload):
    assert "error" in tools.ejecutar("inventada", {}, payload)
    assert "error" in tools.ejecutar("ranking", {}, payload)  # falta `dimension`


# --- filtros de pantalla ------------------------------------------------------

from app.schemas.chat import VistaTablero  # noqa: E402


def test_los_filtros_de_pantalla_se_aplican_si_el_modelo_no_pide_otro_lugar(payload):
    vista = VistaTablero(municipios=["Neiva"], meses=["2026-02"])
    r = tools.ejecutar("efectividad", {}, payload, vista)
    assert (r["ordenes"], r["ef_pct"]) == (10, 50.0)
    assert r["filtros_de_pantalla"] == {"municipio": ["Neiva"], "meses": ["2026-02"]}
    assert r["base"] == {"periodo": "2026-02", "filtros": {"municipio": ["Neiva"]}, "datos_hasta": "2026-02-28"}


def test_lo_que_pide_el_modelo_manda_sobre_la_pantalla(payload):
    r = tools.ejecutar("efectividad", {"municipio": "Aipe", "mes": "2026-01"}, payload, VistaTablero(municipios=["Neiva"], meses=["2026-02"]))
    assert (r["ordenes"], r["ef_pct"]) == (20, 100.0)
    assert "filtros_de_pantalla" not in r


def test_sin_filtros_de_pantalla_da_el_total(payload):
    r = tools.ejecutar("efectividad", {"sin_filtros_de_pantalla": True}, payload, VistaTablero(municipios=["Neiva"]))
    assert r["ordenes"] == 58


def test_un_ranking_no_filtra_por_la_dimension_que_agrupa(payload):
    # Con «Neiva» en pantalla, ranking por municipio seguiría comparando los dos.
    r = tools.ejecutar("ranking", {"dimension": "municipio", "min_ordenes": 1}, payload, VistaTablero(municipios=["Neiva"]))
    assert len(r["filas"]) == 2


def test_la_pantalla_aparece_en_el_prompt_de_sistema():
    from app.services.openai_service import OpenAIService
    from app.schemas.chat import ChatRequest, Message

    req = ChatRequest(messages=[Message(role="user", content="hola")], vista=VistaTablero(zona="Norte", meses=["2026-09"]))
    # La pantalla va al final de la conversación: es lo último que lee el modelo.
    pantalla = OpenAIService(None, "m", "PROMPT")._mensajes(req)[-1]["content"]
    assert "FILTROS ACTIVOS EN SU PANTALLA AHORA — zona: Norte · meses: 2026-09" in pantalla
    req.vista = None
    sin = OpenAIService(None, "m", "PROMPT")._mensajes(req)[-1]["content"]
    assert "NO tiene filtros puestos" in sin and "todo el histórico" in sin


def test_la_bandera_de_ignorar_pantalla_solo_vale_si_el_usuario_lo_pide():
    for frase in ("¿Y en todo el departamento?", "dame todo sin filtros", "ignora mis filtros", "en el Huila completo"):
        assert tools.pide_ignorar_pantalla(frase), frase
    # Nombrar un año o un lugar no es pedir salirse de la pantalla.
    for frase in ("Compara la efectividad por tipo de brigada en 2026", "¿Y en septiembre?", "efectividad del ciclo 3"):
        assert not tools.pide_ignorar_pantalla(frase), frase


def test_el_servicio_descarta_la_bandera_si_el_usuario_no_la_pidio(payload, monkeypatch):
    import asyncio

    monkeypatch.setattr(payload_store, "obtener", lambda *a, **k: payload)
    from app.services.openai_service import OpenAIService

    llamadas = {0: {"id": "c", "name": "efectividad", "args": json.dumps({"sin_filtros_de_pantalla": True})}}
    vista = VistaTablero(municipios=["Neiva"])
    res, _ = asyncio.run(OpenAIService._resultados(llamadas, vista, "¿Cómo va 2026?"))
    assert json.loads(res[0]["content"])["ordenes"] == 18  # Neiva, no los 58 del total
    res, _ = asyncio.run(OpenAIService._resultados(llamadas, vista, "¿Y en todo el departamento?"))
    assert json.loads(res[0]["content"])["ordenes"] == 58


def test_la_vista_rechaza_meses_que_no_son_clave():
    import pytest
    from pydantic import ValidationError

    assert VistaTablero(meses=["2026-10"]).meses == ["2026-10"]
    with pytest.raises(ValidationError):
        VistaTablero(meses=["Octubre de 2026"])


def test_los_tecnicos_elegidos_en_pantalla_llegan_como_lista(payload):
    vista = VistaTablero(tecnicos=["0", "6044"])
    assert vista.filtros() == {"tecnico": ["0", "6044"]}
    assert vista.resumen() == "tecnicos: 0; 6044"
    r = tools.ejecutar("efectividad", {}, payload, vista)
    assert r["ordenes"] == 58
    assert r["filtros_de_pantalla"] == {"tecnico": ["0", "6044"]}


def test_un_ranking_por_tecnico_no_se_filtra_por_los_elegidos(payload):
    vista = VistaTablero(tecnicos=["0"])
    r = tools.ejecutar("ranking", {"dimension": "tecnico", "min_ordenes": 1}, payload, vista)
    assert [f["nombre"] for f in r["filas"]] == ["6044"]


def test_varios_municipios_elegidos_se_suman(payload):
    vista = VistaTablero(municipios=["Neiva", "Aipe"], zona=None)
    assert vista.filtros() == {"municipio": ["Neiva", "Aipe"]}
    assert vista.resumen() == "municipios: Neiva; Aipe"
    r = tools.ejecutar("efectividad", {}, payload, vista)
    assert r["ordenes"] == 58  # 18 de Neiva + 40 de Aipe
    solo = tools.ejecutar("efectividad", {}, payload, VistaTablero(municipios=["Aipe"]))
    assert solo["ordenes"] == 40


def test_un_ranking_por_municipio_no_se_filtra_por_los_elegidos(payload):
    r = tools.ejecutar("ranking", {"dimension": "municipio", "min_ordenes": 1}, payload, VistaTablero(municipios=["Neiva"]))
    assert len(r["filas"]) == 2


# --- filtrar_mapa -------------------------------------------------------------


def test_filtrar_mapa_arma_la_accion_con_nombres_del_catalogo(payload):
    r = tools.ejecutar("filtrar_mapa", {"municipio": ["neiva", "AIPE"], "zona": "norte", "mes": "2026-02"}, payload)
    assert r["accion"] == {
        "tipo": "filtrar_mapa", "municipios": ["Neiva", "Aipe"], "tecnicos": [], "meses": ["2026-02"], "quitar": [],
        "zona": "Norte", "ciclo": None, "brigada": None,
        "causal": None, "clase_servicio": None, "actividad": None,
    }
    assert r["aplicado"]["zona"] == "Norte"


def test_filtrar_mapa_un_municipio_suelto_llega_como_lista(payload):
    r = tools.ejecutar("filtrar_mapa", {"municipio": "Aipe"}, payload)
    assert r["accion"]["municipios"] == ["Aipe"]


def test_filtrar_mapa_sin_filtros_pide_que_diga_cual(payload):
    assert "No dijiste qué filtrar" in tools.ejecutar("filtrar_mapa", {}, payload)["error"]


def test_filtrar_mapa_no_filtra_a_ciegas_un_nombre_que_no_existe(payload):
    r = tools.ejecutar("filtrar_mapa", {"municipio": "Atlántico"}, payload)
    assert "error" in r and "accion" not in r


def test_filtrar_mapa_no_hereda_los_filtros_de_pantalla(payload):
    # Solo cambia lo que se le pide: completarlo con la pantalla le diría al tablero lo que ya tiene.
    r = tools.ejecutar("filtrar_mapa", {"zona": "Norte"}, payload, VistaTablero(municipios=["Neiva"]))
    assert r["accion"]["municipios"] == [] and "filtros_de_pantalla" not in r
