/**
 * Traduce el payload del ETL de ElectroHuila al contrato que espera el tablero.
 *
 * El tablero clasifica cada registro en solo dos clases: 0 efectiva · 1 fallida.
 * El diccionario oficial de códigos de ElectroHuila decide qué se ejecutó; el ETL
 * deja el resultado en `pts.gr` (grupo) más `dim.grupoNumerador`. Todo lo que no
 * se logró y sí había que ejecutar cuenta como fallida; «no aplica» queda fuera.
 *
 *  - NUMERADOR=1 → 0 (ejecutada)
 *  - DENOMINADOR=1 sin numerador → 1 (fallida)
 *  - resto (no procedía / sin información) → no entra
 *
 * La «unidad» que el tablero llama barrio es aquí el municipio (ver el CONTEXTO:
 * no hay polígonos de barrio que cubran Neiva).
 */

export const ESTADOS = ["Efectiva", "Fallida"];

// Observaciones que dicen que la suspensión SÍ se hizo (con o sin retiro de material,
// en camioneta, moto o doble moto, acometida en superficie). La base trae algunas de
// esas órdenes como FALLIDA aunque la observación diga lo contrario; el usuario decidió
// que prima la observación y que se cuentan como efectivas. Se deja fuera a propósito
// «EE/EN · reconexión» (es otra operación), «NI» (sin descripción) y «Se encontró
// suspendido» (no la hizo la cuadrilla).
const CODIGOS_SUSPENDIDO = new Set(["SY", "SN", "MD", "SM", "ES", "MR", "SO"]);

import NI_CON_OBSERVACION from "./ni_con_observacion.json";
import UC_POR_CAMPO from "./uc_no_web_service.json";

// EXCLUIDAS DEL CÁLCULO PORQUE NO SE HAN ASIGNADO (ni técnico ni brigada; no hay trabajo
// de campo que medir). Se descartan igual que «no aplica»:
//
//  · Bajas con canal_baja = «WEB SERVICE» (106.178 filas): baja por pago que carga la
//    interfaz sola («Suspensión no realizada ya que el usuario pagó…»). Nunca se asignó a
//    una brigada. Todas son observación «UC · usuario ya canceló», pero no al revés: 39
//    UC traen canal_baja = «CAMPO» (alguien fue al predio) y esas SÍ cuentan. El payload
//    no trae canal_baja, así que la regla es «UC salvo estos 39 documentos»
//    (`uc_no_web_service.json`, sale de la base; regenerar si se recarga la tabla).
//  · «NI» con la columna Observaciones VACÍA (35.037 filas, casi todas de cuentas
//    administrativas): código sin descripción en el catálogo y sin texto que diga qué
//    se hizo; tampoco se han asignado. ElectroHuila debe aclarar qué es NI.
//
// Una «NI» que sí trae texto en Observaciones (2.760 filas, p. ej. «SE CREA ACTA PARA
// CARGAR RECONEXIÓN») se queda: tiene explicación. El payload no trae esa columna, así que
// `ni_con_observacion.json` lista los documentos que sí la tienen (sale del plano de
// control; hay que regenerarlo si se carga un plano nuevo).
const CODIGOS_EXCLUIDOS = new Set(["UC"]);
const CODIGOS_EXCLUIDOS_SIN_OBSERVACION = new Set(["NI"]);
const DOCS_NI_CON_OBSERVACION = new Set(NI_CON_OBSERVACION);
const DOCS_UC_POR_CAMPO = new Set(UC_POR_CAMPO);

/**
 * Tipo de actividad homologado = qué se hizo + con qué brigada: «Suspensión en gabinete / con moto».
 *
 * La columna `actividad` de la base es una constante («Suspension» en todo el plano), así
 * que no sirve para filtrar. Se arma con dos datos que sí varían: el LUGAR técnico donde
 * quedó la orden (`suspension_en`: poste, gabinete, pin de corte, cañuela, o por qué no se
 * hizo) y el TIPO DE BRIGADA ya homologado. El índice es `acción × nBrigadas + brigada`.
 */
function accionDeLugar(lugar) {
  const t = String(lugar ?? "");
  const m = t.match(/ejecutada en (.+)$/i);
  if (m) return `Suspensión en ${m[1].trim().toLowerCase()}`;
  if (/caso aislado/i.test(t)) return "Suspensión (caso aislado)";
  if (/no se pudo ejecutar/i.test(t)) return "Suspensión no ejecutada (se visitó)";
  if (/no se intent/i.test(t)) return "Suspensión no intentada";
  return "Suspensión (lugar sin descripción)";
}

function fraseBrigada(nombre) {
  const n = String(nombre ?? "").toUpperCase();
  if (n === "MOTO") return "con moto";
  if (n === "CAMIONETA") return "con camioneta";
  if (n === "MOTO - DOBLE MOTO") return "con moto o doble moto";
  if (n.startsWith("PERSONAL DE PSS")) return "con persuasión especial";
  if (n === "CUALQUIERA") return "sin brigada específica";
  return "sin brigada asignada"; // SIN DATO, NA
}

/**
 * Deja solo lo que cuenta para la efectividad y deriva las columnas `e` (clase) y
 * `a` (actividad) de un bloque `pts`.
 *
 * Lo que el diccionario clasifica como «no aplica» (acta anulada, persuasión
 * especial, actualizar datos…) ni se ejecutó ni falló: no es una orden que había
 * que ejecutar. Por eso se descarta aquí, una sola vez, y no entra en ningún total,
 * tasa, ranking ni mapa. Entran las órdenes con DENOMINADOR=1 (ejecutadas y fallidas).
 */
export function adaptarPts(pts, dim) {
  const NUM = dim.grupoNumerador || [];
  const DEN = dim.grupoDenominador || [];
  const n = pts.e.length;
  const gr = pts.gr || new Array(n).fill(0);

  const quedan = [];
  const excluida = dim.causaExcluida || [];
  const excluidaSinObs = dim.causaExcluidaSinObservacion || [];
  for (let i = 0; i < n; i++) {
    if (DEN[gr[i]] !== 1) continue;
    const c = pts.c[i];
    if (excluida[c] && !DOCS_UC_POR_CAMPO.has(Number(pts.n[i]))) continue;
    if (excluidaSinObs[c] && !DOCS_NI_CON_OBSERVACION.has(Number(pts.n[i]))) continue;
    quedan.push(i);
  }
  const todas = quedan.length === n;
  const col = (arr) => (todas || !arr ? arr : quedan.map((i) => arr[i]));
  const p = {};
  for (const k of Object.keys(pts)) p[k] = col(pts[k]);

  const m = p.e.length;
  const e = new Array(m);
  const suspendida = dim.causaSuspendida || [];
  for (let i = 0; i < m; i++) {
    e[i] = NUM[p.gr ? p.gr[i] : 0] === 1 || suspendida[p.c[i]] ? 0 : 1;
  }
  // El tablero separa «motivos de pérdida» de lo ejecutado con una causa llamada
  // «Efectiva». Aquí las observaciones de las órdenes efectivas (p. ej. «suspensión
  // realizada») no son motivos de nada, así que se agrupan bajo esa causa; si no,
  // el panel de Causas las contaría como pérdidas y los porcentajes pasarían de 100.
  const efectiva = dim.causas.indexOf("Efectiva");
  const c = efectiva < 0 ? p.c : p.c.map((v, i) => (e[i] === 0 ? efectiva : v));
  // Tipo de brigada: «DOBLE MOTO» y «MOTO - DOBLE MOTO» se muestran como una sola opción.
  let br = dim.brigadaMap && p.br ? p.br.map((v) => dim.brigadaMap[v]) : p.br;
  // El catálogo marca «NA» en observaciones que no identifican brigada, pero cuando la
  // orden no se pudo ejecutar el lugar técnico sí la dice: NM = moto, NC = camioneta,
  // ND = doble moto (misma regla del clasificador de ElectroHuila). Solo se aplica a
  // «NA»; «CUALQUIERA» se deja como está a propósito. Lo que no tiene lugar de
  // brigada (p. ej. «Suspensión AMI» en poste) sigue como «NA».
  const na = dim.brigadas.indexOf("NA");
  if (br && na >= 0) {
    const porLugar = { NM: "MOTO", NC: "CAMIONETA", ND: "MOTO - DOBLE MOTO" };
    const idxLugar = dim.subs.map((t) => dim.brigadas.indexOf(porLugar[String(t).slice(0, 2)]));
    br = br.map((v, i) => (v === na && idxLugar[p.s[i]] >= 0 ? idxLugar[p.s[i]] : v));
  }
  // `a` es el valor de la columna `actividad` de la base (hoy «Suspension» en todo el
  // plano). `ta` es el tipo de actividad homologado (ver arriba), un filtro aparte.
  const accionDeSub = dim.accionDeSub;
  const nb = dim.brigadas.length;
  const ta = accionDeSub && br ? br.map((b, i) => accionDeSub[p.s[i]] * nb + b) : new Array(m).fill(0);
  return { ...p, e, c, br, a: p.ac || new Array(m).fill(0), ta, ci: p.ci || new Array(m).fill(0) };
}

// Siglas que deben conservarse en mayúscula al pasar una descripción a minúsculas.
const SIGLAS = new Set(["AMI"]);

/**
 * Las observaciones llegan como «EP · PERSUASION ESPECIAL». El usuario no quiere ver
 * el código, solo la descripción. Si la observación trae únicamente el código (NI, AA…)
 * no hay descripción que mostrar y se dice así, en vez de dejar un texto que parece roto.
 * La descripción no se corrige ni se completa: se muestra tal como la da el diccionario,
 * solo bajando a minúsculas las palabras que vienen enteras en mayúsculas.
 */
function limpiarCausa(raw) {
  const txt = String(raw ?? "").trim();
  const i = txt.indexOf(" · ");
  const codigo = i < 0 ? txt : txt.slice(0, i);
  const desc = i < 0 ? "" : txt.slice(i + 3).trim();
  if (!desc) {
    // «SIN DATO» ya es una descripción; los códigos cortos («NI», «00») no.
    if (/^[A-Z0-9]{1,3}$/i.test(codigo)) return { nombre: `Sin descripción en el diccionario (${codigo})`, codigo };
    return { nombre: bajar(codigo), codigo };
  }
  return { nombre: bajar(desc), codigo };
}

function bajar(t) {
  const s = t
    .split(/(\s+)/)
    .map((w) => (w.length > 1 && w === w.toUpperCase() && w !== w.toLowerCase() && !SIGLAS.has(w) ? w.toLowerCase() : w))
    .join("");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Nombres de causa sin código; si dos quedan iguales se desambigua con su código. */
function nombresCausas(brutas) {
  const limpias = brutas.map(limpiarCausa);
  const usados = new Map();
  limpias.forEach((l) => usados.set(l.nombre, (usados.get(l.nombre) || 0) + 1));
  return limpias.map((l) => (usados.get(l.nombre) > 1 ? `${l.nombre} (${l.codigo})` : l.nombre));
}

export function adaptarPayload(res) {
  const dim = res.dim;
  const causas = [...nombresCausas(dim.causas || []), "Efectiva"];
  const causaSuspendida = (dim.causas || []).map((c) => CODIGOS_SUSPENDIDO.has(limpiarCausa(c).codigo));
  const causaExcluida = (dim.causas || []).map((c) => CODIGOS_EXCLUIDOS.has(limpiarCausa(c).codigo));
  const causaExcluidaSinObservacion = (dim.causas || []).map((c) =>
    CODIGOS_EXCLUIDOS_SIN_OBSERVACION.has(limpiarCausa(c).codigo)
  );
  // El catálogo separa «doble moto» de «moto o doble moto»; para filtrar se unen.
  const unir = (n) => (n === "DOBLE MOTO" ? "MOTO - DOBLE MOTO" : n);
  const brigadas = [...new Set((dim.brigadas || []).map(unir))];
  const brigadaMap = (dim.brigadas || []).map((n) => brigadas.indexOf(unir(n)));
  const acciones = [];
  const accionDeSub = (dim.subs || []).map((t) => {
    const a = accionDeLugar(t);
    if (!acciones.includes(a)) acciones.push(a);
    return acciones.indexOf(a);
  });
  const acts = acciones.flatMap((a) => brigadas.map((b) => `${a} / ${fraseBrigada(b)}`));
  const dimAdaptada = {
    ...dim,
    brigadas,
    brigadaMap,
    causas,
    causaSuspendida,
    causaExcluida,
    causaExcluidaSinObservacion,
    // La tabla solo guarda el código del funcionario; no existe un nombre. Hay valores
    // que no son una persona («0», «SIN DATO») y no deben recomendarse.
    tecInvalido: (dim.tecCodigos || dim.tecs || []).map((t) => /^(0|na|n\/a|sin dato|)$/i.test(String(t).trim())),
    estados: ESTADOS,
    accionDeSub,
    acts: dim.actividades || [],
    tiposActividad: acts,
    // Sin familias de causa: el diccionario oficial no las define.
    causa_fam: causas.map(() => "otros")
  };
  return { ...res, dim: dimAdaptada, pts: adaptarPts(res.pts, dimAdaptada) };
}
