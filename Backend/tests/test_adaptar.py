"""Reglas de negocio de `adaptar.py`, con un catálogo mínimo hecho a mano.

Cada caso fija una decisión de negocio (ver el README del tablero); si una cambia,
la prueba que falla es la que dice cuál.
"""

from app.services.adaptar import (
    accion_de_lugar,
    clasificar,
    construir_reglas,
    homologar_brigadas,
    nombre_causa,
    nombres_causas,
)

# Causas: 0 normal, 1 suspensión realizada (SY), 2 UC, 3 NI.
DIM = {
    "causas": ["10 · SUSPENSION REALIZADA", "SY · SUSPENDIDA", "UC · USUARIO YA CANCELO", "NI"],
    "subs": ["PO · Ejecutada en poste", "NM · Se visitó y no se pudo ejecutar"],
    "brigadas": ["MOTO", "DOBLE MOTO", "NA", "MOTO - DOBLE MOTO"],
    # grupos: 0 ejecutada, 1 no ejecutable, 2 no procedía
    "grupoNumerador": [1, 0, 0],
    "grupoDenominador": [1, 1, 0],
}


def _pts(filas: list[dict]) -> dict:
    return {k: [f.get(k, 0) for f in filas] for k in ("e", "gr", "c", "s", "br", "n")}


def _clasificar(filas: list[dict], uc: set[int] = frozenset(), ni: set[int] = frozenset()):
    reglas = construir_reglas(DIM, frozenset(uc), frozenset(ni))
    return clasificar(_pts(filas), reglas)


def test_ejecutada_es_efectiva_y_no_ejecutable_es_fallida():
    keep, clase, *_ = _clasificar([{"gr": 0}, {"gr": 1}])
    assert keep == [0, 1]
    assert clase == [0, 1]


def test_no_aplica_no_entra():
    keep, *_ = _clasificar([{"gr": 2}, {"gr": 0}])
    assert keep == [1]


def test_suspendida_en_la_observacion_manda_sobre_la_base():
    # La base dice fallida (gr=1), pero la causa SY dice que se suspendió.
    _, clase, *_ = _clasificar([{"gr": 1, "c": 1}, {"gr": 1, "c": 0}])
    assert clase == [0, 1]


def test_uc_se_excluye_salvo_las_de_campo():
    filas = [{"gr": 1, "c": 2, "n": 100}, {"gr": 1, "c": 2, "n": 200}]
    keep, *_ = _clasificar(filas, uc={200})
    assert keep == [1]


def test_ni_sin_observacion_se_excluye_y_con_observacion_se_queda():
    filas = [{"gr": 1, "c": 3, "n": 100}, {"gr": 1, "c": 3, "n": 200}]
    keep, *_ = _clasificar(filas, ni={200})
    assert keep == [1]


def test_documento_negativo_no_coincide_con_la_excepcion():
    # Igual que el tablero: las reconexiones traen el documento en negativo y no se comparan con abs().
    keep, *_ = _clasificar([{"gr": 1, "c": 2, "n": -200}], uc={200})
    assert keep == []


def test_doble_moto_se_une_a_moto_o_doble_moto():
    nuevo, de = homologar_brigadas(DIM["brigadas"])
    assert nuevo == ["MOTO", "MOTO - DOBLE MOTO", "NA"]
    assert de == [0, 1, 2, 1]


def test_brigada_na_se_deduce_del_lugar_tecnico():
    # NA con subacción «NM» (no se pudo ejecutar en moto) -> MOTO; NA con subacción «PO» sigue NA.
    _, _, brigada, _ = _clasificar([{"gr": 1, "br": 2, "s": 1}, {"gr": 1, "br": 2, "s": 0}])
    assert brigada == [0, 2]


def test_nombres_de_causa_sin_codigo_y_en_minusculas():
    assert nombre_causa("EP · PERSUASION ESPECIAL") == ("Persuasion especial", "EP")
    assert nombre_causa("AM · Suspension AMI") == ("Suspension AMI", "AM")


def test_codigo_corto_sin_descripcion_se_dice_asi():
    assert nombre_causa("NI")[0] == "Sin descripción en el diccionario (NI)"
    assert nombre_causa("SIN DATO")[0] == "Sin dato"


def test_nombres_repetidos_se_desambiguan_con_el_codigo():
    assert nombres_causas(["CA · Ejecutada", "CO · Ejecutada", "GA · Otra"]) == [
        "Ejecutada (CA)", "Ejecutada (CO)", "Otra",
    ]


def test_acciones_segun_el_lugar_tecnico():
    assert accion_de_lugar("GA · Ejecutada en gabinete") == "Suspensión en gabinete"
    assert accion_de_lugar("CO · Ejecutada (caso aislado)") == "Suspensión (caso aislado)"
    assert accion_de_lugar("NM · Se visitó y no se pudo ejecutar") == "Suspensión no ejecutada (se visitó)"
    assert accion_de_lugar("NO · No se intentó la suspensión") == "Suspensión no intentada"
    assert accion_de_lugar("SIN DATO") == "Suspensión (lugar sin descripción)"


def test_tipo_de_actividad_es_accion_por_brigada():
    reglas = construir_reglas(DIM, frozenset(), frozenset())
    # Acciones en orden de aparición: poste (0), no ejecutada (1). Brigadas homologadas: MOTO, MOTO - DOBLE MOTO, NA.
    assert reglas.tipos_actividad[0] == "Suspensión en poste / con moto"
    assert reglas.tipos_actividad[3 + 2] == "Suspensión no ejecutada (se visitó) / sin brigada asignada"
    *_, ta = _clasificar([{"gr": 1, "br": 0, "s": 0}, {"gr": 1, "br": 1, "s": 1}])
    assert ta == [0, 1 * 3 + 1]
