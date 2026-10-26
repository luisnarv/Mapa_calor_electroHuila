"""Rutas de la versión 1 de la API."""

from fastapi import APIRouter, HTTPException

from app.api.v1.endpoints import openai
from app.core.config import settings
from app.services import payload_store

api_router = APIRouter()
api_router.include_router(openai.router, prefix="/openai", tags=["openai"])


@api_router.get("/resumen", tags=["datos"])
def resumen() -> dict:
    """Totales del payload ya adaptado: lo que debe coincidir con el mapa sin filtros."""
    try:
        p = payload_store.obtener(
            settings.DATA_DIR, settings.DOCS_UC_CAMPO, settings.DOCS_NI_CON_OBSERVACION
        )
    except payload_store.PayloadNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    efectivas = p.e.count(0)
    return {
        "ordenes": len(p),
        "efectivas": efectivas,
        "fallidas": len(p) - efectivas,
        # Cruda: efectivas / total de órdenes, la que muestra el mapa.
        "ef_pct": round(100 * efectivas / len(p), 2) if len(p) else None,
        "meses": p.meses,
        "fecha_min": p.fecha_min,
        "fecha_max": p.fecha_max,
        "generado": p.generado,
    }
