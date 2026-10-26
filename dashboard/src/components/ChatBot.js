"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Send, X } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const STREAM_ENDPOINT = `${API_URL}/api/v1/openai/chat/stream`;
const HEALTH_ENDPOINT = `${API_URL}/health`;

// Con el chat cerrado se sondea más espaciado: nadie está esperando una respuesta.
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
const PENSANDO = ["Pensando…", "Revisando los datos…", "Cruzando los datos del tablero…", "Sigo en ello, dame un momento…"];
const PENSANDO_MS = 2800;

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

function Pensando() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((v) => Math.min(v + 1, PENSANDO.length - 1)), PENSANDO_MS);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="cb-thinking">
      <span key={i} className="cb-thinking-t">{PENSANDO[i]}</span>
    </span>
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

export default function ChatBot({ vista }) {
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState([SALUDO]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [estado, setEstado] = useState("wait"); // wait | on | off
  const cuerpo = useRef(null);
  const abortar = useRef(null);
  // El tablero cambia de filtros sin avisar al chat: se lee al enviar, no al montar.
  const vistaRef = useRef(vista);
  useEffect(() => {
    vistaRef.current = vista;
  });

  useEffect(() => {
    let vivo = true;
    const sondear = async () => {
      const ctl = new AbortController();
      const corte = setTimeout(() => ctl.abort(), PING_TIMEOUT_MS);
      try {
        const r = await fetch(HEALTH_ENDPOINT, { signal: ctl.signal });
        if (vivo) setEstado(r.ok ? "on" : "off");
      } catch {
        if (vivo) setEstado("off");
      } finally {
        clearTimeout(corte);
      }
    };
    sondear();
    const t = setInterval(sondear, abierto ? PING_MS : PING_CERRADO_MS);
    return () => {
      vivo = false;
      clearInterval(t);
    };
  }, [abierto]);

  useEffect(() => () => abortar.current?.abort(), []);

  useEffect(() => {
    const el = cuerpo.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [mensajes, abierto]);

  const enviar = useCallback(
    async (pregunta) => {
      const q = pregunta.trim();
      if (!q || enviando) return;
      const previos = mensajes.filter((m) => m !== SALUDO && !m.error);
      const turnos = [...previos, { role: "user", content: q }].slice(-MAX_HISTORIAL);
      setMensajes((ms) => [...ms, { role: "user", content: q }, { role: "assistant", content: "" }]);
      setTexto("");
      setEnviando(true);

      const ctl = new AbortController();
      abortar.current = ctl;
      const escribir = (fn) =>
        setMensajes((ms) => {
          const copia = ms.slice();
          copia[copia.length - 1] = fn(copia[copia.length - 1]);
          return copia;
        });

      try {
        const r = await fetch(STREAM_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: turnos.map(({ role, content }) => ({ role, content })),
            vista: vistaRef.current
          }),
          signal: ctl.signal
        });
        if (!r.ok) {
          const detalle = await r.json().catch(() => ({}));
          throw new Error(typeof detalle.detail === "string" ? detalle.detail : `El servidor respondió ${r.status}.`);
        }
        await leerFlujo(r, (e) => {
          if (e.delta) escribir((m) => ({ ...m, content: m.content + e.delta }));
          if (e.error) escribir((m) => ({ ...m, content: e.error, error: true }));
        });
      } catch (err) {
        if (err.name === "AbortError") return;
        const msg = err instanceof TypeError ? "No pude conectar con el asistente. Revisa que el servidor esté encendido." : err.message;
        escribir((m) => ({ ...m, content: msg, error: true }));
      } finally {
        setEnviando(false);
      }
    },
    [mensajes, enviando]
  );

  const sinConversar = mensajes.length === 1;
  const etiquetaEstado = { on: "En línea", off: "Sin conexión", wait: "Conectando…" }[estado];

  return (
    <>
      {!abierto && (
        <button type="button" className="cb-launcher" onClick={() => setAbierto(true)} aria-label="Abrir el asistente" title="Asistente">
          <Bot size={26} aria-hidden="true" />
          <span className={`cb-launcher-dot ${estado === "off" ? "cb-dot-off" : estado === "wait" ? "cb-dot-wait" : ""}`} />
        </button>
      )}

      {abierto && (
        <section className="cb-panel" role="dialog" aria-label="Asistente del tablero">
          <header className="cb-head">
            <div className="cb-head-ic"><Bot size={18} aria-hidden="true" /></div>
            <div className="cb-head-t">
              <b>Asistente SCR</b>
              <span>
                <i className={`cb-live ${estado === "off" ? "cb-live-off" : estado === "wait" ? "cb-live-wait" : ""}`} />
                {etiquetaEstado}
              </span>
            </div>
            <button type="button" className="cb-x" onClick={() => setAbierto(false)} aria-label="Cerrar el asistente">
              <X size={14} aria-hidden="true" />
            </button>
          </header>

          <div className="cb-body" ref={cuerpo} aria-live="polite">
            {mensajes.map((m, i) => (
              <div key={i} className={`cb-msg ${m.role === "user" ? "me" : "bot"}${m.error ? " err" : ""}`}>
                {m.content ? conNegritas(m.content) : <Pensando />}
              </div>
            ))}
            {sinConversar && (
              <div className="cb-chips">
                {CHIPS.map((c) => (
                  <button key={c.rotulo} type="button" className="cb-chip" onClick={() => enviar(c.pregunta)}>
                    {c.rotulo}
                  </button>
                ))}
              </div>
            )}
          </div>

          <footer className="cb-foot">
            <form
              className="cb-input"
              onSubmit={(e) => {
                e.preventDefault();
                enviar(texto);
              }}
            >
              <input
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Pregunta sobre las órdenes…"
                disabled={enviando}
                aria-label="Tu pregunta"
                maxLength={2000}
              />
              <button type="submit" className="cb-send" disabled={enviando || !texto.trim()} aria-label="Enviar">
                <Send size={15} aria-hidden="true" />
              </button>
            </form>
          </footer>
        </section>
      )}
    </>
  );
}
