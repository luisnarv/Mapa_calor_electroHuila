import json

from app.services import payload_store, tools


def test_cada_herramienta_declara_sus_parametros():
    nombres = [t["function"]["name"] for t in tools.TOOLS]
    assert nombres == ["efectividad", "ranking", "serie_mensual", "comparar_periodos", "valores_de"]
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
    vista = VistaTablero(municipio="Neiva", meses=["2026-02"])
    r = tools.ejecutar("efectividad", {}, payload, vista)
    assert (r["ordenes"], r["ef_pct"]) == (10, 50.0)
    assert r["filtros_de_pantalla"] == {"municipio": "Neiva", "meses": ["2026-02"]}
    assert r["base"] == {"periodo": "2026-02", "filtros": {"municipio": "Neiva"}}


def test_lo_que_pide_el_modelo_manda_sobre_la_pantalla(payload):
    r = tools.ejecutar("efectividad", {"municipio": "Aipe", "mes": "2026-01"}, payload, VistaTablero(municipio="Neiva", meses=["2026-02"]))
    assert (r["ordenes"], r["ef_pct"]) == (20, 100.0)
    assert "filtros_de_pantalla" not in r


def test_sin_filtros_de_pantalla_da_el_total(payload):
    r = tools.ejecutar("efectividad", {"sin_filtros_de_pantalla": True}, payload, VistaTablero(municipio="Neiva"))
    assert r["ordenes"] == 58


def test_un_ranking_no_filtra_por_la_dimension_que_agrupa(payload):
    # Con «Neiva» en pantalla, ranking por municipio seguiría comparando los dos.
    r = tools.ejecutar("ranking", {"dimension": "municipio", "min_ordenes": 1}, payload, VistaTablero(municipio="Neiva"))
    assert len(r["filas"]) == 2


def test_la_pantalla_aparece_en_el_prompt_de_sistema():
    from app.services.openai_service import OpenAIService
    from app.schemas.chat import ChatRequest, Message

    req = ChatRequest(messages=[Message(role="user", content="hola")], vista=VistaTablero(zona="Norte", meses=["2026-09"]))
    sistema = OpenAIService(None, "m", "PROMPT")._mensajes(req)[0]["content"]
    assert "FILTROS ACTIVOS EN SU PANTALLA — zona: Norte · meses: 2026-09" in sistema
    req.vista = None
    assert "todo el histórico" in OpenAIService(None, "m", "PROMPT")._mensajes(req)[0]["content"]


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
    vista = VistaTablero(municipio="Neiva")
    res = asyncio.run(OpenAIService._resultados(llamadas, vista, "¿Cómo va 2026?"))
    assert json.loads(res[0]["content"])["ordenes"] == 18  # Neiva, no los 58 del total
    res = asyncio.run(OpenAIService._resultados(llamadas, vista, "¿Y en todo el departamento?"))
    assert json.loads(res[0]["content"])["ordenes"] == 58
