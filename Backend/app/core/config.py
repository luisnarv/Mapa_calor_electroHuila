"""Variables de entorno con Pydantic. Única fuente de configuración."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = BACKEND_ROOT.parent / "dashboard"
PROMPTS_DIR = BACKEND_ROOT / "app" / "prompts"


def leer_prompt(nombre: str) -> str:
    """Lee un prompt de `app/prompts/`.

    Falla al arrancar si no está, en vez de dejar al asistente sin instrucciones
    y que se note cuando alguien pregunte algo raro.
    """
    ruta = PROMPTS_DIR / nombre
    if not ruta.is_file():
        raise RuntimeError(f"Falta el prompt {ruta}. Restaura el archivo antes de arrancar.")
    return ruta.read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "SCR ElectroHuila API"
    API_V1_PREFIX: str = "/api/v1"

    # Por defecto se lee de donde lee el tablero: el ETL de ElectroHuila no vive
    # en este repo y los JSON se copian a mano a `public/`. Mantener una segunda
    # copia aquí dejaría que el chat y el mapa discreparan sin que nadie se entere.
    DATA_DIR: Path = DASHBOARD / "public"

    # Documentos que `dashboard/src/lib/adaptar.js` exceptúa de la exclusión de UC y NI.
    # Se leen de allí mismo para tener una sola lista (se regenera con cada plano nuevo).
    DOCS_UC_CAMPO: Path = DASHBOARD / "src" / "lib" / "uc_no_web_service.json"
    DOCS_NI_CON_OBSERVACION: Path = DASHBOARD / "src" / "lib" / "ni_con_observacion.json"

    # Vacía por defecto para poder correr las pruebas sin clave; el chat responde 500
    # con un mensaje claro si falta (ver `get_openai_service`).
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_TIMEOUT_SECONDS: float = 60.0
    OPENAI_MAX_RETRIES: int = 2
    OPENAI_SYSTEM_PROMPT: str = leer_prompt("sistema.md")

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cacheado: se lee el entorno una sola vez por proceso."""
    return Settings()


settings = get_settings()
