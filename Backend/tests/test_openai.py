"""Ciclo de tool calling con un cliente de OpenAI falso: sin red y sin gastar cuota."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.chat import ChatRequest, Message
from app.services import openai_service, payload_store
from app.services.openai_service import MAX_RONDAS, OpenAIService


def _chunk(texto=None, llamada=None):
    funcion = SimpleNamespace(name=llamada[1], arguments=llamada[2]) if llamada else None
    tc = [SimpleNamespace(index=0, id=llamada[0], function=funcion)] if llamada else None
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texto, tool_calls=tc))])


async def _stream(chunks):
    for c in chunks:
        yield c


class ClienteFalso:
    """Responde con una lista de turnos guiones y recuerda con qué mensajes se le llamó."""

    def __init__(self, turnos):
        self.turnos = list(turnos)
        self.llamadas: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.llamadas.append({**kwargs, "messages": list(kwargs["messages"])})
        return _stream(self.turnos.pop(0))


def _pedir(cliente) -> list[str]:
    import asyncio

    async def correr():
        servicio = OpenAIService(cliente, "modelo-falso", "PROMPT")
        req = ChatRequest(messages=[Message(role="user", content="¿Cómo va Aipe?")])
        return [e["delta"] async for e in servicio.stream_chat(req)]

    return asyncio.run(correr())


@pytest.fixture(autouse=True)
def datos_de_prueba(payload, monkeypatch):
    monkeypatch.setattr(payload_store, "obtener", lambda *a, **k: payload)


def test_la_herramienta_corre_y_su_resultado_llega_al_modelo():
    cliente = ClienteFalso([
        [_chunk(llamada=("c1", "efectividad", json.dumps({"municipio": "Aipe"})))],
        [_chunk("Aipe va en "), _chunk("75 %.")],
    ])
    assert "".join(_pedir(cliente)) == "Aipe va en 75 %."
    resultado = next(m for m in cliente.llamadas[1]["messages"] if m["role"] == "tool")
    assert resultado["tool_call_id"] == "c1"
    assert json.loads(resultado["content"])["ef_pct"] == 75.0


def test_el_prompt_de_sistema_va_primero_con_la_fecha():
    cliente = ClienteFalso([[_chunk("hola")]])
    _pedir(cliente)
    sistema = cliente.llamadas[0]["messages"][0]
    assert sistema["role"] == "system" and sistema["content"].startswith("PROMPT")
    assert "Hoy es" in sistema["content"]


def test_argumentos_mal_formados_no_tumban_el_turno():
    cliente = ClienteFalso([
        [_chunk(llamada=("c1", "efectividad", "{no es json"))],
        [_chunk("Reintento.")],
    ])
    assert "".join(_pedir(cliente)) == "Reintento."
    resultado = next(m for m in cliente.llamadas[1]["messages"] if m["role"] == "tool")
    assert "error" in json.loads(resultado["content"])


def test_agotadas_las_rondas_se_pide_cierre_sin_herramientas():
    pide = [_chunk(llamada=("c", "efectividad", "{}"))]
    cliente = ClienteFalso([pide] * MAX_RONDAS + [[_chunk("Con lo reunido: 70,7 %.")]])
    assert "".join(_pedir(cliente)) == "Con lo reunido: 70,7 %."
    assert cliente.llamadas[-1]["tool_choice"] == "none"
    assert all(c["tool_choice"] == "auto" for c in cliente.llamadas[:-1])


def test_cierre_vacio_avisa_en_vez_de_callar():
    pide = [_chunk(llamada=("c", "efectividad", "{}"))]
    cliente = ClienteFalso([pide] * MAX_RONDAS + [[]])
    assert "No pude cerrar la consulta" in "".join(_pedir(cliente))


def test_sin_api_key_el_chat_dice_que_falta(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    openai_service.get_openai_service.cache_clear()
    r = TestClient(app).post("/api/v1/openai/chat", json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 500 and "OPENAI_API_KEY" in r.json()["detail"]


def test_el_prompt_nombra_las_reglas_que_no_se_pueden_perder():
    p = settings.OPENAI_SYSTEM_PROMPT
    for regla in ("municipio", "pérdidas", "candidatos", "ef_pond", "base"):
        assert regla in p
