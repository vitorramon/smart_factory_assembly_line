// Aba 2 — Simulação (M2): a linha completa em SimPy, sem hardware. Problema (cenário Atual) e solução lado a lado.
// O servidor simula e calcula os indicadores (software/sfal/m2); aqui só se reproduz e desenha.
import { barras, linhas, radar, setTempo } from "./charts.js";
import { drawLine } from "./m2-draw.js";
import { $, esc, getJSON, hm, num, pct } from "./util.js";

const MANUAL_ORDER = ["Gravação de FW", "PCBA no chassi", "Display", "Bateria", "Alto-falante", "Microfone", "Câmera traseira", "Câmera frontal", "Botões e vibra", "Tampa traseira", "Teste funcional", "Embalagem"];
const COR = { problema: "var(--series-2)", solucao: "var(--series)" };
const CHARTS = [
  { id: "m2c-rty", key: "rty", titulo: "RTY do processo (%)", teto: 100, escala: 100, nota: "Produto dos rendimentos de primeira passagem no SPI, AOI e teste funcional ativos." },
  { id: "m2c-fpy", key: "fpy", titulo: "FPY no teste funcional (%)", teto: 100, escala: 100, nota: "Aprovadas ÷ testadas no teste funcional." },
  { id: "m2c-done", key: "done", titulo: "Produção acumulada (unidades)", casas: 0 },
  { id: "m2c-queue", key: "queue", titulo: "WIP nas filas entre estações", casas: 0, nota: "Só placas aguardando; não inclui as que estão em operação." },
  { id: "m2c-cost", key: "cost", titulo: "Custo da não qualidade estimado (R$)", casas: 0 },
];

const st = { runs: {}, scenarios: [], solution: "lean_ampliado", watch: "problema", hours: 8, now: 0, playing: false, speed: 300, built: false, visible: false, last: 0, lastPaint: 0 };
const run = (papel) => st.runs[papel];

// Estado de cada estação no instante t, a partir dos eventos (colunas t, p, s, k, r).
function snapshot(r, t, flash) {
  const ev = r.events, n = r.stations.length;
  const state = Array.from({ length: n }, () => ({ busy: null, busyCount: 0, busySince: 0, queue: 0, done: 0, busyTime: 0, reject: false, progress: 0 }));
  let lo = 0, hi = ev.t.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (ev.t[mid] <= t) lo = mid + 1; else hi = mid; }
  const latest = new Map(), entered = new Map();
  for (let i = 0; i < lo; i++) {
    const p = ev.p[i], s = ev.s[i], k = ev.k[i];
    latest.set(p, i);
    if (k === 1) entered.set(p, ev.t[i]);
    else if (k === 2) {
      state[s].done++; state[s].busyTime += ev.t[i] - (entered.get(p) ?? ev.t[i]);
      if (ev.r[i] === 2 && t - ev.t[i] < flash) state[s].reject = true;
    }
  }
  for (const i of latest.values()) {
    const a = state[ev.s[i]];
    if (ev.k[i] === 0) a.queue++;
    else if (ev.k[i] === 1) { a.busyCount++; a.busy = ev.p[i]; a.busySince = ev.t[i]; a.busyTime += t - ev.t[i]; }
  }
  state.forEach((a, i) => { if (a.busy != null) a.progress = Math.max(0, Math.min(1, (t - a.busySince) / r.durations[i])); });
  return state;
}
const sample = (r, t) => r.series[Math.max(0, Math.min(r.series.length - 1, Math.ceil((t / r.horizon) * r.series.length) - 1))];
const at = (r, t) => (t <= 0 ? { started: 0, done: 0, rejected: 0, wip: 0, queue: 0, cost: 0, fpy: null, rty: null, oee: null, copq: null, lead_time_s: null, rejects: {} } : sample(r, t));

async function load() {
  $("m2-status").textContent = "Simulando…";
  const q = (id) => getJSON(`/api/m2/run?scenario=${id}&hours=${st.hours}&seed=7`);
  try {
    [st.runs.problema, st.runs.solucao] = await Promise.all([q("atual"), q(st.solution)]);
  } catch (err) { $("m2-status").textContent = "Falha ao simular: " + err.message; return; }
  st.now = Math.min(st.now, st.hours * 3600);
  $("m2-seek").max = st.hours * 3600;
  $("m2-status").textContent = `SimPy · turno de ${num(st.hours, 1)} h · semente 7 · ${num(run("problema").events.t.length + run("solucao").events.t.length)} eventos`;
  build();
  paint(true);
}

function build() {
  const fim = st.hours * 3600;
  for (const papel of ["problema", "solucao"]) {
    const r = run(papel);
    $("m2-card-" + papel).querySelector(".desc").textContent = r.scenario.resumo;
    if (papel === "problema") $("m2-card-problema").querySelector("b").textContent = "Problema · cenário " + r.scenario.label;
  }
  $("m2-charts").innerHTML = CHARTS.map((c) => {
    const serie = (papel) => ({ nome: papel, cor: COR[papel], pontos: [[0, c.key === "done" || c.key === "queue" || c.key === "cost" ? 0 : null], ...run(papel).series.map((p) => [p.t, p[c.key] == null ? null : p[c.key] * (c.escala ?? 1)])] });
    return `<div class="chart"><div class="title"><b>${c.titulo}</b></div>${linhas(c.id, [serie("problema"), serie("solucao")], { fim, teto: c.teto ?? null, fmt: (v) => num(v, c.casas ?? 0) })}
      <div class="legend"><span class="ln" style="--c:${COR.problema}">problema <b id="${c.id}-p"></b></span><span class="ln" style="--c:${COR.solucao}">solução <b id="${c.id}-s"></b></span></div>${c.nota ? `<p class="hint">${c.nota}</p>` : ""}</div>`;
  }).join("");
  st.built = true;
}

function paint(force = false) {
  if (!st.built || (!st.visible && !force)) return;
  const t = st.now, P = run("problema"), S = run("solucao"), mp = at(P, t), ms = at(S, t);
  $("m2-seek").value = t;
  $("m2-clock").textContent = hm(t);
  $("m2-play").textContent = st.playing ? "Pausar" : t >= st.hours * 3600 ? "Reproduzir de novo" : "Reproduzir";

  const two = (a, b) => `<div class="pair"><span><i style="background:${COR.problema}"></i>problema <b>${a}</b></span><span><i style="background:${COR.solucao}"></i>solução <b>${b}</b></span></div>`;
  $("m2-kpis").innerHTML = [["Peças iniciadas", "started"], ["Concluídas", "done"], ["Retidas / reprovadas", "rejected"], ["Em processo (WIP)", "wip"]]
    .map(([nome, k]) => `<div class="tile"><div class="name">${nome}</div>${two(num(mp[k]), num(ms[k]))}</div>`).join("");

  // linha desenhada do cenário escolhido
  const r = run(st.watch);
  drawLine($("m2-line"), r, snapshot(r, t, Math.max(8, st.speed * 0.6)), MANUAL_ORDER);
  $("m2-line-title").textContent = `${st.watch === "problema" ? "Problema" : "Solução"} · ${r.scenario.label}`;

  for (const c of CHARTS) {
    setTempo(c.id, t, st.hours * 3600);
    const f = (v) => (v == null ? "—" : num(v * (c.escala ?? 1), c.escala ? 1 : c.casas ?? 0));
    $(c.id + "-p").textContent = f(mp[c.key]); $(c.id + "-s").textContent = f(ms[c.key]);
  }

  const posts = ["SPI", "AOI", "Teste funcional"];
  $("m2-failures").innerHTML = barras(posts.flatMap((n) => [["problema", P, mp], ["solucao", S, ms]].map(([papel, rr, m]) => ({
    rotulo: `${n} · ${papel === "problema" ? "problema" : "solução"}`, valor: rr.stations.includes(n) ? m.rejects[n] ?? 0 : null, vazio: "desativado", cor: COR[papel] }))), { unidade: "", casas: 0 });

  const eixo = (m) => [m.fpy, m.rty, m.oee == null ? null : Math.min(1, m.oee), m.copq];
  $("m2-radar").innerHTML = radar(["FPY", "RTY", "OEE da linha", "1 − COPQ"], [
    { nome: "problema", valores: eixo(mp), cor: COR.problema }, { nome: "solução", valores: eixo(ms), cor: COR.solucao, preenchido: true }], { min: 0.5 });

  const linha = (nome, f) => `<tr><td>${nome}</td><td class="num">${f(mp)}</td><td class="num">${f(ms)}</td></tr>`;
  $("m2-table").innerHTML = `<thead><tr><th>Indicador</th><th class="num">Problema</th><th class="num">Solução</th></tr></thead><tbody>` +
    linha("Vazão de concluídas", (m) => (t ? num((m.done * 3600) / t, 1) + " un/h" : "—")) +
    linha("Lead time médio das concluídas", (m) => (m.lead_time_s ? num(m.lead_time_s / 60, 2) + " min" : "—")) +
    linha("FPY no teste funcional", (m) => pct(m.fpy, 2)) + linha("RTY estimado", (m) => pct(m.rty, 2)) +
    linha("OEE da linha (ciclo ideal de 20 s)", (m) => pct(m.oee, 2)) + linha("1 − COPQ", (m) => pct(m.copq, 2)) +
    linha("Custo da não qualidade estimado", (m) => "R$ " + num(m.cost, 2)) + linha("WIP nas filas", (m) => num(m.queue)) + `</tbody>`;

  const state = snapshot(r, t, 0);
  $("m2-stations").innerHTML = r.stations.map((n, i) => {
    const a = state[i];
    return `<tr><td>${String(i + 1).padStart(2, "0")} · ${esc(n)}</td><td>${a.busy != null ? "Em operação" : "Livre"}</td><td class="num">${a.queue}</td><td class="num">${a.done}</td><td class="num">${t ? num((100 * a.busyTime) / (t * r.capacities[i]), 1) + " %" : "—"}</td></tr>`;
  }).join("");
}

function tick(ts) {
  if (st.playing && st.visible) {
    st.now = Math.min(st.hours * 3600, st.now + ((ts - st.last) / 1000) * st.speed);
    if (st.now >= st.hours * 3600) st.playing = false;
    if (ts - st.lastPaint > 90 || !st.playing) { paint(); st.lastPaint = ts; }
  }
  st.last = ts;
  requestAnimationFrame(tick);
}

export async function init() {
  st.scenarios = await getJSON("/api/m2/scenarios");
  $("m2-solution").innerHTML = st.scenarios.filter((s) => s.papel === "solucao").map((s) => `<option value="${s.id}" ${s.id === st.solution ? "selected" : ""}>${esc(s.label)}</option>`).join("");
  $("m2-solution").addEventListener("change", (e) => { st.solution = e.target.value; load(); });
  $("m2-hours").addEventListener("change", (e) => { st.hours = +e.target.value; st.now = 0; st.playing = false; load(); });
  $("m2-speed").addEventListener("change", (e) => (st.speed = +e.target.value));
  $("m2-play").addEventListener("click", () => { if (st.now >= st.hours * 3600) st.now = 0; st.playing = !st.playing; paint(); });
  $("m2-reset").addEventListener("click", () => { st.now = 0; st.playing = false; paint(); });
  $("m2-end").addEventListener("click", () => { st.now = st.hours * 3600; st.playing = false; paint(); });
  $("m2-seek").addEventListener("input", (e) => { st.now = +e.target.value; st.playing = false; paint(); });
  for (const papel of ["problema", "solucao"]) {
    $("m2-card-" + papel).addEventListener("click", (e) => {
      if (e.target.closest("select")) return;
      st.watch = papel;
      document.querySelectorAll("#view-m2 .scenario").forEach((c) => c.classList.toggle("sel", c.id === "m2-card-" + papel));
      paint();
    });
  }
  new ResizeObserver(() => paint()).observe($("m2-line"));
  await load();
  st.now = st.hours * 3600;   // abre no fim do turno: o resultado aparece de imediato; "Reproduzir" mostra o filme
  paint(true);
  requestAnimationFrame(tick);
}
export function show(visible) { st.visible = visible; if (visible) paint(); else st.playing = false; }
