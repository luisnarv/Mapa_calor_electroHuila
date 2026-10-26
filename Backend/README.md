# Backend SCR – ElectroHuila

API FastAPI con el asistente del tablero: el modelo de OpenAI consulta las órdenes por
herramientas (`app/services/tools.py`) y responde con esas cifras.

```bash
cd Backend
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env        # y completar OPENAI_API_KEY
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --reload-dir app
.venv/Scripts/python.exe -m pytest -q
```

- **Datos**: lee los mismos JSON que el mapa (`../dashboard/public`, o `DATA_DIR`). El ETL no
  vive en este repo; hay que copiarlos a mano.
- **Reglas**: `app/services/adaptar.py` es la traducción a Python de `dashboard/src/lib/adaptar.js`
  (qué órdenes cuentan y cuáles son efectivas). Si cambia una, cambia la otra, o el chat y el mapa
  dejan de coincidir. Las listas de excepción UC/NI se leen de `dashboard/src/lib`.
- **Pendiente**: feedback con pulgares y traza, observaciones del acta (`buscar_en_observaciones`),
  autenticación y límite de peticiones del endpoint de chat.
