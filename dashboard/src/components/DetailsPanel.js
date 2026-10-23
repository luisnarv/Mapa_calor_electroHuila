"use client";

import React, { useState } from "react";
import { Info, Star } from "lucide-react";

import { useTheme, riskColor as riskColorOf, riskInk } from "@/lib/theme";

export default function DetailsPanel({
  st,
  A,
  ELIG,
  dim,
  geo,
  dayLabel,
  recommend,
  techRoute,
  zoneAvg,
  actionsFor,
  onFilterChange,
  onSelectBarrio,
  V = {}
}) {
  // Controla si el panel de detalles está desplegado u oculto (empieza oculto)
  const [collapsed, setCollapsed] = useState(true);
  const { palette: P } = useTheme();

  const num = (val) => Math.round(val).toLocaleString("es-CO");
  const pct = (val) => val.toFixed(1).replace(".", ",");
  const delta = (v, ref) => {
    const d = v - ref;
    const cls = d > 0 ? "ok" : "bad";
    return (
      <span className={`dl ${Math.abs(d) < 3 ? "" : cls}`}>
        {d >= 0 ? "+" : ""}
        {pct(d)} pp
      </span>
    );
  };

  const riskColor = (r) => riskColorOf(P, r);

  /* Estados: relleno de marca para barras y leyendas */
  const ST_COLOR = P.st;

  const barrioName = (b) => dim.barrios[b].split(" | ")[1];
  const barrioMuni = (b) => dim.barrios[b].split(" | ")[0];

  const miniTable = (rows, heads) => {
    if (!rows.length) return <p className="empty">Sin datos.</p>;
    return (
      <table className="mt">
        <thead>
          <tr>
            {heads.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr key={rIdx}>
              {row.map((cell, cIdx) => (
                <td key={cIdx} className={cIdx ? "num" : ""}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const topList = (map_, k = 5) => {
    return [...map_.entries()].sort((a, b) => b[1] - a[1]).slice(0, k);
  };

  // --- 1. MUNICIPIO / GLOBAL PANEL ---
  const renderBarrio = () => {
    const b = st.selBarrio;

    // GLOBAL OVERVIEW
    if (b == null) {
      const badTot = A.tot - A.ef;
      const causes = [...A.causa.entries()]
        .filter(([c]) => dim.causas[c] !== "Efectiva")
        .sort((x, y) => y[1] - x[1]);
      const topRisky = ELIG.slice()
        .sort((x, y) => (y[1].risk ?? -1) - (x[1].risk ?? -1))
        .slice(0, 5);
      const subRows = [...A.sub.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);

      return (
        <>
          <div className="pb-head" style={{ marginBottom: "12px" }}>
            <div
              className="pb-risk"
              style={{
                background: "var(--badge-bg)",
                width: "38px",
                height: "38px",
                fontSize: "14px",
                flex: "0 0 38px",
                color: "var(--badge-tx)",
                fontWeight: "600"
              }}
            >
              GLO
            </div>
            <div>
              <h2>Resumen de Operación</h2>
              <span className="pb-sub">
                {st.zona === "" ? "Todo el departamento" : "Zona: " + dim.zonas[+st.zona]}{" "}
                &middot; {st.muni === "" ? "Todos los municipios" : dim.munis[+st.muni]}
              </span>
            </div>
          </div>

          <div className="mini-grid" style={{ marginBottom: "14px" }}>
            <div className="mini">
              <span>Total</span>
              <b>{num(A.tot)}</b>
            </div>
            <div className="mini">
              <span>Efectivas</span>
              <b className="ok">{num(A.ef)}</b>
            </div>
            <div className="mini">
              <span>Fallidas</span>
              <b className="warn">{num(A.fa)}</b>
            </div>
          </div>

          <h3>Efectividad Global</h3>
          <table className="cmp" style={{ marginBottom: "14px" }}>
            <tbody>
              <tr>
                <td>Efectividad</td>
                <td className="num ok" style={{ fontWeight: "600" }}>
                  {pct(A.efPct)}%
                </td>
              </tr>
              <tr>
                <td>Tasa de fallas</td>
                <td className="num warn">{pct(A.faPct)}%</td>
              </tr>
            </tbody>
          </table>

          <h3>
            Municipios con mayor riesgo <span className="hint">clic para analizar</span>
          </h3>
          {topRisky.length ? (
            <table className="mt rk" style={{ marginBottom: "14px" }}>
              <thead>
                <tr>
                  <th>Municipio</th>
                  <th>Zona</th>
                  <th className="num">Riesgo</th>
                </tr>
              </thead>
              <tbody>
                {topRisky.map(([bIdx, o]) => (
                  <tr
                    key={bIdx}
                    className="clk"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectBarrio(bIdx);
                    }}
                  >
                    <td>{barrioName(bIdx)}</td>
                    <td className="dim">{barrioMuni(bIdx)}</td>
                    <td className="num">
                      <span
                        className="pill"
                        style={{ background: riskColor(o.risk), color: riskInk(P, o.risk) }}
                      >
                        {o.risk}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty" style={{ marginBottom: "14px" }}>
              Sin municipios con muestra suficiente.
            </p>
          )}

          <h3>
            Motivos de no efectividad <span className="hint">{num(badTot)} {V.ordenMin || "orden"}es</span>
          </h3>
          <div className="causes" style={{ marginBottom: "14px" }}>
            {causes.slice(0, 5).map(([c, n]) => {
              const p = badTot ? (n / badTot) * 100 : 0;
              return (
                <div key={c} className="cz">
                  <span className="cz-n">
                    {dim.causas[c]}{" "}
                  </span>
                  <i>
                    <b
                      style={{
                        width: `${p}%`,
                        background: P.series[1]
                      }}
                    ></b>
                  </i>
                  <span className="cz-v">
                    {pct(p)}% <em>{num(n)}</em>
                  </span>
                </div>
              );
            })}
            {!causes.length && (
              <p className="empty" style={{ marginBottom: "14px" }}>
                Sin {V.ordenMin || "orden"}es no efectivas.
              </p>
            )}
          </div>

          <h3>
            Distribución de trabajo realizado <span className="hint">efectivas</span>
          </h3>
          {A.ef
            ? miniTable(
                subRows.map(([s, n]) => [
                  dim.subs[s],
                  num(n),
                  pct((n / A.ef) * 100) + "%"
                ]),
                [V.subaccion || "Subacción", V.ordenes || "Órdenes", "Part."]
              )
            : <p className="empty">Sin datos.</p>}

          <p
            className="hint"
            style={{ marginTop: "16px", lineHeight: "1.45", color: "var(--dim)" }}
          >
            * Selecciona un municipio en la columna de riesgo o haz clic en cualquier
            círculo del mapa para ver el diagnóstico específico de esa zona.
          </p>
        </>
      );
    }

    // SPECIFIC MUNICIPIO OVERVIEW
    const o = A.barrio.get(b);
    if (!o) {
      return (
        <p className="empty">
          Ese municipio no tiene {V.ordenMin || "orden"}es con los filtros actuales.
        </p>
      );
    }

    const z = zoneAvg(dim.b_zona[b]);
    const zonaN = dim.zonas[dim.b_zona[b]];

    const causes = [...o.causa.entries()]
      .filter(([c]) => dim.causas[c] !== "Efectiva")
      .sort((x, y) => y[1] - x[1]);
    const badTot = o.tot - o.ef;

    const acts = actionsFor(b, o, z);
    const recT = recommend(b, st.tipo === "" ? -1 : +st.tipo, "tec").slice(0, 3);

    // local effective technicians
    const localTechs = [...o.tecEf.entries()]
      .map(([t, s]) => {
        return {
          t,
          tot: s.tot,
          ef: s.ef,
          efPct: s.tot > 0 ? (s.ef / s.tot) * 100 : 0
        };
      })
      .filter((r) => r.tot >= 3 && !dim.tecInvalido[r.t])
      .sort((a, b) => b.efPct - a.efPct);

    return (
      <>
        <div className="pb-head">
          <div
            className="pb-risk"
            style={{ background: riskColor(o.risk), color: riskInk(P, o.risk) }}
          >
            {o.risk ?? "—"}
          </div>
          <div>
            <h2>{barrioName(b)}</h2>
            <span className="pb-sub">
              {zonaN} · Prioridad{" "}
              <b style={{ color: riskColorOf(P, o.risk, true) }}>
                {o.prio ?? "muestra insuficiente"}
              </b>
            </span>
          </div>
        </div>

        <div className="mini-grid">
          <div className="mini">
            <span>Total</span>
            <b>{num(o.tot)}</b>
          </div>
          <div className="mini">
            <span>Efectivas</span>
            <b className="ok">{num(o.ef)}</b>
          </div>
          <div className="mini">
            <span>Fallidas</span>
            <b className="warn">{num(o.fa)}</b>
          </div>
        </div>

        <h3>Comparación contra la zona {zonaN}</h3>
        <table className="cmp">
          <thead>
            <tr>
              <th></th>
              <th>Municipio</th>
              <th>Zona</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Efectividad</td>
              <td>{pct(o.efPct)}%</td>
              <td>{pct(z.efPct)}%</td>
              <td>{delta(o.efPct, z.efPct)}</td>
            </tr>
            <tr>
              <td>% Fallidas</td>
              <td>{pct(o.faPct)}%</td>
              <td>{pct(z.faPct)}%</td>
              <td>{delta(z.faPct, o.faPct)}</td>
            </tr>
          </tbody>
        </table>

        {o.risk != null && (
          <>
            <h3>
              Composición del índice de riesgo <span className="hint">(0-100)</span>
            </h3>
            <div className="parts">
              {[
                ["% fallidas", o.parts.fa, 65],
                ["Volumen", o.parts.vol, 15],
                ["Tendencia", o.parts.tr, 10],
                ["Desempeño histórico", o.parts.hist, 10]
              ].map(([l, v, mx]) => (
                <div key={l} className="part">
                  <span>{l}</span>
                  <i>
                    <b style={{ width: `${(v / mx) * 100}%` }}></b>
                  </i>
                  <em>
                    {v.toFixed(1)}/{mx}
                  </em>
                </div>
              ))}
            </div>
          </>
        )}

        <h3>
          Acciones recomendadas{" "}
          <span className="hint" title="Sugerencias automáticas derivadas de reglas operativas sobre los datos del municipio (causas, efectividad, tendencia). No usan IA.">
            generadas por reglas operativas
          </span>
        </h3>
        <div className="acts">
          {acts.map((a, idx) => (
            <div key={idx} className={`act ${a.lvl}`}>
              <b>{a.t}</b>
              <p dangerouslySetInnerHTML={{ __html: a.d }} />
            </div>
          ))}
        </div>

        <h3>
          Motivos de no efectividad <span className="hint">{num(badTot)} {V.ordenMin || "orden"}es</span>
        </h3>
        <div className="causes">
          {causes.map(([c, n]) => {
            const p = badTot ? (n / badTot) * 100 : 0;
            return (
              <div key={c} className="cz">
                <span className="cz-n">
                  {dim.causas[c]}{" "}
                </span>
                <i>
                  <b
                    style={{
                      width: `${p}%`,
                      background: P.series[1]
                    }}
                  ></b>
                </i>
                <span className="cz-v">
                  {pct(p)}% <em>{num(n)}</em>
                </span>
              </div>
            );
          })}
          {!causes.length && <p className="empty">Sin {V.ordenMin || "orden"}es no efectivas.</p>}
        </div>

        <h3>{V.tecnico || "Técnico"} recomendado aquí</h3>
        {recT.length ? (
          <div className="recs">
            {recT.map((r, i) => (
              <div key={i} className={`rec ${i === 0 ? "best" : ""}`}>
                <div className="rec-h">
                  <b>{r.name}</b>
                  <span 
                    className={`conf ${r.conf.toLowerCase()}`}
                    title={`La confianza estadística se calcula según la cantidad de ${V.ordenMin || "orden"}es comparables:\n• Alta: 30 o más ${V.ordenMin || "orden"}es\n• Media: 10 a 29 ${V.ordenMin || "orden"}es\n• Baja: menos de 10 ${V.ordenMin || "orden"}es`}
                    style={{ cursor: "help", textDecoration: "underline dotted", display: "inline-flex", alignItems: "center", gap: "2px" }}
                  >
                    Confianza {r.conf} <Info size={11} strokeWidth={2.2} style={{ opacity: 0.8 }} aria-hidden="true" />
                  </span>
                </div>
                <div className="rec-m">
                  <span>
                    <b>{pct(r.efPct)}%</b> efectividad
                  </span>
                  <span>
                    <b>{num(r.n)}</b> {V.ordenMin || "orden"}es
                  </span>
                  <span>
                    Última:{" "}
                    {r.last >= 0
                      ? dayLabel(Math.floor(r.last / 1440))
                      : "—"}
                  </span>
                </div>
                <div className="rec-s">Base: {r.scope}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty">
            Muestra insuficiente para recomendar con fiabilidad en este municipio.
          </p>
        )}

        <h3>
          {V.tecnicos || "Técnicos"} más efectivos aquí <span className="hint">en este municipio</span>
        </h3>
        {localTechs.length
          ? miniTable(
              localTechs
                .slice(0, 6)
                .map((r) => [
                  dim.tecs[r.t],
                  num(r.tot),
                  pct(r.efPct) + "%"
                ]),
              [V.tecnico || "Técnico", V.ordenes || "Órdenes", "Efectividad aquí"]
            )
          : <p className="empty">Ningún {V.tecnicoMin || "técnico"} tiene ≥3 {V.ordenMin || "orden"}es aquí.</p>}

        <h3>
          Trabajo efectivo realizado <span className="hint">para saber qué distribuir</span>
        </h3>
        {o.ef
          ? miniTable(
              topList(o.subEf, 6).map(([s, n]) => [
                dim.subs[s],
                num(n),
                pct((n / o.ef) * 100) + "%"
              ]),
              ["Acción ejecutada", V.ordenes || "Órdenes", "Part."]
            )
          : <p className="empty">Sin {V.ordenMin || "orden"}es efectivas en este municipio.</p>}

        <h3>{V.brigadas || "Brigadas"} asignadas</h3>
        {miniTable(
          topList(o.brig, 5).map(([g, c]) => [
            dim.brigs[g],
            num(c),
            pct((c / o.tot) * 100) + "%"
          ]),
          [V.brigada || "Brigada", V.ordenes || "Órdenes", "Part."]
        )}

        <h3>{V.tiposOs || "Tipos de orden"}</h3>
        {miniTable(
          topList(o.tipo, 5).map(([t, c]) => [
            dim.tipos[t],
            num(c),
            pct((c / o.tot) * 100) + "%"
          ]),
          [V.tipoOs || "Tipo OS", V.ordenes || "Órdenes", "Part."]
        )}

        <h3>Tipos de suspensión</h3>
        {miniTable(
          topList(o.susp, 5).map(([u, c]) => [
            dim.susps[u],
            num(c),
            pct((c / o.tot) * 100) + "%"
          ]),
          ["Suspensión", V.ordenes || "Órdenes", "Part."]
        )}

        <h3>
          {V.subacciones || "Subacciones"} en no efectivas <span className="hint">{num(badTot)} {V.ordenMin || "orden"}es</span>
        </h3>
        {miniTable(
          topList(o.sub, 6).map(([sx, c]) => [
            dim.subs[sx],
            num(c),
            badTot ? pct((c / badTot) * 100) + "%" : "—"
          ]),
          [V.subaccion || "Subacción", "No efect.", "Part."]
        )}

        <h3>
          Causales en efectivas <span className="hint">distribución de lo ejecutado</span>
        </h3>
        {miniTable(
          topList(o.efTipo || new Map(), 5).map(([t, c]) => [
            dim.tipos[t],
            num(c),
            pct(o.ef ? (c / o.ef) * 100 : 0) + "%"
          ]),
          [V.tipoOs || "Tipo OS", "Efectivas", "Part."]
        )}

        <h3>
          {V.subacciones || "Subacciones"} en efectivas <span className="hint">qué se ejecutó</span>
        </h3>
        {miniTable(
          topList(o.subEf || new Map(), 6).map(([sx, c]) => [
            dim.subs[sx],
            num(c),
            pct(o.ef ? (c / o.ef) * 100 : 0) + "%"
          ]),
          [V.subaccion || "Subacción", "Efectivas", "Part."]
        )}
      </>
    );
  };

  // --- 2. TECNICO PANEL ---
  const renderTecnico = () => {
    const opts = [...A.tec.entries()]
      .sort((a, b) => b[1].tot - a[1].tot)
      .map(([t]) => (
        <option key={t} value={t}>
          {dim.tecs[t]}
        </option>
      ));

    let body = (
      <p className="empty">
        Selecciona un {V.tecnicoMin || "técnico"} para ver su cobertura, recorrido y desempeño.
      </p>
    );

    if (st.selTec != null && A.tec.has(st.selTec)) {
      const o = A.tec.get(st.selTec);
      const R = techRoute(st.selTec);
      const mainBrigList = [...o.brig.entries()].sort((a, b) => b[1] - a[1]);
      const mainBrig = mainBrigList.length ? mainBrigList[0][0] : null;
      const bo = mainBrig ? A.brig.get(mainBrig) : null;
      const brigName = mainBrig ? dim.brigs[mainBrig] : "—";
      const barrios = [...o.barrios]
        .map((b) => [barrioName(b), A.barrio.get(b)])
        .filter((x) => x[1]);

      body = (
        <>
          <div className="mini-grid">
            <div className="mini">
              <span>{V.ordenes || "Órdenes"}</span>
              <b>{num(o.tot)}</b>
            </div>
            <div className="mini">
              <span>Efectivas · {num(o.ef)}</span>
              <b className="ok">{pct(o.efPct)}%</b>
            </div>
            <div className="mini">
              <span>Fallidas · {num(o.fa)}</span>
              <b className="warn">{pct(o.faPct)}%</b>
            </div>
          </div>
          <div className="mini-grid">
            <div className="mini">
              <span>Efectividad</span>
              <b className="ok">{pct(o.efPct)}%</b>
            </div>
            <div className="mini">
              <span>Distancia</span>
              <b>{num(R.km)} km</b>
            </div>
            <div className="mini">
              <span>Mediana por {V.ordenMin || "orden"}</span>
              <b>{num(R.medMin)} min</b>
            </div>
            <div className="mini">
              <span>Días en campo</span>
              <b>{num(R.days)}</b>
            </div>
          </div>

          <h3>Distribución de resultados</h3>
          <div className="dist-bar">
            <i style={{ width: `${o.efPct}%`, background: ST_COLOR[0] }} title="Efectivas"></i>
            <i style={{ width: `${o.faPct}%`, background: ST_COLOR[1] }} title="Fallidas"></i>
          </div>
          <div className="dist-leg">
            <span>
              <i style={{ background: ST_COLOR[0] }}></i> Efectivas <b>{pct(o.efPct)}%</b>
            </span>
            <span>
              <i style={{ background: ST_COLOR[1] }}></i> Fallidas <b>{pct(o.faPct)}%</b>
            </span>
          </div>

          <h3>Comparación</h3>
          {bo && (
            <table className="cmp">
              <thead>
                <tr>
                  <th></th>
                  <th>{V.tecnico || "Técnico"}</th>
                  <th>{V.brigada || "Brigada"} {brigName}</th>
                  <th>Δ</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Efectividad</td>
                  <td>{pct(o.efPct)}%</td>
                  <td>{pct(bo.efPct)}%</td>
                  <td>{delta(o.efPct, bo.efPct)}</td>
                </tr>
              </tbody>
            </table>
          )}

          <h3>{V.brigadas || "Brigadas"} con las que trabaja</h3>
          {miniTable(
            [...o.brig.entries()]
              .sort((a, b) => b[1] - a[1])
              .map(([g, c]) => [
                dim.brigs[g],
                num(c),
                pct((c / o.tot) * 100) + "%"
              ]),
            [V.brigada || "Brigada", V.ordenes || "Órdenes", "Part."]
          )}

          <h3>
            Municipios atendidos <span className="hint">{barrios.length}</span>
          </h3>
          {miniTable(
            barrios
              .sort((a, b) => b[1].tot - a[1].tot)
              .slice(0, 12)
              .map(([nm, bo]) => [nm, num(bo.tot), pct(bo.efPct) + "%"]),
            ["Municipio", V.ordenes || "Órdenes", "Efect."]
          )}

          <h3>Motivos de no efectividad</h3>
          {miniTable(
            topList(o.causa, 8)
              .filter(([c]) => dim.causas[c] !== "Efectiva")
              .slice(0, 6)
              .map(([c, n]) => [dim.causas[c], num(n)]),
            ["Causa", V.ordenes || "Órdenes"]
          )}
        </>
      );
    }

    return (
      <>
        <div className="sel-wrap">
          <label>{V.tecnico || "Técnico"}</label>
          <select
            id="tecSel"
            value={st.selTec ?? ""}
            onChange={(e) =>
              onFilterChange("selTec", e.target.value === "" ? null : +e.target.value)
            }
          >
            <option value="">— elegir —</option>
            {opts}
          </select>
        </div>
        {body}
      </>
    );
  };

  // --- 3. RECOMENDADOR PANEL ---
  const renderRecomendador = () => {
    const bopts = [...A.barrio.entries()]
      .sort((a, b) => b[1].tot - a[1].tot)
      .map(([b]) => (
        <option key={b} value={b}>
          {barrioName(b)} — {barrioMuni(b)}
        </option>
      ));

    const topts = dim.tipos.map((t, i) => (
      <option key={i} value={i}>
        {t}
      </option>
    ));

    let body = (
      <p className="empty">
        Elige un municipio y una {V.tipoOsMin || "clase de servicio"} para recibir la asignación sugerida.
      </p>
    );

    if (st.selBarrio != null) {
      const tp = st.tipo === "" ? -1 : +st.tipo;
      const rt = recommend(st.selBarrio, tp, "tec");
      const rb = recommend(st.selBarrio, tp, "brig");

      const card = (r, i, kind) => (
        <div key={i} className={`rec ${i === 0 ? "best" : ""}`}>
          <div className="rec-h">
            <b style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
              {i === 0 && (
                <Star size={12} strokeWidth={2.2} fill="currentColor" aria-hidden="true" />
              )}
              {r.name}
            </b>
            <span 
              className={`conf ${r.conf.toLowerCase()}`}
              title={`La confianza estadística se calcula según la cantidad de ${V.ordenMin || "orden"}es comparables:\n• Alta: 30 o más ${V.ordenMin || "orden"}es\n• Media: 10 a 29 ${V.ordenMin || "orden"}es\n• Baja: menos de 10 ${V.ordenMin || "orden"}es`}
              style={{ cursor: "help", textDecoration: "underline dotted", display: "inline-flex", alignItems: "center", gap: "2px" }}
            >
              Confianza {r.conf} <Info size={11} strokeWidth={2.2} style={{ opacity: 0.8 }} aria-hidden="true" />
            </span>
          </div>
          <div className="rec-m">
            <span>
              <b>{pct(r.efPct)}%</b> efectividad
            </span>
            <span>
              <b>{num(r.n)}</b> {V.ordenMin || "orden"}es
            </span>
            <span>
              Última:{" "}
              {r.last >= 0 ? dayLabel(Math.floor(r.last / 1440)) : "—"}
            </span>
          </div>
          <div className="rec-s">
            Base: {r.scope} &middot; puntaje Wilson {pct(r.score)}
          </div>
        </div>
      );

      body = (
        <>
          <h3>{V.tecnico || "Técnico"} recomendado</h3>
          {rt.length ? (
            <div className="recs">
              {rt.slice(0, 4).map((r, i) => card(r, i, "tec"))}
            </div>
          ) : (
            <p className="empty">
              Muestra insuficiente: no hay suficientes {V.ordenMin || "orden"}es comparables para recomendar con fiabilidad.
            </p>
          )}

          <h3>{V.brigada || "Brigada"} recomendada</h3>
          {rb.length ? (
            <div className="recs">
              {rb.slice(0, 3).map((r, i) => card(r, i, "brig"))}
            </div>
          ) : (
            <p className="empty">Muestra insuficiente.</p>
          )}

          <p className="hint">
            El puntaje usa el <b>límite inferior de Wilson (95%)</b> sobre la
            efectividad.
          </p>
        </>
      );
    }

    return (
      <>
        <div className="sel-wrap">
          <label>Municipio</label>
          <select
            id="recBarrio"
            value={st.selBarrio ?? ""}
            onChange={(e) =>
              onFilterChange("selBarrio", e.target.value === "" ? null : +e.target.value)
            }
          >
            <option value="">— elegir —</option>
            {bopts}
          </select>
        </div>
        <div className="sel-wrap">
          <label>{V.tipoOs || "Tipo de orden"}</label>
          <select
            id="recTipo"
            value={st.tipo}
            onChange={(e) => onFilterChange("tipo", e.target.value)}
          >
            <option value="">Todos</option>
            {topts}
          </select>
        </div>
        {body}
      </>
    );
  };

  const renderNic = () => {
    const nicVal = st.selNic;
    if (!nicVal) {
      return (
        <p className="empty">
          Ninguna {(V.cuenta || "cuenta").toLowerCase()} seleccionada. Haz clic en un punto GPS real en el mapa para ver su historial detallado.
        </p>
      );
    }

    const { E_raw, C_raw, S_raw, T_raw, DAY_raw, M_raw, ORD_raw, B_raw, NIC_raw } = st;
    const history = [];

    if (NIC_raw) {
      const N = NIC_raw.length;
      for (let i = 0; i < N; i++) {
        if (NIC_raw[i] === nicVal) {
          history.push({
            idx: i,
            ord: ORD_raw[i],
            est: E_raw[i],
            causa: dim.causas[C_raw[i]],
            sub: dim.subs[S_raw[i]],
            tec: dim.tecs[T_raw[i]],
            m: M_raw[i],
            day: DAY_raw[i],
            barrio: barrioName(B_raw[i]),
            muni: barrioMuni(B_raw[i])
          });
        }
      }
    }

    history.sort((a, b) => b.m - a.m);
    const clientInfo = history[0] || {};

    const tableRows = history.map((h) => {
      const hh = String(Math.floor((h.m % 1440) / 60)).padStart(2, "0");
      const mm = String(h.m % 60).padStart(2, "0");
      const estClass = h.est === 0 ? "ok" : "warn";
      return [
        <span className="mono" style={{ fontSize: "10.5px" }}>{h.ord || "—"}</span>,
        <span className={estClass} style={{ fontWeight: "600" }}>{dim.estados[h.est]}</span>,
        `${dayLabel(h.day)} ${hh}:${mm}`,
        <span style={{ display: "block", fontSize: "10px", lineHeight: "1.1" }}>
          <b>{h.causa}</b>
          <span style={{ display: "block", color: "var(--dim)", marginTop: "2px" }}>{h.sub}</span>
        </span>,
        h.tec
      ];
    });

    return (
      <>
        <div className="pb-head" style={{ marginBottom: "14px" }}>
          <div
            className="pb-risk"
            style={{
              background: "var(--badge-bg)",
              width: "38px",
              height: "38px",
              fontSize: "13px",
              flex: "0 0 38px",
              color: "var(--badge-tx)",
              fontWeight: "600"
            }}
          >
            {V.cuenta || "Cuenta"}
          </div>
          <div>
            <h2 style={{ fontSize: "15px" }}>{V.cuenta || "Cuenta"} {nicVal}</h2>
            <span className="pb-sub">
              {clientInfo.barrio || "—"} &middot; {clientInfo.muni || "—"}
            </span>
          </div>
        </div>

        <div className="mini-grid" style={{ marginBottom: "14px" }}>
          <div className="mini">
            <span>Visitas</span>
            <b>{history.length}</b>
          </div>
          <div className="mini">
            <span>Efectivas</span>
            <b className="ok">{history.filter(h => h.est === 0).length}</b>
          </div>
          <div className="mini">
            <span>Fallidas</span>
            <b className="warn">{history.filter(h => h.est === 1).length}</b>
          </div>
        </div>

        <h3>Historial de {V.ordenes || "Órdenes"}</h3>
        <div className="tbl-wrap" style={{ overflowX: "auto", border: "1px solid var(--line)", borderRadius: "var(--r)", background: "var(--pan2)", maxHeight: "400px" }}>
          {miniTable(tableRows, [V.orden || "Orden", "Estado", "Fecha/Hora", "Clasificación", V.tecnico || "Técnico"])}
        </div>
      </>
    );
  };

  return (
    <aside id="right">
      <div className="ph">
        <button
          className={`ptab ${st.tab === "barrio" ? "on" : ""}`}
          onClick={() => onFilterChange("tab", "barrio")}
        >
          Análisis de municipio
        </button>
        <button
          className={`ptab ${st.tab === "tecnico" ? "on" : ""}`}
          onClick={() => onFilterChange("tab", "tecnico")}
        >
          Cobertura del {V.tecnicoMin || "técnico"}
        </button>
        <button
          className={`ptab ${st.tab === "recomendador" ? "on" : ""}`}
          onClick={() => onFilterChange("tab", "recomendador")}
        >
          Recomendador
        </button>
        {st.selNic && (
          <button
            className={`ptab ${st.tab === "nic" ? "on" : ""}`}
            onClick={() => onFilterChange("tab", "nic")}
          >
            Historial de la {(V.cuenta || "cuenta").toLowerCase()}
          </button>
        )}
      </div>
      <div id="panelBody">
        {st.tab === "barrio" && renderBarrio()}
        {st.tab === "tecnico" && renderTecnico()}
        {st.tab === "recomendador" && renderRecomendador()}
        {st.tab === "nic" && renderNic()}
      </div>
    </aside>
  );
}