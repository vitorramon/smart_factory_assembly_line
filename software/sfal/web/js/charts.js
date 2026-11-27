// Gráficos em SVG usados pelas abas M1, M2 e Síntese. Cada função devolve uma string SVG.
// Cores vêm dos tokens CSS; texto sempre em tinta, nunca na cor da série; marcas têm data-tip para o hover.
import { esc, num, pct } from "./util.js";

const wrapText = (x, y, w, h, html, cls = "") => `<foreignObject x="${x}" y="${y}" width="${w}" height="${h}"><div xmlns="http://www.w3.org/1999/xhtml" class="fo ${cls}">${html}</div></foreignObject>`;

// ---------------------------------------------------------------- Pareto
// Um eixo só (% do total): a barra é a participação da categoria, a linha é o acumulado.
export function pareto(items, { unit = "falhas" } = {}) {
  const data = items.filter((i) => i.qtd > 0).sort((a, b) => b.qtd - a.qtd);
  const total = data.reduce((a, i) => a + i.qtd, 0);
  if (!total) return `<p class="hint empty">Nenhuma falha registrada ainda.</p>`;
  const W = 420, H = 250, L = 38, R = 14, T = 22, B = 54, pw = W - L - R, ph = H - T - B;
  const slot = pw / data.length, bw = Math.min(64, slot - 10);
  const y = (v) => T + ph * (1 - v);
  let acc = 0, line = "", dots = "", bars = "";
  data.forEach((d, i) => {
    const share = d.qtd / total, cx = L + slot * (i + 0.5);
    acc += share;
    const tipText = `${d.nome}: ${num(d.qtd)} ${unit} · ${pct(share)} · acumulado ${pct(acc)}`;
    bars += `<path d="M${cx - bw / 2} ${y(0)}V${y(share) + 4}q0-4 4-4h${bw - 8}q4 0 4 4V${y(0)}z" fill="var(--series)" data-tip="${esc(tipText)}"/>
      <text x="${cx}" y="${y(share) - 6}" text-anchor="middle" class="val">${num(d.qtd)}</text>`;
    bars += wrapText(cx - slot / 2 + 2, H - B + 6, slot - 4, B - 6, esc(d.nome), "axis-label");
    line += (i ? "L" : "M") + cx + " " + y(acc);
    dots += `<circle cx="${cx}" cy="${y(acc)}" r="4" fill="var(--ink)" stroke="var(--surface)" stroke-width="2" data-tip="${esc(tipText)}"/>`;
    if (i > 0 && i < data.length - 1) dots += `<text x="${cx + 7}" y="${y(acc) - 7}" class="val">${pct(acc, 0)}</text>`;
  });
  const grid = [0, 0.5, 0.8, 1].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)" ${v === 0.8 ? 'stroke-dasharray="4 3" stroke="var(--axis)"' : ""}/><text x="${L - 5}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Diagrama de Pareto">${grid}${bars}<path d="${line}" fill="none" stroke="var(--ink)" stroke-width="2"/>${dots}</svg>
    <div class="legend"><span class="sq">participação da categoria</span><span class="ln ink">acumulado</span><span class="plain">total: ${num(total)} ${unit}</span></div>`;
}

// ---------------------------------------------------------------- Radar (teia)
// series: [{nome, valores: [0..1 | null], cor: "var(--…)", tracejado?, preenchido?}]
export function radar(eixos, series, { min = 0.5, max = 1 } = {}) {
  const W = 440, H = 340, cx = W / 2, cy = H / 2 + 4, R = 118, n = eixos.length;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, v) => { const r = R * Math.max(0, Math.min(1, (v - min) / (max - min))); return [cx + Math.cos(ang(i)) * r, cy + Math.sin(ang(i)) * r]; };
  const rings = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const p = eixos.map((_, i) => [cx + Math.cos(ang(i)) * R * f, cy + Math.sin(ang(i)) * R * f].join(" ")).join("L");
    return `<path d="M${p}Z" fill="none" stroke="var(--grid)"/>${f < 1 ? `<text x="${cx + 5}" y="${cy - R * f + 12}">${num((min + (max - min) * f) * 100)}%</text>` : ""}`;
  }).join("");
  const spokes = eixos.map((e, i) => {
    const [x, y] = [cx + Math.cos(ang(i)) * R, cy + Math.sin(ang(i)) * R], [lx, ly] = [cx + Math.cos(ang(i)) * (R + 16), cy + Math.sin(ang(i)) * (R + 16)];
    const anchor = Math.abs(Math.cos(ang(i))) < 0.3 ? "middle" : Math.cos(ang(i)) > 0 ? "start" : "end";
    return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--grid)"/><text x="${lx}" y="${ly + 4}" text-anchor="${anchor}" class="axis-name">${esc(e)}</text>`;
  }).join("");
  const shapes = series.map((s) => {
    if (s.valores.some((v) => v == null)) return "";
    const pts = s.valores.map((v, i) => pt(i, v));
    const d = "M" + pts.map((p) => p.map((c) => c.toFixed(1)).join(" ")).join("L") + "Z";
    const marks = pts.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="4" fill="${s.cor}" stroke="var(--surface)" stroke-width="2" data-tip="${esc(`${s.nome} · ${eixos[i]}: ${pct(s.valores[i])}`)}"/>`).join("");
    return `<path d="${d}" fill="${s.preenchido ? s.cor : "none"}" fill-opacity=".12" stroke="${s.cor}" stroke-width="2" ${s.tracejado ? 'stroke-dasharray="6 4"' : ""} stroke-linejoin="round"/>${marks}`;
  }).join("");
  const legend = series.map((s) => `<span class="ln ${s.tracejado ? "dash" : ""}" style="--c:${s.cor}">${esc(s.nome)}${s.valores.some((v) => v == null) ? " (sem dado)" : ""}</span>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico de teia dos indicadores">${rings}${spokes}${shapes}</svg>
    <div class="legend">${legend}<span class="plain">escala de ${num(min * 100)} % a ${num(max * 100)} %</span></div>`;
}

// ---------------------------------------------------------------- Ishikawa (espinha de peixe)
// causas: [{m, causa_raiz, status?}] — até 6: três em cima, três embaixo. Cada espinha é clicável (data-cause).
export function ishikawa(efeito, causas, { selecionada = 0, comStatus = false } = {}) {
  // Cada espinha sai da categoria (em cima ou embaixo) e desce inclinada até a espinha central;
  // o texto da causa fica à esquerda dela, onde nenhuma outra espinha passa.
  const W = 1200, H = 470, spineY = 235, icon = { feito: "✔", parcial: "▲", pendente: "✕" };
  const bones = causas.slice(0, 6).map((c, i) => {
    const top = i < 3, bx = 330 + (i % 3) * 290, ex = bx - 120, ey = top ? 62 : 408;
    const sel = i === selecionada;
    const status = comStatus ? `<span class="st ${c.m3.status}">${icon[c.m3.status]} ${c.m3.status}</span>` : "";
    return `<g class="bone ${sel ? "sel" : ""}" data-cause="${i}" tabindex="0" role="button" aria-label="${esc(c.m)}">
      <line x1="${ex}" y1="${ey}" x2="${bx}" y2="${spineY}" class="rib"/>
      <rect x="${ex - 66}" y="${top ? ey - 34 : ey + 6}" width="132" height="28" rx="14" class="cat"/>
      <text x="${ex}" y="${top ? ey - 15 : ey + 25}" text-anchor="middle" class="cat-name">${esc(c.m)}</text>
      ${wrapText(ex - 192, top ? ey + 8 : ey - 128, 186, 120, `${status}<span>${esc(c.causa_raiz)}</span>`, "cause " + (top ? "" : "bottom"))}
    </g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="fish" role="img" aria-label="Diagrama de Ishikawa">
    <line x1="20" y1="${spineY}" x2="952" y2="${spineY}" class="spine"/><path d="M952 ${spineY - 9}l18 9l-18 9z" class="arrow"/>
    <rect x="972" y="${spineY - 56}" width="214" height="112" rx="10" class="head"/>
    ${wrapText(982, spineY - 48, 196, 98, `<small>efeito</small>${esc(efeito)}`, "effect")}${bones}</svg>`;
}

// ---------------------------------------------------------------- Evolução de um indicador pelas gerações
// pontos: [{rotulo, valor, cor, tip}] · linha tracejada = meta, faixa cinza = entre a referência do M1 e a meta.
export function evolucao(pontos, { referencia, meta, min, max }) {
  const W = 300, H = 210, L = 40, R = 14, T = 18, B = 46, pw = W - L - R, ph = H - T - B;
  const vals = pontos.map((p) => p.valor).filter((v) => v != null);
  const lo = min ?? Math.min(referencia, ...vals) - 0.04, hi = max ?? Math.min(1, Math.max(meta, ...vals) + 0.04);
  const y = (v) => T + ph * (1 - (v - lo) / (hi - lo)), x = (i) => L + (pw * (i + 0.5)) / pontos.length;
  const ticks = [lo, (lo + hi) / 2, hi].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${L - 5}" y="${y(v) + 4}" text-anchor="end">${num(v * 100)}%</text>`).join("");
  const band = `<rect x="${L}" y="${y(meta)}" width="${pw}" height="${Math.max(0, y(referencia) - y(meta))}" fill="var(--band)"/>
    <line x1="${L}" x2="${W - R}" y1="${y(meta)}" y2="${y(meta)}" stroke="var(--ink)" stroke-dasharray="6 4"/>`;
  const known = pontos.map((p, i) => [i, p]).filter(([, p]) => p.valor != null);
  const path = known.map(([i, p], j) => (j ? "L" : "M") + x(i) + " " + y(p.valor)).join("");
  const marks = pontos.map((p, i) => {
    const label = wrapText(x(i) - pw / pontos.length / 2, H - B + 6, pw / pontos.length, B - 6, esc(p.rotulo), "axis-label");
    if (p.valor == null) return label + `<text x="${x(i)}" y="${T + ph / 2}" text-anchor="middle">—</text>`;
    const above = y(p.valor) - 10 > T + 8;
    return label + `<circle cx="${x(i)}" cy="${y(p.valor)}" r="6" fill="${p.cor}" stroke="var(--surface)" stroke-width="2" data-tip="${esc(p.tip ?? p.rotulo + ": " + pct(p.valor))}"/>
      <text x="${x(i)}" y="${above ? y(p.valor) - 11 : y(p.valor) + 20}" text-anchor="middle" class="val">${num(p.valor * 100, 1)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolução do indicador; meta ${pct(meta, 0)}">${ticks}${band}<path d="${path}" fill="none" stroke="var(--axis)" stroke-width="2"/>${marks}</svg>`;
}

// ---------------------------------------------------------------- Barras horizontais simples (um valor por linha)
export function barras(linhas, { unidade = "", casas = 1 } = {}) {
  const max = Math.max(...linhas.map((l) => l.valor ?? 0), 1e-9);
  return `<div class="hbars">${linhas.map((l) => `<div class="hbar"><span class="name">${esc(l.rotulo)}</span>
      <span class="track" data-tip="${esc(l.rotulo + ": " + (l.valor == null ? "sem dado" : num(l.valor, casas) + " " + unidade))}"><i style="width:${l.valor == null ? 0 : Math.max(1.5, (l.valor / max) * 100)}%;background:${l.cor}"></i></span>
      <span class="v">${l.valor == null ? esc(l.vazio ?? "—") : num(l.valor, casas) + " " + unidade}</span></div>`).join("")}</div>`;
}

// ---------------------------------------------------------------- Séries no tempo (M2): duas linhas + cursor
// series: [{nome, cor, pontos: [[t, v|null]], tracejado?}] · devolve SVG com cursor e recorte controlados por setTempo().
export function linhas(id, series, { fim, fmt = (v) => num(v, 1), teto = null }) {
  const W = 520, H = 190, L = 50, R = 14, T = 14, B = 24, pw = W - L - R, ph = H - T - B;
  let max = teto ?? 0;
  if (teto == null) for (const s of series) for (const p of s.pontos) if (p[1] != null) max = Math.max(max, p[1]);
  max = max || 1;
  const x = (t) => L + (pw * t) / fim, y = (v) => T + ph * (1 - v / max);
  const grid = [0, 0.5, 1].map((f) => `<line x1="${L}" x2="${W - R}" y1="${y(max * f)}" y2="${y(max * f)}" stroke="var(--grid)"/><text x="${L - 6}" y="${y(max * f) + 4}" text-anchor="end">${fmt(max * f)}</text>`).join("");
  const paths = series.map((s) => {
    let d = "", on = false;
    for (const [t, v] of s.pontos) { if (v == null) { on = false; continue; } d += (on ? "L" : "M") + x(t).toFixed(1) + " " + y(v).toFixed(1); on = true; }
    return `<path d="${d}" fill="none" stroke="${s.cor}" stroke-width="2" stroke-linejoin="round" ${s.tracejado ? 'stroke-dasharray="6 4"' : ""}/>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" id="${id}" data-l="${L}" data-pw="${pw}" role="img">
    <defs><clipPath id="${id}-clip"><rect x="${L}" y="0" width="0" height="${H}"/></clipPath></defs>${grid}
    <g opacity=".22">${paths}</g><g clip-path="url(#${id}-clip)">${paths}</g>
    <line class="cursor" y1="${T}" y2="${H - B}" x1="${L}" x2="${L}" stroke="var(--ink2)" stroke-dasharray="3 3"/>
    <text x="${L}" y="${H - 6}">0 h</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${num(fim / 3600, 1)} h</text></svg>`;
}
export function setTempo(id, t, fim) {
  const svg = document.getElementById(id);
  if (!svg) return;
  const L = +svg.dataset.l, w = (+svg.dataset.pw * Math.min(t, fim)) / fim;
  svg.querySelector("clipPath rect").setAttribute("width", w);
  const c = svg.querySelector(".cursor");
  c.setAttribute("x1", L + w); c.setAttribute("x2", L + w);
}
