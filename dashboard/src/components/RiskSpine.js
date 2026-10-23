"use client";

import React, { useState } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";

import { useTheme, riskColor as riskColorOf, riskInk } from "@/lib/theme";

export default function RiskSpine({
  ELIG,
  st,
  dim,
  onFilterChange,
  onSelectBarrio,
  V = {}
}) {
  const [q, setQ] = useState("");
  const { palette: P } = useTheme();

  const num = (val) => Math.round(val).toLocaleString("es-CO");
  const pct = (val) => val.toFixed(1).replace(".", ",");

  const riskColor = (r) => riskColorOf(P, r);

  const barrioName = (b) => dim.barrios[b].split(" | ")[1];
  const barrioMuni = (b) => dim.barrios[b].split(" | ")[0];

  // Filtering based on search query
  let rows = ELIG.slice();
  if (q) {
    rows = rows.filter(([b]) =>
      dim.barrios[b].toLowerCase().includes(q.toLowerCase())
    );
  }

  // Sorting
  const sortFns = {
    risk: (x, y) => (y[1].risk ?? -1) - (x[1].risk ?? -1),
    tot: (x, y) => y[1].tot - x[1].tot,
    fa: (x, y) => y[1].faPct - x[1].faPct,
    ef: (x, y) => x[1].efPct - y[1].efPct
  };
  rows.sort(sortFns[st.spineSort] || sortFns.risk);

  const hsCount = rows.filter(([, o]) => o.risk >= st.hotspot).length;

  const ctx = [];
  if (st.zona !== "") ctx.push(dim.zonas[+st.zona]);
  if (st.muni !== "") ctx.push(dim.munis[+st.muni]);
  if (st.brig !== "") ctx.push(dim.brigs[+st.brig]);
  if (st.tipo !== "") ctx.push(dim.tipos[+st.tipo]);

  return (
    <aside id="left">
      <div className="lh">
        <h3>
          Cola de triaje por riesgo <em id="hotCount">{hsCount}</em>
        </h3>
        <p>Municipios ordenados por índice de riesgo operativo. Lo más crítico, siempre arriba.</p>
        <input
          id="spineSearch"
          placeholder="Buscar municipio…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="lctl">
        <div className="f">
          <label>Mín. {V.ordenMin || "orden"}es</label>
          <input
            type="number"
            id="minOrders"
            value={st.minOrders}
            min="1"
            max="500"
            onChange={(e) => onFilterChange("minOrders", +e.target.value)}
          />
        </div>
        <div className="f rgw">
          <label>
            Umbral hotspot · <span id="hotLabel">{st.hotspot}</span>
          </label>
          <input
            type="range"
            id="hotspot"
            min="10"
            max="95"
            value={st.hotspot}
            onChange={(e) => onFilterChange("hotspot", +e.target.value)}
          />
        </div>
      </div>

      <div className="lctl">
        <div className="f" style={{ flex: 1 }}>
          <label>Ordenar por</label>
          <select
            id="spineSort"
            value={st.spineSort}
            onChange={(e) => onFilterChange("spineSort", e.target.value)}
          >
            <option value="risk">Riesgo ↓</option>
            <option value="tot">{V.ordenes || "Órdenes"} ↓</option>
            <option value="fa">% Fallidas ↓</option>
            <option value="ef">Efectividad ↑</option>
          </select>
        </div>
      </div>

      <div id="spineCount">
        {ctx.length ? (
          <b className="flt">{ctx.join(" · ")}</b>
        ) : (
          <span className="flt-off">Toda la operación</span>
        )}{" "}
        · {rows.length} municipios · ≥{st.minOrders} {V.ordenMin || "orden"}es
      </div>

      <div id="spine">
        {rows.slice(0, 400).map(([b, o]) => {
          const hot = o.risk >= st.hotspot;
          const efW = (o.ef / o.tot) * 100;
          const faW = (o.fa / o.tot) * 100;
          const tr =
            o.trend > 2 ? (
              <span className="tr up">
                <TrendingUp size={11} strokeWidth={2.4} aria-hidden="true" /> {pct(o.trend)}pp
              </span>
            ) : o.trend < -2 ? (
              <span className="tr dn">
                <TrendingDown size={11} strokeWidth={2.4} aria-hidden="true" />{" "}
                {pct(Math.abs(o.trend))}pp
              </span>
            ) : (
              ""
            );

          return (
            <div
              key={b}
              className={`sp-row${hot ? " hot" : ""}${
                st.selBarrio === b ? " sel" : ""
              }`}
              onClick={() => onSelectBarrio(b)}
            >
              <div
                className="sp-risk"
                style={{ background: riskColor(o.risk), color: riskInk(P, o.risk) }}
              >
                {o.risk}
              </div>
              <div className="sp-body">
                <div className="sp-t">
                  {hot && <span className="dot"></span>}
                  {barrioName(b)}
                  <span className="sp-m">{barrioMuni(b)}</span>
                </div>
                <div className="sp-bar">
                  <i style={{ width: `${efW}%`, background: P.st[0] }}></i>
                  <i style={{ width: `${faW}%`, background: P.st[1] }}></i>
                </div>
                <div className="sp-f">
                  <span>{num(o.tot)} {V.ordenMin || "orden"}es</span>
                  <span className="sp-fa">{pct(o.faPct)}% fallidas</span>
                  {tr}
                </div>
              </div>
            </div>
          );
        })}
        {!rows.length && (
          <p className="empty">
            Ningún municipio alcanza el mínimo de {st.minOrders} {V.ordenMin || "orden"}es con los
            filtros actuales. Baja el umbral o amplía el rango de fechas.
          </p>
        )}
      </div>
    </aside>
  );
}
