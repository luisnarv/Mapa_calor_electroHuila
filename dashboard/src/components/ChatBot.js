"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Check, Copy, Crosshair, MessageSquare, Maximize2, Mic, Minus, Pin, PinOff, Send, X } from "lucide-react";

const BUBBLE = 56;
const MARGIN = 20;
const PANEL_W = 380;
const PANEL_MAX_H = 640;
const DRAG_SLOP = 4;
// Debe coincidir con la animación `cb-out` de globals.css.
const CLOSE_MS = 160;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const STREAM_ENDPOINT = `${API_URL}/api/v1/openai/chat/stream`;
const HEALTH_ENDPOINT = `${API_URL}/health`;

// También con el chat cerrado, porque el globo muestra su propio punto de estado;
// ahí se espacía, que nadie está leyendo la respuesta en ese momento.
const PING_MS = 30000;
const PING_CERRADO_MS = 120000;
// Si el backend está caído la petición muere por timeout de red y eso tarda;
// con un corte propio el aviso sale rápido en vez de dejar «Conectando…».
const PING_TIMEOUT_MS = 5000;

// El backend no guarda la conversación: se manda en cada turno, acotada.
const MAX_HISTORIAL = 20;

const CHIPS = [
  { rotulo: "Peor efectividad", pregunta: "¿Qué municipios tienen peor efectividad?" },
  { rotulo: "Por qué fallan", pregunta: "¿Por qué causas fallan más las órdenes?" },
  { rotulo: "Tendencia", pregunta: "¿Cómo ha cambiado la efectividad mes a mes?" }
];

const SALUDO = { role: "assistant", content: "Hola. ¿En qué puedo ayudarte hoy?" };

// Se van mostrando en orden mientras no llegue el primer trozo de respuesta.
const PENSANDO = [
  "Pensando…",
  "Analizando la consulta…",
  "Revisando los datos…",
  "Cruzando los datos del tablero…",
  "Redactando la respuesta…",
  "Sigo en ello, dame un momento…"
];
const PENSANDO_MS = 2800;

// `.` no cruza saltos de línea a propósito: si el modelo deja un ** suelto, se
// come una palabra y no el resto del mensaje.
const NEGRITA = /\*\*(.+?)\*\*/g;
// El modelo a veces escupe encabezados; en 380 px no titulan nada, se degradan a negrita.
const ENCABEZADO = /^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$/gm;

/**
 * Pone en negrita los `**...**` del modelo. Devuelve nodos de React, nunca HTML: el texto
 * viene de un modelo de lenguaje y con `dangerouslySetInnerHTML` cualquier etiqueta se ejecutaría.
 */
function conNegritas(crudo) {
  const texto = crudo.replace(ENCABEZADO, "**$1**");
  const nodos = [];
  let cursor = 0;
  for (const m of texto.matchAll(NEGRITA)) {
    if (m.index > cursor) nodos.push(texto.slice(cursor, m.index));
    nodos.push(<strong key={m.index}>{m[1]}</strong>);
    cursor = m.index + m[0].length;
  }
  if (!nodos.length) return texto;
  if (cursor < texto.length) nodos.push(texto.slice(cursor));
  return nodos;
}

/**
 * Hora local de un mensaje, "HH:MM". Se guarda la marca y se formatea al pintar: así sale en
 * el huso de quien mira. El saludo no lleva marca a propósito, porque el panel también se
 * renderiza en el servidor y una hora calculada ahí no coincidiría con la del navegador.
 */
function horaDe(marca) {
  if (!marca) return null;
  return new Date(marca).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", hour12: false });
}

const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** «2026-09» → «sep 2026»: el chip no debe mostrar la clave interna. */
const mesLegible = (ym) => {
  const [anio, mes] = String(ym).split("-");
  return MESES_CORTOS[+mes - 1] ? `${MESES_CORTOS[+mes - 1]} ${anio}` : ym;
};

const NOMBRE_QUITAR = {
  todos: "todos los filtros",
  municipio: "municipio",
  zona: "zona",
  ciclo: "ciclo",
  tecnico: "técnico",
  brigada: "brigada",
  causal: "causal",
  clase_servicio: "clase de servicio",
  actividad: "actividad",
  mes: "mes"
};

/** Convierte el filtro que el asistente puso en el mapa en una línea legible. Null si no filtra nada. */
function resumirFiltro(a) {
  const lista = (v, varios) => (!v?.length ? null : v.length <= 2 ? v.join(", ") : `${v.length} ${varios}`);
  const partes = [
    lista(a.municipios, "municipios"),
    lista(a.tecnicos, "técnicos"),
    a.zona,
    a.ciclo,
    a.brigada,
    a.causal,
    a.clase_servicio,
    a.actividad,
    a.meses?.length ? a.meses.map(mesLegible).join(", ") : null,
    a.quitar?.length ? `sin ${a.quitar.map((c) => NOMBRE_QUITAR[c] || c).join(", ")}` : null
  ].filter(Boolean);
  return partes.length ? partes.join(" · ") : null;
}

/** Copiar la respuesta. Sin permiso de portapapeles el botón simplemente no confirma. */
function Acciones({ texto }) {
  const [copiado, setCopiado] = useState(false);

  const copiar = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1600);
    } catch {
      // Sin HTTPS o sin permiso no hay nada que hacer: se puede seleccionar a mano.
    }
  }, [texto]);

  return (
    <div className="cb-acts">
      <button type="button" onClick={copiar} title={copiado ? "Copiado" : "Copiar respuesta"} aria-label="Copiar la respuesta">
        {copiado ? <Check size={13} strokeWidth={2.2} aria-hidden="true" /> : <Copy size={13} strokeWidth={2.2} aria-hidden="true" />}
      </button>
    </div>
  );
}

/** Etiqueta de espera. Avanza por las frases y se queda en la última. */
function Pensando() {
  const [i, setI] = useState(0);

  useEffect(() => {
    if (i >= PENSANDO.length - 1) return;
    const id = setTimeout(() => setI((n) => n + 1), PENSANDO_MS);
    return () => clearTimeout(id);
  }, [i]);

  return (
    <div className="cb-msg bot cb-thinking">
      <span key={i} className="cb-thinking-t">
        {PENSANDO[i]}
      </span>
    </div>
  );
}

/** Lee el SSE del backend y entrega cada evento JSON. Termina con `[DONE]` o al cerrarse el flujo. */
async function leerFlujo(respuesta, alEvento) {
  const lector = respuesta.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const bloques = buffer.split("\n\n");
    buffer = bloques.pop();
    for (const b of bloques) {
      const dato = b.replace(/^data: ?/, "").trim();
      if (dato === "[DONE]") return;
      if (dato) alEvento(JSON.parse(dato));
    }
  }
}

/**
 * @param {{ vista?: object|null, onAccion?: (accion: object) => void, onToggle?: (abierto: boolean) => void }} props
 *   `vista` son los filtros que el usuario tiene en pantalla (en nombres). Se lee al enviar,
 *   no al montar: el tablero cambia de filtros sin avisar al chat.
 *   `onAccion` recibe los filtros que el asistente pide poner en el mapa.
 *   `onToggle` avisa al tablero para que repliegue lo que flota debajo (el panel de capas).
 */
export default function ChatBot({ vista, onAccion, onToggle }) {
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([SALUDO]);
  const [busy, setBusy] = useState(false);
  // "probando" mientras no se sabe: afirmar «En línea» desde el primer render sería
  // decir algo que nadie comprobó.
  const [conexion, setConexion] = useState("probando");

  const [escuchando, setEscuchando] = useState(false);
  const [soportaVoz, setSoportaVoz] = useState(false);
  const [errorVoz, setErrorVoz] = useState(null);

  const [panelPos, setPanelPos] = useState(null);
  const [panelDragging, setPanelDragging] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [minimized, setMinimized] = useState(false);

  // Hasta que se arrastra, la burbuja va anclada abajo a la derecha por CSS: calcular una
  // posición al montar dependía del tamaño de la ventana en ese instante (con el panel recién
  // abierto o en cero quedaba en una esquina equivocada).
  const [place, setPlace] = useState(null);

  const anclaX = panelPos ? panelPos.x + PANEL_W / 2 : place ? place.x + BUBBLE / 2 : null;
  const side = anclaX !== null && typeof window !== "undefined" && anclaX < window.innerWidth / 2 ? "left" : "right";

  const launcherRef = useRef(null);
  const panelRef = useRef(null);
  const bodyRef = useRef(null);
  const abortRef = useRef(null);
  const closeTimer = useRef(null);
  const dragRef = useRef({ dx: 0, dy: 0, ox: 0, oy: 0, moved: false });
  const panelDragRef = useRef({ dx: 0, dy: 0, w: 0, h: 0 });
  const vozRef = useRef(null);
  const previoRef = useRef("");

  // El último filtro que el asistente puso en el mapa, para poder volver a ponerlo si el usuario lo limpió.
  const [filtroAplicado, setFiltroAplicado] = useState(null);

  const vistaRef = useRef(vista);
  const accionRef = useRef(onAccion);
  useEffect(() => {
    vistaRef.current = vista;
    accionRef.current = onAccion;
  }, [vista, onAccion]);

  useEffect(() => {
    onToggle?.(open);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // El texto y el color del punto salen del mismo sitio para que no puedan contradecirse.
  const estadoConexion =
    conexion === "caido"
      ? { clase: "off", texto: "Sin conexión con el servidor" }
      : busy
        ? { clase: "on", texto: "Escribiendo…" }
        : conexion === "probando"
          ? { clase: "wait", texto: "Conectando…" }
          : { clase: "on", texto: "En línea" };

  // Comprueba el backend periódicamente, abierto o cerrado: sin esto el indicador solo se
  // enteraba de una caída cuando un envío fallaba. Depende de `open` para reajustar el ritmo.
  useEffect(() => {
    let cancelado = false;
    let timer = null;

    const comprobar = async () => {
      const controller = new AbortController();
      const corte = setTimeout(() => controller.abort(), PING_TIMEOUT_MS);
      try {
        const res = await fetch(HEALTH_ENDPOINT, { signal: controller.signal, cache: "no-store" });
        if (!cancelado) setConexion(res.ok ? "ok" : "caido");
      } catch {
        if (!cancelado) setConexion("caido");
      } finally {
        clearTimeout(corte);
        if (!cancelado) timer = setTimeout(comprobar, open ? PING_MS : PING_CERRADO_MS);
      }
    };

    comprobar();
    return () => {
      cancelado = true;
      if (timer) clearTimeout(timer);
    };
  }, [open]);

  // El reconocimiento de voz se crea una vez. En Firefox no existe y el botón no se dibuja:
  // un botón permanentemente inhabilitado no ayuda.
  useEffect(() => {
    const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Reconocimiento) return;

    const rec = new Reconocimiento();
    rec.lang = "es-CO";
    rec.continuous = false;
    rec.interimResults = true; // el texto aparece mientras hablas

    rec.onresult = (e) => {
      let dicho = "";
      for (let i = 0; i < e.results.length; i++) dicho += e.results[i][0].transcript;
      setDraft(`${previoRef.current} ${dicho}`.trim());
    };
    rec.onerror = (e) => {
      setEscuchando(false);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") setErrorVoz("Falta el permiso del micrófono.");
      else if (e.error === "no-speech") setErrorVoz("No escuché nada.");
      else if (e.error !== "aborted") setErrorVoz("No pude usar el micrófono.");
    };
    rec.onend = () => setEscuchando(false);

    vozRef.current = rec;
    setSoportaVoz(true);
    return () => {
      rec.onresult = rec.onerror = rec.onend = null;
      rec.abort();
    };
  }, []);

  const alternarVoz = useCallback(() => {
    const rec = vozRef.current;
    if (!rec) return;
    if (escuchando) {
      rec.stop();
      return;
    }
    setErrorVoz(null);
    previoRef.current = draft;
    try {
      rec.start();
      setEscuchando(true);
    } catch {
      // start() lanza si ya estaba activo; el estado se corrige con onend.
    }
  }, [escuchando, draft]);

  // Cerrar o plegar el panel con el micrófono abierto lo dejaría grabando.
  useEffect(() => {
    if (!open || minimized) vozRef.current?.abort();
  }, [open, minimized]);

  const openPanel = useCallback(() => {
    clearTimeout(closeTimer.current);
    setClosing(false);
    setOpen(true);
  }, []);

  /** Marca la salida y desmonta cuando la animación termina, no antes. */
  const closePanel = useCallback(() => {
    setClosing(true);
    clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      setOpen(false);
      setClosing(false);
    }, CLOSE_MS);
  }, []);

  /** La burbuja se queda donde la sueltes; solo se impide que salga del viewport. */
  const clamp = (x, y) => ({
    x: Math.min(Math.max(x, MARGIN), window.innerWidth - BUBBLE - MARGIN),
    y: Math.min(Math.max(y, MARGIN), window.innerHeight - BUBBLE - MARGIN)
  });

  /** Igual que `clamp`, pero para una caja del tamaño del panel. */
  const clampPanel = (x, y, w, h) => ({
    x: Math.max(MARGIN, Math.min(x, window.innerWidth - w - MARGIN)),
    y: Math.max(MARGIN, Math.min(y, window.innerHeight - h - MARGIN))
  });

  useEffect(() => {
    const onResize = () => {
      setPlace((prev) => (prev ? clamp(prev.x, prev.y) : prev));
      setPanelPos((prev) => {
        const el = panelRef.current;
        if (!prev || !el) return prev;
        const r = el.getBoundingClientRect();
        return clampPanel(prev.x, prev.y, r.width, r.height);
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closePanel]);

  // Corta el streaming y el temporizador de cierre si el componente se desmonta.
  useEffect(
    () => () => {
      abortRef.current?.abort();
      clearTimeout(closeTimer.current);
    },
    []
  );

  // El hilo siempre pegado abajo mientras entra texto.
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open, minimized]);

  /** Añade texto al último mensaje del asistente, que es el que se está escribiendo. */
  const appendToLast = useCallback((delta) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, content: last.content + delta };
      return next;
    });
  }, []);

  const send = useCallback(
    async (text) => {
      const pregunta = text.trim();
      if (!pregunta || busy) return;
      // El chip es de la última respuesta que movió el mapa: si esta no lo mueve (o el chat lo rechaza), el
      // de la anterior se veía como si acabara de aplicarse.
      setFiltroAplicado(null);

      const marca = Date.now();
      const historial = [...messages, { role: "user", content: pregunta, hora: marca }];
      setMessages([...historial, { role: "assistant", content: "", hora: marca }]);
      setDraft("");
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(STREAM_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            // El saludo no es parte de la conversación y los errores tampoco.
            messages: historial
              .filter((m) => m !== SALUDO && !m.error)
              .slice(-MAX_HISTORIAL)
              .map(({ role, content }) => ({ role, content })),
            vista: vistaRef.current ?? null
          }),
          signal: controller.signal
        });

        if (!res.ok || !res.body) {
          // El backend explica qué pasó (falta la clave, no hay datos...): más útil que un "error 500".
          const detalle = await res.json().catch(() => ({}));
          throw new Error(typeof detalle.detail === "string" ? detalle.detail : `El servidor respondió ${res.status}`);
        }

        // Un envío que sale bien es la mejor prueba de que el backend responde.
        setConexion("ok");

        await leerFlujo(res, (e) => {
          if (e.error) throw new Error(e.error);
          if (e.delta) appendToLast(e.delta);
          // Llega al final del flujo, con el texto ya escrito: el mapa se mueve al cerrar la respuesta.
          if (e.accion) {
            accionRef.current?.(e.accion);
            // Se guarda la acción completa, no solo su resumen: el chip la vuelve a aplicar.
            const resumen = resumirFiltro(e.accion);
            if (resumen) setFiltroAplicado({ accion: e.accion, resumen });
          }
        });
      } catch (err) {
        if (err.name === "AbortError") return;
        // `TypeError` es el fallo de red de fetch: el servidor no contestó.
        const red = err instanceof TypeError;
        if (red) setConexion("caido");
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          // Si no alcanzó a llegar nada, la burbuja vacía se convierte en el aviso.
          next[next.length - 1] = {
            ...last,
            error: !last.content,
            content:
              last.content ||
              (red ? "No pude conectar con el asistente. Revisa que el servidor esté encendido." : `No pude responder: ${err.message}`)
          };
          return next;
        });
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [appendToLast, busy, messages]
  );

  // --- Arrastre de la burbuja ---------------------------------------------------

  const onPointerDown = useCallback((e) => {
    if (e.button != null && e.button !== 0) return;
    const el = launcherRef.current;
    if (!el) return;
    // Se parte de la caja real: mientras está indexada, el transform la desplaza.
    const r = el.getBoundingClientRect();
    dragRef.current = { dx: e.clientX - r.left, dy: e.clientY - r.top, ox: e.clientX, oy: e.clientY, moved: false };
    el.setPointerCapture(e.pointerId);
    setPlace({ x: r.left, y: r.top });
    setDragging(true);
  }, []);

  const onPointerMove = useCallback(
    (e) => {
      if (!dragging) return;
      const d = dragRef.current;
      if (!d.moved && (Math.abs(e.clientX - d.ox) > DRAG_SLOP || Math.abs(e.clientY - d.oy) > DRAG_SLOP)) d.moved = true;
      setPlace(clamp(e.clientX - d.dx, e.clientY - d.dy));
    },
    [dragging]
  );

  const endDrag = useCallback(
    (e) => {
      const el = launcherRef.current;
      if (el && e.pointerId != null && el.hasPointerCapture?.(e.pointerId)) el.releasePointerCapture(e.pointerId);
      setDragging(false);
      // Un toque sin arrastre abre el panel; con arrastre, solo mueve la burbuja.
      if (!dragRef.current.moved) openPanel();
    },
    [openPanel]
  );

  // --- Arrastre del panel abierto, tomándolo por la cabecera --------------------

  const onHeadPointerDown = useCallback(
    (e) => {
      if (pinned || (e.button != null && e.button !== 0)) return;
      // Los botones de la cabecera no arrastran: son clics.
      if (e.target.closest("button")) return;
      const el = panelRef.current;
      if (!el) return;

      const r = el.getBoundingClientRect();
      panelDragRef.current = { dx: e.clientX - r.left, dy: e.clientY - r.top, w: r.width, h: r.height };
      // Fija la posición actual antes de moverla: hasta ahora era automática.
      setPanelPos({ x: r.left, y: r.top });
      e.currentTarget.setPointerCapture(e.pointerId);
      setPanelDragging(true);
    },
    [pinned]
  );

  const onHeadPointerMove = useCallback(
    (e) => {
      if (!panelDragging) return;
      const d = panelDragRef.current;
      setPanelPos(clampPanel(e.clientX - d.dx, e.clientY - d.dy, d.w, d.h));
    },
    [panelDragging]
  );

  const endHeadDrag = useCallback((e) => {
    const el = e.currentTarget;
    if (el && e.pointerId != null && el.hasPointerCapture?.(e.pointerId)) el.releasePointerCapture(e.pointerId);
    setPanelDragging(false);
  }, []);

  /** Al plegar, congela la posición actual para que la barra no salte. */
  const toggleMinimized = useCallback(() => {
    setPanelPos((prev) => {
      if (prev) return prev;
      const r = panelRef.current?.getBoundingClientRect();
      return r ? { x: r.left, y: r.top } : prev;
    });
    setMinimized((m) => !m);
  }, []);

  const panelStyle = () => {
    if (typeof window === "undefined") return { right: MARGIN, bottom: MARGIN };

    const w = window.innerWidth;
    const h = window.innerHeight;
    const width = Math.min(PANEL_W, w - MARGIN * 2);
    const height = Math.min(PANEL_MAX_H, h - MARGIN * 2);
    // Plegado: la altura la marca la cabecera, así que se deja libre.
    const size = { width, height: minimized ? "auto" : height };

    if (panelPos) return { left: panelPos.x, top: panelPos.y, ...size };
    if (!place) return { right: MARGIN, bottom: MARGIN, ...size };

    // Sin posición propia, el panel se abre junto a la burbuja, hacia el lado con más sitio.
    const top = Math.min(Math.max(place.y + BUBBLE / 2 - height / 2, MARGIN), h - height - MARGIN);
    const left = side === "left" ? MARGIN : w - width - MARGIN;
    return { left, top, ...size };
  };

  const launcherStyle = place ? { left: place.x, top: place.y } : { right: MARGIN, bottom: MARGIN };
  const esperandoPrimerTrozo = busy && messages[messages.length - 1]?.content === "";

  return (
    <>
      {!open && (
        <button
          ref={launcherRef}
          type="button"
          className={`cb-launcher ${dragging ? "dragging" : ""}`}
          style={launcherStyle}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          aria-label="Abrir el asistente"
          title="Asistente SCR"
        >
          <MessageSquare size={22} strokeWidth={2} aria-hidden="true" />
          <span className={`cb-launcher-dot cb-dot-${estadoConexion.clase}`} aria-hidden="true"></span>
        </button>
      )}

      {open && (
        <section
          ref={panelRef}
          className={`cb-panel ${side === "left" ? "from-l" : "from-r"} ${closing ? "closing" : ""} ${minimized ? "min" : ""}`}
          style={panelStyle()}
          role="dialog"
          aria-label="Asistente SCR"
        >
          <header
            className={`cb-head ${pinned ? "pinned" : ""} ${panelDragging ? "dragging" : ""}`}
            onPointerDown={onHeadPointerDown}
            onPointerMove={onHeadPointerMove}
            onPointerUp={endHeadDrag}
            onPointerCancel={endHeadDrag}
            title={pinned ? "Fijado en su sitio" : "Arrástrame para mover el asistente"}
          >
            <span className="cb-head-ic" aria-hidden="true">
              <Bot size={18} strokeWidth={2} />
            </span>
            <div className="cb-head-t">
              <b>Asistente SCR</b>
              <span role="status">
                <i className={`cb-live cb-live-${estadoConexion.clase}`} aria-hidden="true"></i>
                {estadoConexion.texto}
              </span>
            </div>

            <div className="cb-head-acts">
              <button
                type="button"
                className={`cb-x ${pinned ? "on" : ""}`}
                onClick={() => setPinned((p) => !p)}
                aria-pressed={pinned}
                aria-label={pinned ? "Soltar el asistente" : "Fijar el asistente"}
                title={pinned ? "Soltar: vuelve a moverse" : "Fijar: no se podrá mover"}
              >
                {pinned ? <PinOff size={13} strokeWidth={2.2} aria-hidden="true" /> : <Pin size={13} strokeWidth={2.2} aria-hidden="true" />}
              </button>

              <button
                type="button"
                className="cb-x"
                onClick={toggleMinimized}
                aria-expanded={!minimized}
                aria-label={minimized ? "Restaurar el asistente" : "Minimizar el asistente"}
                title={minimized ? "Restaurar" : "Minimizar"}
              >
                {minimized ? <Maximize2 size={12} strokeWidth={2.4} aria-hidden="true" /> : <Minus size={14} strokeWidth={2.6} aria-hidden="true" />}
              </button>

              <button type="button" className="cb-x" onClick={closePanel} aria-label="Cerrar el asistente" title="Cerrar">
                <X size={14} strokeWidth={2.5} aria-hidden="true" />
              </button>
            </div>
          </header>

          {!minimized && (
            <>
              <div className="cb-body" ref={bodyRef} aria-live="polite">
                {messages.length === 1 && (
                  <div className="cb-chips">
                    {CHIPS.map((c) => (
                      <button key={c.rotulo} type="button" className="cb-chip" disabled={busy} onClick={() => send(c.pregunta)} title={c.pregunta}>
                        {c.rotulo}
                      </button>
                    ))}
                  </div>
                )}

                {messages.map((m, i) => {
                  const ultimo = i === messages.length - 1;
                  if (ultimo && esperandoPrimerTrozo) return <Pensando key={i} />;
                  // El saludo (índice 0) y los avisos de error no son una respuesta que copiar.
                  const copiable = m.role === "assistant" && i > 0 && !m.error && !(ultimo && busy);
                  return (
                    <React.Fragment key={i}>
                      <div className={`cb-msg ${m.role === "user" ? "me" : "bot"}${m.error ? " err" : ""}`}>{conNegritas(m.content)}</div>
                      {m.hora && (
                        <time className={`cb-hora ${m.role === "user" ? "me" : "bot"}`} dateTime={new Date(m.hora).toISOString()}>
                          {horaDe(m.hora)}
                        </time>
                      )}
                      {copiable && <Acciones texto={m.content} />}
                    </React.Fragment>
                  );
                })}

                {filtroAplicado && (
                  <button
                    type="button"
                    className="cb-filtro"
                    onClick={() => accionRef.current?.(filtroAplicado.accion)}
                    title="Volver a aplicar este filtro en el mapa"
                    aria-label={`Volver a aplicar el filtro: ${filtroAplicado.resumen}`}
                  >
                    <Crosshair size={12} strokeWidth={2.2} aria-hidden="true" />
                    <span>
                      Mapa filtrado: <b>{filtroAplicado.resumen}</b>
                    </span>
                  </button>
                )}
              </div>

              <footer className="cb-foot">
                <form
                  className="cb-input"
                  onSubmit={(e) => {
                    e.preventDefault();
                    vozRef.current?.abort();
                    send(draft);
                  }}
                >
                  <input
                    type="text"
                    value={draft}
                    onChange={(e) => {
                      setDraft(e.target.value);
                      if (errorVoz) setErrorVoz(null); // si ya está escribiendo, sobra el aviso
                    }}
                    placeholder={escuchando ? "Escuchando…" : "¿Cómo puedo ayudarte hoy?"}
                    aria-label="Consulta para el asistente"
                    disabled={busy}
                    maxLength={2000}
                  />

                  {soportaVoz && (
                    <button
                      type="button"
                      className={`cb-mic ${escuchando ? "on" : ""}`}
                      onClick={alternarVoz}
                      disabled={busy}
                      aria-pressed={escuchando}
                      aria-label={escuchando ? "Detener el dictado" : "Dictar por voz"}
                      title={escuchando ? "Detener" : "Dictar por voz"}
                    >
                      <Mic size={15} strokeWidth={2.2} aria-hidden="true" />
                    </button>
                  )}

                  <button type="submit" className="cb-send" disabled={busy || !draft.trim()} aria-label="Enviar consulta">
                    <Send size={15} strokeWidth={2.2} aria-hidden="true" />
                  </button>
                </form>
                <p className={`cb-legal ${errorVoz ? "err" : ""}`}>{errorVoz || "Las respuestas las genera un modelo IA. Verifica antes de operar."}</p>
              </footer>
            </>
          )}
        </section>
      )}
    </>
  );
}
