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

    municipios: list[str] = Field(
        default_factory=list, max_length=60, description="Municipios elegidos a la vez en el tablero."
    )
    zona: str | None = None
    ciclo: str | None = None
    tecnicos: list[str] = Field(
        default_factory=list, max_length=200, description="Técnicos elegidos a la vez en el tablero."
    )
    brigada: str | None = None
    tipo_actividad: str | None = None
    causal: str | None = None
    clase_servicio: str | None = None
    actividad: str | None = None
    # Con un formato fijo y no «cualquier texto»: el tablero mandó «Octubre de 2026» y el
    # chat respondió «no hay datos» sin que nada indicara por qué.
    meses: list[Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]] = Field(
        default_factory=list, max_length=48, description="Claves YYYY-MM"
    )
    # Lo que el usuario tiene apagado en «Capas»: el mapa solo dibuja lo demás, y el chat cuenta ambas.
    ocultas: list[Literal["efectivas", "fallidas"]] = Field(default_factory=list, max_length=2)

    def filtros(self) -> dict[str, str | list[str]]:
        """Solo los filtros de catálogo puestos, sin los meses. Los técnicos van con el nombre del filtro."""
        puestos = {k: v for k, v in self.model_dump(exclude={"meses", "tecnicos", "municipios", "ocultas"}).items() if v}
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
        # Separador « | » y no « · »: el nombre de un ciclo («6 · CALLES 12 A 25C») ya lleva « · » y el modelo lo
        # partía en un ciclo «6» y un municipio «CALLES 12 A 25C».
        return " | ".join(partes)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=50)
    vista: VistaTablero | None = Field(default=None, description="Filtros activos en el tablero del usuario.")
    model: str | None = Field(default=None, description="Ignorado: el modelo lo fija OPENAI_MODEL del servidor.")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=64, le=16_000)


class ChatResponse(BaseModel):
    content: str
    model: str
    acciones: list[dict] = Field(default_factory=list, description="Filtros que el tablero debe aplicar.")
