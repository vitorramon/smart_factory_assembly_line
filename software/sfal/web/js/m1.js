// Aba 1 — Problema e metas (M1): o diagnóstico Lean que deu origem a tudo. Conteúdo em config/m1.yaml.
import { ishikawa, pareto, radar } from "./charts.js";
import { $, esc, getJSON, pct, pp } from "./util.js";

let m1 = null, causa = 0;

function renderCausa() {
  const c = m1.ishikawa.causas[causa];
  $("m1-fish").innerHTML = ishikawa(m1.ishikawa.efeito, m1.ishikawa.causas, { selecionada: causa });
  $("m1-why").innerHTML = `<h3>${esc(c.m)} · 5 Porquês</h3><p class="lead"><b>Efeito:</b> ${esc(c.efeito_local)}</p>
    <ol class="whys">${c.porques.map((p) => `<li><span>Por quê?</span> ${esc(p)}</li>`).join("")}</ol>
    <p class="root"><b>Causa-raiz:</b> ${esc(c.causa_raiz)}</p>`;
}

export async function init() {
  m1 = await getJSON("/api/m1");
  $("m1-hero").innerHTML = `<div class="panel"><h2>O cenário</h2><p class="lead">${esc(m1.cenario)}</p><ul class="plain">${m1.contexto.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>
    <div class="panel callout bad"><h2>Problema central</h2><p class="lead">${esc(m1.problema_central)}</p></div>
    <div class="panel callout goal"><h2>Meta SMART</h2><p class="lead">${esc(m1.smart)}</p></div>`;

  $("m1-kpis").innerHTML = m1.indicadores.map((i) => `<div class="tile"><div class="name">${esc(i.nome)} · ${esc(i.descricao)}</div>
      <div class="value">${pct(i.atual, 0)} <small>→ ${pct(i.meta, 0)}</small></div>
      <div class="meter"><i class="red" style="width:${i.atual * 100}%"></i><b style="left:${i.atual * 100}%" title="situação atual"></b><b class="goal" style="left:${i.meta * 100}%" title="meta"></b></div>
      <div class="foot">situação atual → meta em 90 dias · ${pp(i.meta - i.atual, 0)}</div></div>`).join("");
  $("m1-radar").innerHTML = radar(m1.indicadores.map((i) => i.nome), [
    { nome: "situação atual", valores: m1.indicadores.map((i) => i.atual), cor: "var(--series-2)" },
    { nome: "meta em 90 dias", valores: m1.indicadores.map((i) => i.meta), cor: "var(--series)", preenchido: true }], { min: 0.6 });

  $("m1-pilares").innerHTML = m1.pilares.map((p) => `<div class="panel"><h3>${esc(p.titulo)}</h3><p class="hint">${esc(p.autor)}</p><p>${esc(p.texto)}</p></div>`).join("");
  $("m1-pontos").innerHTML = m1.pontos_problema.map((p) => `<li><b>${esc(p.id)}</b> ${esc(p.texto)}</li>`).join("");
  $("m1-waste").innerHTML = m1.desperdicios.map((d) => `<div class="waste ${d.prioritario ? "prio" : ""}"><span class="letter">${esc(d.letra)}</span><div><b>${esc(d.nome)}</b>${d.prioritario ? ' <span class="tag">priorizado</span>' : ""}<p>${esc(d.texto)}</p></div></div>`).join("");

  renderCausa();
  const pick = (e) => { const g = e.target.closest("[data-cause]"); if (g && (e.type === "click" || e.key === "Enter")) { causa = +g.dataset.cause; renderCausa(); } };
  $("m1-fish").addEventListener("click", pick);
  $("m1-fish").addEventListener("keydown", pick);

  $("m1-pareto").innerHTML = pareto(m1.pareto.itens.map((i) => ({ nome: i.categoria, qtd: i.qtd })));
  $("m1-pareto-note").textContent = `Lote de ${m1.pareto.lote.toLocaleString("pt-BR")} unidades. ${m1.pareto.leitura}`;

  $("m1-plano").innerHTML = `<thead><tr><th>Categoria</th><th>Causa-raiz</th><th>Contramedida</th><th>Ferramenta</th></tr></thead><tbody>` +
    m1.ishikawa.causas.map((c) => `<tr><td><b>${esc(c.m)}</b></td><td>${esc(c.causa_raiz)}</td><td>${esc(c.contramedida)}</td><td>${esc(c.ferramenta)}</td></tr>`).join("") + `</tbody>`;
  $("m1-lean").innerHTML = `<thead><tr><th>Ferramenta Lean</th><th>Problema atacado</th><th>Aplicação</th></tr></thead><tbody>` +
    m1.ferramentas_lean.map((f) => `<tr><td><b>${esc(f.ferramenta)}</b></td><td>${esc(f.problema)}</td><td>${esc(f.aplicacao)}</td></tr>`).join("") + `</tbody>`;
  $("m1-futuro").innerHTML = `<p><b>Tecnologia 4.0 prevista:</b></p><ul class="plain">${m1.tecnologia_40.map((t) => `<li>${esc(t)}</li>`).join("")}</ul><p>${esc(m1.digital_twin)}</p>`;
  $("m1-refs").innerHTML = `<p class="hint">Fonte: ${esc(m1.fonte)}.</p><ul class="plain hint">${m1.referencias.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`;
}
