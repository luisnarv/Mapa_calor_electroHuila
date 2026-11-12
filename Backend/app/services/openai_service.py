"""Servicio de OpenAI: única puerta de salida hacia la API del proveedor.

El modelo pide datos a través de las herramientas de `services.tools`: se ejecutan
aquí, se le devuelven como JSON y con eso redacta la respuesta.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.core.config import settings
from app.schemas.chat import ChatRequest, VistaTablero
from app.services import payload_store, tools

logger = logging.getLogger(__name__)

# Colombia no tiene horario de verano: un desfase fijo de -5 es exacto y evita
# depender de la zona horaria del servidor (en la nube suele ser UTC).
COLOMBIA = timezone(timedelta(hours=-5))

# Tope de idas y vueltas modelo -> herramienta -> modelo. Sin esto, un modelo
# confundido puede pedir datos en bucle y consumir la cuota.
MAX_RONDAS = 4

AVISO_SIN_CIERRE = "\n\n(No pude cerrar la consulta; intenta con una pregunta más concreta.)"


class OpenAIServiceError(Exception):
    """Falla al hablar con OpenAI, ya traducida a un estado HTTP."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OpenAIService:
    def __init__(self, client: AsyncOpenAI, default_model: str, system_prompt: str) -> None:
        self._client = client
        self._default_model = default_model
        self._system_prompt = system_prompt

    @property
    def modelo_por_defecto(self) -> str:
        return self._default_model

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[dict[str, Any]]:
        """Emite `{"delta": ...}` con la respuesta y, al final, `{"accion": ...}` si hay que mover el mapa.

        El ciclo de herramientas no sale a la red. La acción va después del texto: el tablero se mueve
        al cerrar la respuesta, no a media redacción, y un turno lo mueve una sola vez (gana la última).
        """
        # El modelo lo fija el servidor: dejarlo al cliente permitía elegir uno caro o inexistente.
        model = self._default_model
        mensajes = self._mensajes(request)
        accion: dict[str, Any] | None = None
        respondio = False
        try:
            for ronda in range(MAX_RONDAS):
                texto, llamadas = "", {}
                async for delta, parcial in self._ronda(model, mensajes, request, con_tools=True):
                    if delta:
                        texto += delta
                        yield {"delta": delta}
                    if parcial is not None:
                        self._acumular(llamadas, parcial)

                if not llamadas:
                    respondio = True
                    break
                mensajes.append(self._mensaje_asistente(texto, llamadas))
                resultados, nueva = await self._resultados(llamadas, request.vista, self._ultimo_del_usuario(request))
                mensajes.extend(resultados)
                accion = _unir_acciones(accion, nueva)
                logger.info("Ronda %s: %s herramienta(s) ejecutada(s).", ronda + 1, len(llamadas))

            # Agotadas las rondas se pide una última respuesta SIN herramientas: cortar con
            # un aviso dejaría sin redactar a un modelo que ya tiene todos los datos delante.
            if not respondio:
                vacio = True
                async for delta, _ in self._ronda(model, mensajes, request, con_tools=False):
                    if delta:
                        vacio = False
                        yield {"delta": delta}
                if vacio:
                    yield {"delta": AVISO_SIN_CIERRE}
            if accion:
                yield {"accion": accion}
        except OpenAIServiceError:
            raise
        except Exception as exc:
            raise self._translate(exc) from exc

    async def close(self) -> None:
        await self._client.close()

    async def _ronda(
        self, model: str, mensajes: list[dict], request: ChatRequest, *, con_tools: bool
    ) -> AsyncIterator[tuple[str, Any]]:
        # Se declaran las herramientas también al cerrar (con `none`): el historial ya
        # trae `tool_calls` y sin declararlas la API rechaza la conversación.
        stream = await self._client.chat.completions.create(
            model=model,
            messages=mensajes,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            tools=tools.TOOLS,
            tool_choice="auto" if con_tools else "none",
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content, None
            for parcial in delta.tool_calls or []:
                yield "", parcial

    @staticmethod
    def _acumular(llamadas: dict[int, dict[str, str]], parcial: Any) -> None:
        """Junta los trozos de una tool call, que llegan repartidos en el stream."""
        slot = llamadas.setdefault(parcial.index, {"id": "", "name": "", "args": ""})
        if parcial.id:
            slot["id"] = parcial.id
        if parcial.function and parcial.function.name:
            slot["name"] += parcial.function.name
        if parcial.function and parcial.function.arguments:
            slot["args"] += parcial.function.arguments

    @staticmethod
    def _mensaje_asistente(texto: str, llamadas: dict[int, dict[str, str]]) -> dict[str, Any]:
        """Reconstruye el turno del asistente para que el modelo lo vea en la siguiente ronda."""
        return {
            "role": "assistant",
            "content": texto or None,
            "tool_calls": [
                {
                    "id": ll["id"],
                    "type": "function",
                    "function": {"name": ll["name"], "arguments": ll["args"] or "{}"},
                }
                for ll in llamadas.values()
            ],
        }

    @staticmethod
    async def _resultados(
        llamadas: dict[int, dict[str, str]], vista: VistaTablero | None, pidio: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        p = payload_store.obtener(
            settings.DATA_DIR, settings.DOCS_UC_CAMPO, settings.DOCS_NI_CON_OBSERVACION
        )
        mensajes = []
        accion = None
        for ll in llamadas.values():
            try:
                args = json.loads(ll["args"] or "{}")
            except json.JSONDecodeError:
                logger.warning("Argumentos no son JSON válido: %r", ll["args"])
                resultado = {"error": "Los argumentos no eran JSON válido. Reintenta."}
            else:
                if args.get("sin_filtros_de_pantalla") and not tools.pide_ignorar_pantalla(pidio):
                    args.pop("sin_filtros_de_pantalla")
                # Recorrer el histórico completo es CPU pura: fuera del hilo del bucle de eventos.
                resultado = await asyncio.to_thread(tools.ejecutar, ll["name"], args, p, vista)
            # La acción es para el navegador, no para el modelo.
            accion = _unir_acciones(accion, resultado.pop("accion", None))
            mensajes.append(
                {"role": "tool", "tool_call_id": ll["id"], "content": json.dumps(resultado, ensure_ascii=False)}
            )
        return mensajes, accion

    @staticmethod
    def _ultimo_del_usuario(request: ChatRequest) -> str:
        return next((m.content for m in reversed(request.messages) if m.role == "user"), "")

    def _mensajes(self, request: ChatRequest) -> list[dict]:
        """Antepone el prompt de sistema. El cliente no puede sobrescribirlo."""
        turnos = [m.model_dump() for m in request.messages if m.role != "system"]
        p = payload_store.obtener(settings.DATA_DIR, settings.DOCS_UC_CAMPO, settings.DOCS_NI_CON_OBSERVACION)
        inicio = "\n\n".join((self._system_prompt, self._fecha(p.fecha_max)))
        # La pantalla va DESPUÉS de la conversación: es lo último que lee el modelo. Al principio lo
        # ganaba el historial y, tras «Limpiar», seguía respondiendo con los técnicos de dos turnos atrás.
        return [{"role": "system", "content": inicio}, *turnos, {"role": "system", "content": self._vista(request.vista)}]

    @staticmethod
    def _fecha(fecha_max: str = "") -> str:
        """El modelo no tiene reloj: sin esto rellena el año con el de su entrenamiento."""
        hoy = datetime.now(COLOMBIA).date()
        texto = (
            f"Hoy es {hoy.isoformat()}. Si el usuario nombra un mes sin año, se refiere al del año "
            f"en curso ({hoy.year}); tradúcelo a YYYY-MM antes de llamar a una herramienta."
        )
        if fecha_max:
            texto += (
                f"\nLOS DATOS LLEGAN HASTA EL {fecha_max} (último dato cargado). Esa es la fecha de corte, no «hoy»: "
                f"si el mes de {fecha_max[:7]} no terminó en esa fecha, está INCOMPLETO. Cuando te pregunten hasta "
                "cuándo llegan los datos o si un mes está completo, responde con esta fecha."
            )
        return texto

    @staticmethod
    def _vista(vista: VistaTablero | None) -> str:
        """Los filtros que el usuario tiene puestos, para que chat y mapa hablen del mismo recorte."""
        resumen = vista.resumen() if vista else ""
        ocultas = (
            "\nEn su mapa tiene OCULTAS las órdenes " + " y ".join(vista.ocultas) + f": ve solo las demás; tus cifras "
            "incluyen ambas clases, y si pregunta por lo que ve en el mapa, aclara esa diferencia."
            if vista and vista.ocultas
            else ""
        )
        if not resumen:
            return (
                "PANTALLA ACTUAL: el usuario NO tiene filtros puestos; está viendo todo el histórico. Aunque en la "
                "conversación se hablara antes de un municipio, técnico, ciclo o mes, YA NO están en su pantalla "
                "(los quitó o los cambió): no los repitas en las herramientas salvo que los pida de nuevo."
                + ocultas
            )
        return (
            f"FILTROS ACTIVOS EN SU PANTALLA AHORA — {resumen}\n"
            "Esta lista es la ÚNICA verdad de lo que ve: los filtros que se mencionaron en turnos anteriores y no "
            "aparecen aquí ya no valen, no los repitas en las herramientas salvo que los pida de nuevo.\n"
            "El servidor los aplica a cada consulta cuando tú no pasas otro lugar o periodo: no hace "
            "falta repetirlos, y el resultado trae `filtros_de_pantalla` con lo que aplicó. Si pide "
            "expresamente otro lugar o periodo, pásalo solo ese: los demás filtros siguen aplicándose. "
            "Usa `sin_filtros_de_pantalla: true` únicamente si dice «todo el departamento» o que ignores sus filtros; "
            "nombrar un año o un mes no es motivo. «Este municipio» o «aquí» se refiere a los de arriba.\n"
            "Al dar una cifra di siempre sobre qué recorte la calculaste."
            + ocultas
        )

    @staticmethod
    def _translate(exc: Exception) -> OpenAIServiceError:
        """Convierte los errores del SDK en algo que el cliente pueda entender."""
        if isinstance(exc, RateLimitError):
            return OpenAIServiceError("OpenAI está limitando las peticiones.", 429)
        if isinstance(exc, APITimeoutError):
            return OpenAIServiceError("OpenAI tardó demasiado en responder.", 504)
        if isinstance(exc, APIConnectionError):
            return OpenAIServiceError("No se pudo conectar con OpenAI.", 502)
        if isinstance(exc, APIStatusError):
            # 401/403 casi siempre es la API key: no se revela al cliente.
            logger.error("OpenAI respondió %s: %s", exc.status_code, exc.message)
            if exc.status_code in (401, 403):
                return OpenAIServiceError("La API no está bien configurada.", 500)
            return OpenAIServiceError("OpenAI rechazó la petición.", 502)
        if isinstance(exc, payload_store.PayloadNoDisponible):
            return OpenAIServiceError(f"No hay datos cargados: {exc}", 503)
        logger.exception("Error inesperado llamando a OpenAI")
        return OpenAIServiceError("Error inesperado al consultar el modelo.", 502)


def _unir_acciones(previa: dict[str, Any] | None, nueva: dict[str, Any] | None) -> dict[str, Any] | None:
    """Junta las acciones de mapa de un mismo turno: lo que pide la última pisa, pero no borra lo anterior.

    «Muéstrame Neiva y la zona Sur» llegaba a veces como dos llamadas y se quedaba solo la última.
    """
    if not nueva:
        return previa
    if not previa:
        return nueva
    unida = dict(previa)
    for campo, valor in nueva.items():
        if valor not in (None, [], ""):
            unida[campo] = valor
    return unida


@lru_cache
def get_openai_service() -> OpenAIService:
    """Una sola instancia: comparte el pool HTTP entre peticiones."""
    if not settings.OPENAI_API_KEY:
        raise OpenAIServiceError("Falta OPENAI_API_KEY en el .env del backend.", 500)
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    return OpenAIService(client, settings.OPENAI_MODEL, settings.OPENAI_SYSTEM_PROMPT)
