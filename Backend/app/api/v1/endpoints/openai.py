"""Endpoints del chat. Solo traducen HTTP: la lógica vive en el servicio."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.openai_service import OpenAIServiceError, get_openai_service

router = APIRouter()


def _servicio():
    try:
        return get_openai_service()
    except OpenAIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Devuelve la respuesta completa."""
    servicio = _servicio()
    partes: list[str] = []
    acciones: list[dict] = []
    try:
        async for e in servicio.stream_chat(request):
            if "delta" in e:
                partes.append(e["delta"])
            elif "accion" in e:
                acciones.append(e["accion"])
    except OpenAIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ChatResponse(
        content="".join(partes), model=request.model or servicio.modelo_por_defecto, acciones=acciones
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Igual que `/chat`, pero por trozos vía SSE.

    Eventos: `{"delta": "..."}` con un trozo de texto, `{"accion": {...}}` con los filtros que el
    tablero debe aplicar (al final) y `{"error": "..."}` si falla ya empezado el flujo. Termina
    siempre con `data: [DONE]`.
    """
    servicio = _servicio()

    async def eventos() -> AsyncIterator[str]:
        try:
            async for e in servicio.stream_chat(request):
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        except OpenAIServiceError as exc:
            # La cabecera 200 ya salió: el error solo puede viajar dentro del flujo.
            yield f"data: {json.dumps({'error': exc.message}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
