# Tablero SCR — ElectroHuila

Copia del tablero SCR de Air-E (`Dashboar mapa de calor AIRE SCR-COBROS/Frontend/dashboard`)
alimentada con el payload de ElectroHuila. El original no se tocó.

```bash
npm install
npm run dev      # http://localhost:3000  (usa --webpack; Turbopack no arranca en este equipo)
```

## Qué cambió respecto al original

- **Datos**: `public/data.json` y `public/data_YYYY-MM.json` (21 meses) salen del ETL de
  ElectroHuila (`ElectroHuila_Mapa_Nuevo/web/public`). El ETL no vive aquí.
- **`src/lib/adaptar.js`**: traduce el payload al contrato del tablero. La clase de cada
  orden se deriva de `pts.gr` con `dim.grupoNumerador`: ejecutada = efectiva; todo lo demás
  (no fue posible, no procedía, sin información) = fallida. El mapa solo tiene dos resultados,
  «Efectiva» y «Fallida»; «No aplica» ya no existe. La efectividad es efectivas / total de órdenes.
- **Unidad = municipio**, no barrio (no hay polígonos de barrio que cubran Neiva).
- **Riesgo 0–100**: 65 % fallidas, 15 % volumen, 10 % tendencia, 10 % historial
  del funcionario (la fórmula del visor ElectroHuila anterior; el original daba 40 %
  a las «perdidas», que aquí no existen).
- **Filtros**: zona, municipio, causal de suspensión, clase de servicio, ciclo, actividad, meses.
- **Quitado**: carga de órdenes por ejecutar, selector SCR/COBROS y el rewrite
  a `/api-backend` (dependían del backend de Air-E).
- **Asistente**: `src/components/ChatBot.js` habla con el `Backend/` de este repo
  (`ELECTROHUILA_API_URL`, por defecto `http://127.0.0.1:8000`) y le manda los filtros
  que el usuario tiene en pantalla.
- Sin «familias de causa» (`causa_fam`): el diccionario oficial no las define, así que
  «Acciones recomendadas» solo dispara las reglas que no dependen de ellas.

## Regla: «suspendida» en la observación manda sobre la base
Si la base dice FALLIDA pero la observación es SY, SN, MD, SM, ES, MR o SO (suspensión
realizada en sus variantes), la orden cuenta como **efectiva**. Son 2.137 órdenes en los
21 meses (1.671 SY). La lista está en `src/lib/adaptar.js` (`CODIGOS_SUSPENDIDO`).

## Regla: lo que no se ha asignado no entra
- **Bajas con canal_baja = WEB SERVICE** (baja por pago automática, 106.178 filas, todas observación UC): se excluyen. Las 39 UC con canal CAMPO sí cuentan (`src/lib/uc_no_web_service.json`).
- **NI con la columna Observaciones vacía** (35.037 filas): se excluye. Una NI que sí trae
  texto (2.760) se queda; su lista de documentos está en `src/lib/ni_con_observacion.json`,
  que sale del plano de control y se regenera con cada plano nuevo.
Ambas se descartan igual que «no aplica», porque no se han asignado a un técnico ni a una brigada.
Reglas y comentario en `src/lib/adaptar.js`.
