"use client";

import React from "react";
import { ChevronRight, MapPin, Search } from "lucide-react";

const num = (n) => (n || 0).toLocaleString("es-CO");

const sinTildes = (t) =>
  (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Zona › Municipio en un solo control, reemplazo de las píldoras de zona y municipio.
 *
 * ElectroHuila no tiene corregimientos ni barrios en sus datos: la unidad más fina del mapa
 * es el municipio dentro de su zona. Por eso el control termina ahí, en vez de ofrecer
 * columnas vacías. Se aplica al instante, sin botón «Aplicar», como el resto de filtros.
 *
 * Las opciones salen de `avail`, que cuenta las órdenes de cada valor bajo el resto de
 * filtros (los Map `zona` y `muni`): solo se ofrece lo que tiene datos. Suaza, Tarqui y Pital
 * están partidos entre dos zonas, así que con zona puesta el conteo de un municipio es solo
 * el de su parte en esa zona.
 *
 * @param {object} st Estado del tablero (`zona`, `muni`).
 * @param {object} dim Catálogos (`zonas`, `munis`).
 * @param {object} avail Conteos por opción bajo los demás filtros.
 * @param {(clave: string, valor: string) => void} onFilterChange Aplica la cascada del tablero.
 */
export default function FiltroUbicacion({ st, dim, avail, onFilterChange }) {
  const [abierto, setAbierto] = React.useState(false);
  const [busca, setBusca] = React.useState("");
  const cajaRef = React.useRef(null);
  const panelRef = React.useRef(null);
  const buscaRef = React.useRef(null);
  // El panel es `fixed` y centrado: anclado a la píldora (a la izquierda) se salía por la
  // derecha en pantallas angostas. Se mide la distancia al borde superior al abrir.
  const [arriba, setArriba] = React.useState(48);

  const puestoZona = st.zona !== "";
  const puestoMuni = st.muni !== "";
  // Los municipios que elige el mapa, la cola de triaje o el chat viven en `st.barrios`, no en
  // `st.muni`: sin mirarlos, el control decía «Ubicación» a secas con el mapa recortado.
  const eligidos = [...new Set((st.barrios || []).map((b) => dim.b_muni?.[b]).filter((m) => m != null))];
  const puestoBarrios = eligidos.length > 0 && !puestoMuni;
  const puesto = puestoZona || puestoMuni || puestoBarrios;

  const cerrar = React.useCallback((devolverFoco = true) => {
    setAbierto(false);
    setBusca("");
    if (devolverFoco) cajaRef.current?.querySelector(".hd-pill")?.focus();
  }, []);

  // Clic fuera cierra; en captura, para que el clic que abre otra píldora no se pierda.
  React.useEffect(() => {
    if (!abierto) return;
    const fuera = (e) => {
      if (!cajaRef.current?.contains(e.target)) cerrar(false);
    };
    document.addEventListener("mousedown", fuera, true);
    return () => document.removeEventListener("mousedown", fuera, true);
  }, [abierto, cerrar]);

  React.useLayoutEffect(() => {
    if (!abierto) return;
    const medir = () => {
      const caja = cajaRef.current?.getBoundingClientRect();
      if (caja) setArriba(Math.round(caja.bottom) + 6);
    };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [abierto]);

  // `preventScroll`: sin él, enfocar el buscador desplaza la página y se ve como un salto.
  React.useEffect(() => {
    if (abierto) buscaRef.current?.focus({ preventScroll: true });
  }, [abierto]);

  const q = sinTildes(busca.trim());
  const opciones = (nombres, conteos) =>
    nombres
      .map((texto, valor) => ({ valor, texto, n: conteos.get(valor) }))
      .filter((o) => o.n > 0 && (!q || sinTildes(o.texto).includes(q)));

  const zonas = opciones(dim.zonas, avail.zona);
  const munis = opciones(dim.munis, avail.muni);

  const ruta = [
    puestoZona ? dim.zonas[+st.zona] : null,
    puestoMuni ? dim.munis[+st.muni] : null,
    puestoBarrios ? (eligidos.length === 1 ? dim.munis[eligidos[0]] : `${eligidos.length} municipios`) : null
  ].filter(Boolean);

  // Cada conteo de `avail` ya trae aplicado el otro nivel: el del más profundo es el de la selección.
  const ordenes = puestoMuni
    ? avail.muni.get(+st.muni) || 0
    : puestoZona
      ? avail.zona.get(+st.zona) || 0
      : [...avail.zona.values()].reduce((a, n) => a + n, 0);

  const limpiar = () => onFilterChange("zona", ""); // en cascada limpia también el municipio

  // Teclado: ↑ ↓ dentro de la columna, ← → entre columnas, Esc cierra.
  const filasDe = (col) => [...panelRef.current.querySelectorAll(`[data-col="${col}"]`)];
  const teclas = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cerrar();
      return;
    }
    if (e.key === "ArrowDown" && e.target === buscaRef.current) {
      e.preventDefault();
      filasDe(0)[0]?.focus();
      return;
    }
    const actual = e.target.dataset?.col;
    if (actual === undefined) return;
    const col = +actual;
    const filas = filasDe(col);
    const i = filas.indexOf(e.target);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      filas[i + (e.key === "ArrowDown" ? 1 : -1)]?.focus();
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const lista = filasDe(col + (e.key === "ArrowRight" ? 1 : -1));
      (lista.find((f) => f.classList.contains("on")) || lista[0])?.focus();
    }
  };

  const fila = (col, o, activa, onClick) => (
    <button
      key={o.valor}
      type="button"
      data-col={col}
      className={`ub-fila${activa ? " on" : ""}`}
      aria-pressed={activa}
      onClick={onClick}
    >
      <span className="ub-nombre">{o.texto}</span>
      <span className="ub-n">{num(o.n)}</span>
      <ChevronRight size={12} strokeWidth={2.2} aria-hidden="true" />
    </button>
  );

  const filaTodas = (col, texto, activa, onClick) => (
    <button
      type="button"
      data-col={col}
      className={`ub-fila${activa ? " on" : ""}`}
      aria-pressed={activa}
      onClick={onClick}
    >
      <span className="ub-nombre">{texto}</span>
    </button>
  );

  return (
    <div className="hd-f" ref={cajaRef}>
      <button
        type="button"
        className={`hd-pill ub-pill${puesto ? " on" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        onClick={() => (abierto ? cerrar(false) : setAbierto(true))}
      >
        <MapPin size={13} strokeWidth={2.2} aria-hidden="true" />
        <span className="hd-pill-k">Ubicación</span>
        {puesto && <span className="hd-pill-v">: {ruta.join(" › ")}</span>}
      </button>

      {/* Quitar es un botón aparte, como en FiltroPildora: abrir y limpiar no se pelean el clic. */}
      {puesto && (
        <button
          type="button"
          className="hd-pill-x"
          aria-label="Quitar el filtro de ubicación"
          onClick={(e) => {
            e.stopPropagation();
            limpiar();
          }}
        />
      )}

      {abierto && (
        <div
          className="hd-pop ub-pop ub-pop-2"
          role="dialog"
          aria-label="Ubicación"
          ref={panelRef}
          onKeyDown={teclas}
          style={{ top: arriba }}
        >
          <div className="ub-buscar">
            <Search size={13} strokeWidth={2.2} aria-hidden="true" />
            <input
              ref={buscaRef}
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar zona o municipio…"
              aria-label="Buscar ubicación"
            />
          </div>

          <div className="ub-cols" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))" }}>
            <div className="ub-col">
              <div className="ub-head">Zona ({zonas.length})</div>
              <div className="ub-lista">
                {filaTodas(0, "Todas las zonas", !puestoZona, () => onFilterChange("zona", ""))}
                {zonas.map((o) =>
                  fila(0, o, puestoZona && +st.zona === o.valor, () => onFilterChange("zona", String(o.valor)))
                )}
              </div>
            </div>

            <div className="ub-col">
              <div className="ub-head">Municipio ({munis.length})</div>
              <div className="ub-lista">
                {filaTodas(1, "Todos los municipios", !puestoMuni, () => onFilterChange("muni", ""))}
                {munis.map((o) =>
                  fila(1, o, puestoMuni && +st.muni === o.valor, () => onFilterChange("muni", String(o.valor)))
                )}
              </div>
            </div>
          </div>

          <div className="ub-pie">
            <span>
              {num(ordenes)} órdenes · {num(puestoMuni ? 1 : avail.muni.size)}{" "}
              {(puestoMuni ? 1 : avail.muni.size) === 1 ? "municipio" : "municipios"} en la selección
            </span>
            {puesto && (
              <button type="button" className="ub-limpiar" onClick={limpiar}>
                Limpiar ubicación
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
