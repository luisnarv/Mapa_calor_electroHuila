import pytest

from app.services import metrics


def test_efectividad_total_y_por_municipio(payload):
    total = metrics.efectividad(payload, {})
    assert (total["ordenes"], total["efectivas"], total["fallidas"]) == (58, 41, 17)
    assert total["ef_pct"] == 70.7
    neiva = metrics.efectividad(payload, {"municipio": "neiva"}, "2026-02")
    assert (neiva["ordenes"], neiva["ef_pct"]) == (10, 50.0)
    assert neiva["base"] == {"periodo": "2026-02", "filtros": {"municipio": "Neiva"}}


def test_un_anio_vale_por_todos_sus_meses(payload):
    assert metrics.efectividad(payload, {}, "2026")["ordenes"] == 58


def test_periodo_sin_datos_dice_cuales_hay(payload):
    with pytest.raises(metrics.PeriodoNoResuelto) as exc:
        metrics.efectividad(payload, {}, "2024-01")
    assert exc.value.disponibles == ["2026-01", "2026-02"]


def test_filtro_que_no_existe_no_devuelve_el_total(payload):
    # El caso que motivó la regla: «Atlántico» no es un municipio y no debe dar el total sin filtrar.
    with pytest.raises(metrics.FiltroNoResuelto):
        metrics.efectividad(payload, {"municipio": "Atlántico"})


def test_filtro_ambiguo_lista_los_candidatos(payload):
    with pytest.raises(metrics.FiltroNoResuelto) as exc:
        metrics.efectividad(payload, {"estrato": "estrato"})
    assert exc.value.candidatos == ["Estrato 5", "Estrato 5 exento"]


def test_coincidencia_exacta_gana_a_la_parcial(payload):
    # «Estrato 5» está contenido en «Estrato 5 exento», pero es exacto de uno solo.
    assert metrics.resolver(payload.tarifas, "estrato 5", "estrato") == 0


def test_ranking_pondera_por_volumen(payload):
    # Aipe: 30/40 = 75 %; Neiva: 11/18 = 61,1 %; media 70,7 %. Neiva (61,1 %) sube a 68,2 y Aipe (75 %) baja a 72,6: la poca muestra tira hacia la media.
    r = metrics.ranking(payload, "municipio", {}, min_ordenes=1)
    aipe, neiva = r["filas"]
    assert (aipe["nombre"], neiva["nombre"]) == ("Aipe", "Neiva")
    assert (aipe["puntaje_orden"], neiva["puntaje_orden"]) == (72.6, 68.2)


def test_el_ranking_no_presenta_el_puntaje_como_efectividad(payload):
    fila = metrics.ranking(payload, "municipio", {}, min_ordenes=1)["filas"][0]
    assert fila["ef_pct"] == 75.0 and "ef_pond" not in fila


def test_ranking_respeta_minimo_y_peores(payload):
    r = metrics.ranking(payload, "municipio", {}, min_ordenes=30)
    assert [f["nombre"] for f in r["filas"]] == ["Aipe"]
    peores = metrics.ranking(payload, "municipio", {}, peores=True, min_ordenes=1)
    assert peores["filas"][0]["nombre"] == "Neiva"


def test_ranking_por_fallidas_y_su_participacion(payload):
    r = metrics.ranking(payload, "municipio", {}, ordenar_por="fallidas", min_ordenes=1)
    assert [(f["nombre"], f["fallidas"]) for f in r["filas"]] == [("Aipe", 10), ("Neiva", 7)]
    assert r["filas"][0]["pct_de_las_fallidas"] == 58.8


def test_ranking_de_tecnicos_omite_codigos_que_no_son_personas(payload):
    r = metrics.ranking(payload, "tecnico", {}, min_ordenes=1)
    assert [f["nombre"] for f in r["filas"]] == ["6044"]


def test_comparar_periodos_deja_primero_lo_que_mas_empeoro(payload):
    r = metrics.comparar_periodos(payload, "2026-01", "2026-02", {}, "municipio", min_ordenes=1)
    assert [(f["nombre"], f["cambio_pp"]) for f in r["filas"]] == [("Aipe", -50.0), ("Neiva", -25.0)]


def test_serie_mensual(payload):
    s = metrics.serie_mensual(payload, {"municipio": "Aipe"})["serie"]
    assert [(f["mes"], f["ef_pct"]) for f in s] == [("2026-01", 100.0), ("2026-02", 50.0)]


def test_valores_de_filtra_por_texto(payload):
    assert metrics.valores_de(payload, "estrato", "exento")["valores"] == ["Estrato 5 exento"]
