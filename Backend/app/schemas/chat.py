"""Contrato de entrada y salida del chat."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=32_000)


class VistaTablero(BaseModel):
    """Lo que el usuario tiene filtrado en pantalla cuando escribe.

    Sin esto el chat responde sobre todo el histórico mientras la persona mira un mes
    y un municipio concretos, y las dos cifras se contradicen sin que nadie entienda
    por qué. Llega en **nombres**, no en índices: el backend no conoce el orden de las
    dimensiones del payload del navegador. Los nombres de los campos son los de
    `metrics.DIMENSIONES`.
    """

    municipios: list[str] = Field(default_factory=list, description="Municipios elegidos a la vez en el tablero.")
    zona: str | None = None
    ciclo: str | None = None
    tecnicos: list[str] = Field(default_factory=list, description="Técnicos elegidos a la vez en el tablero.")
    brigada: str | None = None
    tipo_actividad: str | None = None
    causal: str | None = None
    clase_servicio: str | None = None
    actividad: str | None = None
    # Con un formato fijo y no «cualquier texto»: el tablero mandó «Octubre de 2026» y el
    # chat respondió «no hay datos» sin que nada indicara por qué.
    meses: list[Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]] = Field(
        default_factory=list, description="Claves YYYY-MM"
    )

    def filtros(self) -> dict[str, str | list[str]]:
        """Solo los filtros de catálogo puestos, sin los meses. Los técnicos van con el nombre del filtro."""
        puestos = {k: v for k, v in self.model_dump(exclude={"meses", "tecnicos", "municipios"}).items() if v}
        if self.municipios:
            puestos["municipio"] = self.municipios
        if self.tecnicos:
            puestos["tecnico"] = self.tecnicos
        return puestos

    def resumen(self) -> str:
        partes = [
            f"{k.replace('_', ' ')}{'s' if isinstance(v, list) else ''}: {'; '.join(v) if isinstance(v, list) else v}"
            for k, v in self.filtros().items()
        ]
        if self.meses:
            partes.append(f"meses: {', '.join(self.meses)}")
        return " · ".join(partes)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=50)
    vista: VistaTablero | None = Field(default=None, description="Filtros activos en el tablero del usuario.")
    model: str | None = Field(default=None, description="Si se omite, se usa OPENAI_MODEL del entorno.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=16_000)


class ChatResponse(BaseModel):
    content: str
    model: str
    acciones: list[dict] = Field(default_factory=list, description="Filtros que el tablero debe aplicar.")
