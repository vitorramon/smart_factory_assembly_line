// Aba 4 — Síntese: do problema (M1) à simulação (M2) e à linha conectada (M3), indicador por indicador.
import { barras, evolucao, ishikawa, pareto, radar } from "./charts.js";
import { $, clock, esc, getJSON, level, num, pct, pp, STATUS } from "./util.js";

const COR = { m1: "var(--muted)", problema: "var(--series-2)", solucao: "var(--series)", m3: "var(--series-3)" };
const ICON = { feito: "✔", parcial: "▲", pendente: "✕" };
const ROTULO = { feito: "tratada", parcial: "tratada em parte", pendente: "não tratada" };
let data = null, causa = 0, visible = false, timer = null;
const shown = { m1: true, meta: true, problema: false, solucao: true, m3: true };

function scorecard() {
  const cell = (v, base, goal) => `<td class="num"><span class="status ${level(v, base, goal)}">${pct(v)}</span></td>`;
  $("s-score").innerHTML = `<thead><tr><th>Indicador</th><th class="num">M1 · situação atual</th><th class="num">M2 · problema simulado</th><th class="num">M2 · solução simulada</th><th class="num">M3 · agora</th><th class="num">Meta (M1)</th><th>M3 contra a meta</th></tr></thead><tbody>` +
    data.geracoes.map((g) => `<tr><td><b>${esc(g.nome)}</b><div class="hint">${esc(g.descricao)}</div></td><td class="num">${pct(g.m1_atual, 0)}</td>${cell(g.m2_atual, g.m1_atual, g.meta)}${cell(g.m2_solucao, g.m1_atual, g.meta)}${cell(g.m3, g.m1_atual, g.meta)}<td class="num">${pct(g.meta, 0)}</td>
      <td>${g.m3 == null ? "sem dado" : `${pp(g.m3 - g.meta)} · ${STATUS[g.nivel]}`}</td></tr>`).join("") + `</tbody>`;
  $("s-origin").innerHTML = `<b>M3 · agora:</b> ${esc(data.m3.origem)} · turno desde ${clock(data.m3.window_start)} · ${num(data.m3.line.done)} unidades prontas.`;
}

function evolution() {
  $("s-evo").innerHTML = data.geracoes.map((g) => `<div class="chart"><div class="title"><b>${esc(g.nome)} <span class="hint">meta ${pct(g.meta, 0)}</span></b><span class="status ${g.nivel}">${STATUS[g.nivel]}</span></div>
    ${evolucao([
      { rotulo: "M1 atual", valor: g.m1_atual, cor: COR.m1 }, { rotulo: "M2 problema", valor: g.m2_atual, cor: COR.problema },
      { rotulo: "M2 solução", valor: g.m2_solucao, cor: COR.solucao }, { rotulo: "M3 agora", valor: g.m3, cor: COR.m3 }], { referencia: g.m1_atual, meta: g.meta })}</div>`).join("");
}

function web() {
  const g = data.geracoes, col = (k) => g.map((x) => (x[k] == null ? null : Math.min(1, x[k])));
  const all = [
    ["m1", { nome: "M1 · situação atual", valores: col("m1_atual"), cor: COR.m1, tracejado: true }],
    ["meta", { nome: "Meta (M1)", valores: col("meta"), cor: "var(--ink)", tracejado: true }],
    ["problema", { nome: "M2 · problema simulado", valores: col("m2_atual"), cor: COR.problema }],
    ["solucao", { nome: "M2 · solução simulada", valores: col("m2_solucao"), cor: COR.solucao }],
    ["m3", { nome: "M3 · agora", valores: col("m3"), cor: COR.m3, preenchido: true }],
  ];
  $("s-radar").innerHTML = radar(g.map((x) => x.nome), all.filter(([k]) => shown[k]).map(([, s]) => s), { min: 0.6 });
  $("s-radar-toggle").innerHTML = all.map(([k, s]) => `<label><input type="checkbox" data-serie="${k}" ${shown[k] ? "checked" : ""}> ${esc(s.nome)}</label>`).join("");
}

function paretos() {
  $("s-pareto").innerHTML = ["m1", "m2_atual", "m2_solucao", "m3"].map((k) => {
    const p = data.pareto[k];
    return `<div class="chart"><div class="title"><b>${esc(p.titulo)}</b></div>${pareto(p.itens)}<p class="hint">${esc(p.nota)}</p></div>`;
  }).join("");
}

function fish() {
  const causas = data.ishikawa.causas, c = causas[causa];
  $("s-fish").innerHTML = ishikawa(data.ishikawa.efeito, causas, { selecionada: causa, comStatus: true });
  $("s-cause").innerHTML = `<h3>${esc(c.m)} <span class="st ${c.m3.status}">${ICON[c.m3.status]} ${ROTULO[c.m3.status]}</span></h3>
    <ol class="trail">
      <li><span>M1 · causa-raiz</span>${esc(c.causa_raiz)}</li>
      <li><span>M1 · contramedida planejada</span>${esc(c.contramedida)} <em>(${esc(c.ferramenta)})</em></li>
      <li><span>M2 · na simulação</span>${esc(c.m2)}</li>
      <li><span>M3 · na linha conectada</span>${esc(c.m3.texto)}</li>
    </ol>`;
  const n = (s) => causas.filter((x) => x.m3.status === s).length;
  $("s-fish-sum").textContent = `Das 6 causas-raiz do M1: ${n("feito")} tratada(s), ${n("parcial")} tratada(s) em parte, ${n("pendente")} não tratada(s).`;
  $("s-cause-table").innerHTML = `<thead><tr><th>6M</th><th>Causa-raiz (M1)</th><th>Situação no M3</th></tr></thead><tbody>` +
    causas.map((x) => `<tr><td><b>${esc(x.m)}</b></td><td>${esc(x.causa_raiz)}</td><td><span class="st ${x.m3.status}">${ICON[x.m3.status]} ${ROTULO[x.m3.status]}</span></td></tr>`).join("") + `</tbody>`;
}

function flow() {
  $("s-flow").innerHTML = data.fluxo.map((f) => `<div class="chart"><div class="title"><b>${esc(f.nome)}</b><span class="hint">sem referência no M1</span></div>
    ${barras([{ rotulo: "M2 · problema", valor: f.m2_atual, cor: COR.problema }, { rotulo: "M2 · solução", valor: f.m2_solucao, cor: COR.solucao }, { rotulo: "M3 · agora", valor: f.m3, cor: COR.m3 }], { unidade: f.unidade, casas: f.id === "wip" ? 0 : 1 })}</div>`).join("");
}

function reading() {
  const g = data.geracoes, ok = g.filter((x) => x.nivel === "green").map((x) => x.nome), mid = g.filter((x) => x.nivel === "yellow").map((x) => x.nome), bad = g.filter((x) => x.nivel === "red").map((x) => x.nome);
  const list = (a) => a.join(", ");
  const items = [];
  if (!data.m3.line.done) items.push("A linha conectada ainda não tem unidades prontas neste turno; a comparação do M3 aparece quando houver produção.");
  else {
    if (ok.length) items.push(`<b>Na meta agora:</b> ${list(ok)}.`);
    if (mid.length) items.push(`<b>Acima da situação de partida, abaixo da meta:</b> ${list(mid)}.`);
    if (bad.length) items.push(`<b>Abaixo da situação de partida:</b> ${list(bad)}.`);
  }
  const sim = data.geracoes.find((x) => x.id === "rty");
  items.push(`<b>O que a simulação do M2 antecipou:</b> a inspeção na fonte leva o FPY do teste final de ${pct(data.m2.problema.fpy)} para ${pct(data.m2.solucao.fpy)}, mas o RTY quase não muda (${pct(sim.m2_atual)} → ${pct(sim.m2_solucao)}): o defeito continua nascendo, só passa a ser retido antes. Atingir a meta de RTY exige reduzir o defeito na origem, não só detectá-lo.`);
  items.push(`<b>Cuidado ao comparar:</b> o M1 fala da linha inteira com 12 operadoras, o M2 simula 22 estações e o M3 é um recorte de 5 estações. ${data.m3.medido ? "" : "Hoje o M3 também é simulação (o firmware é o real; o mundo em volta, não): "}as colunas mostram tendência, não a mesma medição repetida.`);
  items.push(`<b>Meta SMART do M1:</b> “${esc(data.smart)}” No M3, ${num(data.m3.evidence.blocked_route)} tentativa(s) de avanço de unidade reprovada foram barradas pelo intertravamento neste turno; a padronização das 12 estações manuais não é verificável num recorte com um posto de montagem.`);
  $("s-reading").innerHTML = items.map((i) => `<li>${i}</li>`).join("");
  $("s-scope").innerHTML = `<thead><tr><th>Módulo</th><th>O que é</th><th>Linha representada</th><th>De onde vêm os números</th></tr></thead><tbody>` +
    data.escopo.map((e) => `<tr><td><b>${esc(e.modulo)}</b></td><td>${esc(e.o_que)}</td><td>${esc(e.linha)}</td><td>${esc(e.origem)}</td></tr>`).join("") + `</tbody>`;
}

async function refresh() {
  try { data = await getJSON("/api/sintese"); } catch (err) { $("s-origin").textContent = "Não foi possível carregar a síntese: " + err.message; return; }
  scorecard(); evolution(); web(); paretos(); fish(); flow(); reading();
}

export async function init() {
  const pick = (e) => { const g = e.target.closest("[data-cause]"); if (g && (e.type === "click" || e.key === "Enter")) { causa = +g.dataset.cause; fish(); } };
  $("s-fish").addEventListener("click", pick);
  $("s-fish").addEventListener("keydown", pick);
  $("s-radar-toggle").addEventListener("change", (e) => { shown[e.target.dataset.serie] = e.target.checked; web(); });
  await refresh();
}
export function show(v) {
  visible = v;
  clearInterval(timer);
  if (v) { refresh(); timer = setInterval(() => { if (visible && !document.querySelector("#view-sintese svg:hover")) refresh(); }, 8000); }
}
