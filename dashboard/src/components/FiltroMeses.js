"use client";

import React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

const num = (n) => (n || 0).toLocaleString("es-CO");

const MES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** «Octubre de 2026» → «Octubre». */
const nombreMes = (key) => key.split(" de ")[0];

/**
 * Meses en dos columnas, Año › Mes, como el filtro de Ubicación (Zona › Municipio).
 *
 * Se pueden elegir varios años y varios meses a la vez, y cualquier combinación: la casilla de un año
 * marca o suelta todos sus meses; la columna de meses muestra los del año en foco. Se aplica al
 * instante, sin botón «Aplicar». Nunca se deja el tablero sin meses: la última casilla no se suelta.
 *
 * `st.months` guarda la etiqueta legible de cada mes («Octubre de 2026»); `ym` («2026-10») solo se usa
 * para ordenar y agrupar por año.
 *
 * @param {{key: string, ym: string, n: number, recent: boolean}[]} availableMonths Meses del manifiesto.
 * @param {string[]} activeMonths Etiquetas de los meses elegidos.
 * @param {string[]} loadingMonths Etiquetas de los meses que se están descargando.
 * @param {(clave: string, valor: any) => void} onFilterChange Aplica el cambio al tablero.
 * @param {boolean} puesta Si lo elegido no es el mes de arranque (se pinta la píldora como filtro puesto).
 */
export default function FiltroMeses({ availableMonths, activeMonths, loadingMonths = [], onFilterChange, puesta }) {
  const [abierto, setAbierto] = React.useState(false);
  const [foco, setFoco] = React.useState(null);
  const cajaRef = React.useRef(null);
  // Fijo y centrado, como Ubicación: anclado a la píldora se salía por la derecha en pantallas angostas.
  const [arriba, setArriba] = React.useState(48);

  const meses = React.useMemo(
    () => availableMonths.map((m) => ({ ...m, anio: m.ym.slice(0, 4), mes: +m.ym.slice(5, 7) })),
    [availableMonths]
  );
  const porAnio = React.useMemo(() => {
    const mapa = new Map();
    for (const m of meses) mapa.set(m.anio, [...(mapa.get(m.anio) || []), m]);
    for (const lista of mapa.values()) lista.sort((a, b) => a.mes - b.mes);
    return mapa;
  }, [meses]);
  // Lo más reciente arriba: es lo que casi siempre se busca.
  const anios = React.useMemo(() => [...porAnio.keys()].sort().reverse(), [porAnio]);

  const activos = React.useMemo(() => new Set(activeMonths), [activeMonths]);
  const elegidos = meses.filter((m) => activos.has(m.key));
  const total = meses.length;

  const cerrar = React.useCallback((devolverFoco = true) => {
    setAbierto(false);
    if (devolverFoco) cajaRef.current?.querySelector(".hd-pill")?.focus();
  }, []);

  const abrir = () => {
    // El año en foco es el del último mes elegido: ahí está lo que se mira.
    setFoco(elegidos.length ? elegidos[elegidos.length - 1].anio : anios[0] || null);
    setAbierto(true);
  };

  // Clic fuera cierra; en captura, para que el clic que abre otra píldora no se pierda.
  React.useEffect(() => {
    if (!abierto) return;
    const fuera = (e) => {
      if (!cajaRef.current?.contains(e.target)) cerrar(false);
    };
    const esc = (e) => e.key === "Escape" && cerrar();
    document.addEventListener("mousedown", fuera, true);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fuera, true);
      document.removeEventListener("keydown", esc);
    };
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

  // --- cambios -------------------------------------------------------------------------------
  // Siempre queda al menos un mes elegido: sin meses no hay nada que mostrar.
  const aplicar = (claves) => {
    if (!claves.length) return;
    // En el orden del manifiesto, que es el que espera el resto del tablero.
    onFilterChange("months", meses.filter((m) => claves.includes(m.key)).map((m) => m.key));
  };

  const alternarMes = (key) =>
    aplicar(activos.has(key) ? activeMonths.filter((k) => k !== key) : [...activeMonths, key]);

  const alternarAnio = (anio) => {
    const delAnio = porAnio.get(anio).map((m) => m.key);
    const todos = delAnio.every((k) => activos.has(k));
    aplicar(todos ? activeMonths.filter((k) => !delAnio.includes(k)) : [...new Set([...activeMonths, ...delAnio])]);
  };

  const todosLosMeses = () => aplicar(meses.map((m) => m.key));
  const soloElUltimo = () => {
    const ultimo = meses.find((m) => m.recent) || meses[meses.length - 1];
    if (ultimo) aplicar([ultimo.key]);
  };

  // --- lo que dice la píldora ----------------------------------------------------------------
  const corto = (m) => `${MES_CORTO[m.mes - 1]} ${m.anio}`;
  const seguidos = (lista) => lista.every((m, i) => i === 0 || m.anio * 12 + m.mes === lista[i - 1].anio * 12 + lista[i - 1].mes + 1);
  let resumen;
  if (!elegidos.length || elegidos.length === total) {
    resumen = "Todos los meses";
  } else if (elegidos.length <= 2) {
    resumen = elegidos.map(corto).join(" · ");
  } else {
    const aniosElegidos = [...new Set(elegidos.map((m) => m.anio))];
    const primero = elegidos[0];
    const ultimo = elegidos[elegidos.length - 1];
    if (seguidos(elegidos)) {
      resumen =
        aniosElegidos.length === 1
          ? `${MES_CORTO[primero.mes - 1]} – ${MES_CORTO[ultimo.mes - 1]} ${primero.anio}`
          : `${corto(primero)} – ${corto(ultimo)}`;
    } else {
      resumen = `${elegidos.length} meses · ${aniosElegidos.join(", ")}`;
    }
  }

  const delFoco = foco ? porAnio.get(foco) || [] : [];

  return (
    <div className="hd-f" ref={cajaRef}>
      <button
        type="button"
        className={`hd-pill${puesta ? " on" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        onClick={() => (abierto ? cerrar(false) : abrir())}
      >
        <span className="hd-pill-k">Meses</span>
        <span className="hd-pill-v">: {resumen}</span>
        <span className="hd-pill-n">
          {elegidos.length}/{total}
        </span>
        <span className="hd-pill-ic" aria-hidden="true">
          <ChevronDown size={13} strokeWidth={2.4} />
        </span>
      </button>

      {abierto && (
        <div className="hd-pop ub-pop ub-pop-2" role="dialog" aria-label="Meses" style={{ top: arriba }}>
          <div className="ub-cols mm-cols" style={{ gridTemplateColumns: "minmax(0,0.85fr) minmax(0,1.15fr)" }}>
            <div className="ub-col">
              <div className="ub-head">Año ({anios.length})</div>
              <div className="ub-lista">
                {anios.map((anio) => {
                  const lista = porAnio.get(anio);
                  const marcados = lista.filter((m) => activos.has(m.key)).length;
                  return (
                    <div
                      key={anio}
                      className={`ub-fila mm-fila${foco === anio ? " on" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-pressed={foco === anio}
                      onClick={() => setFoco(anio)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setFoco(anio);
                        }
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={marcados === lista.length}
                        ref={(el) => {
                          if (el) el.indeterminate = marcados > 0 && marcados < lista.length;
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onChange={() => alternarAnio(anio)}
                        aria-label={`Todo ${anio}`}
                      />
                      <span className="ub-nombre">{anio}</span>
                      <span className="ub-n">
                        {marcados}/{lista.length}
                      </span>
                      <ChevronRight size={12} strokeWidth={2.2} aria-hidden="true" />
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="ub-col">
              <div className="ub-head">Mes{foco ? ` · ${foco}` : ""}</div>
              <div className="ub-lista">
                {delFoco.map((m) => {
                  const on = activos.has(m.key);
                  const bajando = loadingMonths.includes(m.key);
                  return (
                    <label
                      key={m.key}
                      className={`ub-fila mm-fila${on ? " on" : ""}`}
                      title={m.recent ? "Mes en curso" : bajando ? "Descargando…" : undefined}
                    >
                      <input type="checkbox" checked={on} onChange={() => alternarMes(m.key)} />
                      <span className="ub-nombre">{nombreMes(m.key)}</span>
                      {bajando ? <span className="mm-spin" aria-label="Descargando" /> : <span className="ub-n">{num(m.n)}</span>}
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="ub-pie">
            <span>
              {elegidos.length} de {total} meses elegidos
            </span>
            <span className="mm-acciones">
              <button type="button" className="ub-limpiar" onClick={todosLosMeses}>
                Todos
              </button>
              <button type="button" className="ub-limpiar" onClick={soloElUltimo}>
                Solo el último
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
