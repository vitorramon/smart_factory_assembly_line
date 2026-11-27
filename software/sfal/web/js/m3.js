// Aba 3 — Linha conectada (M3): o estado ao vivo que as estações informam.
import { onSnapshot } from "./live.js";
import { $, clock, dur, esc, hideTip, num, pct, showTip, STATUS } from "./util.js";

const STATE = { IDLE: "Aguardando", WAIT: "Pedindo liberação", RUNNING: "Em ciclo", BLOCKED: "Bloqueada", OFFLINE: "Offline", "?": "—" };
const REASON = {
  upstream_fail: "reprovada antes", skipped_step: "pulou estação", already_done: "já processada", unknown_unit: "desconhecida",
  scrapped: "refugada", in_process: "em outra estação", no_unit: "sem unidade na fila", hold: "retida (jidoka)",
  no_server: "servidor mudo", no_link: "sem rede",
};
let snap = null;

// ---------------------------------------------------------------- desenho
function render() {
  const { line } = snap, k = line.kpi;
  $("line-sub").textContent = `takt ${num(line.takt_s)} s · turno desde ${clock(k.window_start)} · intertravamento ${line.interlock ? "ligado" : "desligado"} · atualizado ${clock(snap.ts)}`;
  renderTiles(line, k);
  renderFloor();
  renderFlow();
  renderVision();
  renderAas();
  renderCharts();
  $("insights").innerHTML = snap.insights.map((i) => `<li class="${i.level}">${esc(i.text)}</li>`).join("");
  $("log").innerHTML = snap.log.map((e) => `<li><time>${clock(e.ts)}</time><span class="${e.level}"></span><span>${linkUnits(esc(e.message))}</span></li>`).join("");
  renderSim();
  renderScenarios();
}
const linkUnits = (html) => html.replace(/U-\d{6}/g, (u) => `<a href="#" data-unit="${u}">${u}</a>`);

function goalTile(name, key, line) {
  const v = line.kpi[key], t = line.targets[key], lvl = line.levels[key];
  const meter = t ? `<div class="meter"><i class="${lvl}" style="width:${Math.max(0, Math.min(100, (v ?? 0) * 100))}%"></i><b style="left:${t.baseline * 100}%" title="referência"></b><b class="goal" style="left:${t.goal * 100}%" title="meta"></b></div>` : "";
  return `<div class="tile"><div class="name">${name}</div><div class="value">${pct(v)}</div>${meter}
    <div class="status ${lvl}">${STATUS[lvl]}</div><div class="foot">${t ? `referência ${pct(t.baseline, 0)} · meta ${pct(t.goal, 0)}` : ""}</div></div>`;
}
function renderTiles(line, k) {
  $("tiles").innerHTML =
    goalTile("FPY · certo na primeira vez", "fpy", line) + goalTile("RTY · rendimento acumulado", "rty", line) + goalTile("OEE · contra o takt", "oee", line) + goalTile("1 − COPQ · custo da não qualidade", "copq", line) +
    `<div class="tile"><div class="name">Produção</div><div class="value">${k.done} <small>prontas</small></div><div class="foot">${num(k.throughput_h, 0)} por hora · ritmo ${k.pace_s == null ? "—" : num(k.pace_s, 1) + " s"}</div><div class="foot">${k.scrap} refugo · ${k.failed_units} com reprovação</div></div>` +
    `<div class="tile"><div class="name">Lead time</div><div class="value">${dur(k.lead_time_avg_s)}</div><div class="foot">95 % das unidades em até ${dur(k.lead_time_p95_s)}</div><div class="foot">${k.wip} em processo · ${k.in_rework} em retrabalho</div></div>`;
}

function stationLevel(s) {
  if (!s.online) return s.seen ? "red" : "gray";
  if (s.call || s.hold || s.state === "BLOCKED") return "red";
  if (s.light === "yellow" || (s.state === "RUNNING" && s.cycle_ms > snap.line.takt_s * 1000) || s.queued > 0) return "yellow";
  return "green";
}
function lamp(s) {
  // Espelho aproximado da torre luminosa da estação.
  let g = false, y = false, r = false;
  if (s.online) {
    if (s.call || s.state === "BLOCKED" || s.light === "red") r = true;
    else if (s.light === "yellow") y = true;
    else if (s.state === "RUNNING") { if (s.cycle_ms > snap.line.takt_s * 1000) y = true; else g = true; }
    else if (s.state === "WAIT") g = true;
  }
  return `<span class="lamp" title="torre luminosa"><i class="r ${r ? "on" : ""}"></i><i class="y ${y ? "on" : ""}"></i><i class="g ${g ? "on" : ""}"></i></span>`;
}
// ---------------------------------------------------------------- chão de fábrica
const FW = 1200, FH = 350, BELT = 203, unitEls = new Map();
let floorKey = "";
function towerState(s) {
  if (!s.online) return { blink: false };
  if (s.call) return { r: true, blink: true };
  if (s.state === "BLOCKED" || s.light === "red") return { r: true };
  if (s.light === "yellow") return { y: true };
  if (s.state === "RUNNING") return s.cycle_ms > snap.line.takt_s * 1000 ? { y: true } : { g: true };
  if (s.state === "WAIT") return { g: true, blink: true };
  return {};
}
function fitFloor() {
  const k = $("floor").clientWidth / FW;
  $("stage").style.transform = `scale(${k})`;
  $("floor").style.height = FH * k + "px";
}
new ResizeObserver(fitFloor).observe($("floor"));
function renderFloor() {
  const st = snap.stations, n = st.length;
  const xs = st.map((_, i) => (n === 1 ? FW / 2 : 200 + (i * (FW - 330)) / (n - 1)));
  const idx = Object.fromEntries(st.map((s, i) => [s.id, i]));
  const at = (x, y, w = 0) => `style="left:${x - w / 2}px;top:${y}px"`;
  const key = st.map((s) => s.id + s.kind + s.name).join("|");
  if (key !== floorKey) {
    floorKey = key;
    $("floor-static").innerHTML = st.map((s, i) =>
      `<div class="fl fname" ${at(xs[i], 40, 180)}>${esc(s.name)}</div>` + (s.kind === "manual" ? `<div class="fl operator" ${at(xs[i] + 82, 122)} title="posto com operador"></div>` : "")).join("") +
      `<div class="fl bin-label" style="left:14px;top:${BELT + 22}px">entrada →</div>`;
    fitFloor();
  }
  const k = snap.line.kpi;
  // estado de cada estação
  $("floor-live").innerHTML = st.map((s, i) => {
    const x = xs[i], t = towerState(s);
    const cls = !s.online ? "offline" : s.call || s.hold || s.state === "BLOCKED" ? "stopped" : s.state === "RUNNING" ? "running" : "";
    let state = STATE[s.state] ?? s.state;
    const ia = s.id === snap.vision?.station && snap.vision.enabled;     // estação com inspeção por IA
    if (s.call) state = "Chamado aberto"; else if (s.hold) state = "Retida (jidoka)"; else if (s.state === "BLOCKED") state = "Bloqueada: " + (REASON[s.reason] ?? s.reason);
    else if (ia && s.state === "RUNNING") state = "Inspecionando por IA";
    const prog = s.state === "RUNNING" ? Math.min(100, (s.cycle_ms / 1000 / s.ideal_cycle_s) * 100) : 0;
    const lamp = (c) => `<i class="${c} ${t[c] ? "on" : ""} ${t[c] && t.blink ? "blink" : ""}"></i>`;
    const more = s.kpi.waiting > 6 ? `<div class="fl more" ${at(xs[i] - 78 - 6 * 21, BELT - 8, 30)}>+${s.kpi.waiting - 6}</div>` : "";
    return `<div class="fl tower" ${at(x - 76, 100)} title="torre luminosa">${lamp("r")}${lamp("y")}${lamp("g")}</div>
      <div class="fl machine ${cls}" ${at(x, 96, 116)}>${s.temp != null ? num(s.temp, 1) + " °C" : ia ? "câmera + IA" : s.hw === "esp32" ? "placa ESP32" : s.hw === "sim" ? "simulada" : "sem placa"}<div class="bar"><i class="${s.cycle_ms / 1000 > s.ideal_cycle_s * 1.25 ? "late" : ""}" style="width:${prog}%"></i></div></div>
      <div class="fl fstate" ${at(x, 60, 180)}>${esc(state)}</div>${more}`;
  }).join("") + `<div class="fl bin-label" style="right:14px;top:${BELT + 22}px">→ expedição <b>${k.done}</b></div><div class="fl bin-label" style="right:14px;top:${FH - 28}px">refugo <b>${k.scrap}</b></div>`;

  // onde está cada unidade
  const pos = new Map(), q = {}, rw = {};
  for (const u of snap.floor.units) {
    const i = idx[u.next_station];
    if (i == null) continue;
    if (u.busy) pos.set(u.id, [xs[i], 122, ""]);
    else if (u.status === "rework") { const j = (rw[i] = (rw[i] ?? 0) + 1) - 1; if (j < 4) pos.set(u.id, [xs[i] - 33 + j * 22, 262, "rework"]); }
    else { const j = (q[i] = (q[i] ?? 0) + 1) - 1; if (j < 6) pos.set(u.id, [xs[i] - 78 - j * 21, BELT, ""]); }
  }
  const shelves = Object.keys(rw).map((i) => `<div class="fl shelf" ${at(xs[i], 278, 96)}></div><div class="fl shelf-label" ${at(xs[i], 282, 96)}>retrabalho</div>`).join("");
  $("floor-live").insertAdjacentHTML("beforeend", shelves);
  const layer = $("floor-units"), move = (el, x, y) => (el.style.transform = `translate(${x}px,${y}px)`);
  for (const [id, [x, y, cls]] of pos) {
    let el = unitEls.get(id);
    if (!el) {
      el = document.createElement("div");
      el.dataset.unit = id; el.title = id; el.textContent = id.slice(-3);
      el.className = "piece";
      move(el, x < xs[0] ? -20 : x, y);          // unidade nova entra pela esquerda
      layer.appendChild(el); unitEls.set(id, el);
      el.getBoundingClientRect();                 // fixa a posição inicial antes de animar
    }
    el.className = "piece " + cls; el._x = x;
    move(el, x, y);
  }
  for (const [id, el] of unitEls) {
    if (pos.has(id)) continue;
    unitEls.delete(id);
    const exit = snap.floor.exits[id];
    if (exit === "done") move(el, FW + 30, BELT);
    else if (exit === "scrap") { el.className = "piece out"; move(el, el._x ?? 0, FH - 20); }
    el.classList.add("gone");
    setTimeout(() => el.remove(), 1100);
  }
}

function renderFlow() {
  $("flow").innerHTML = snap.stations.map((s, i) => {
    const k = s.kpi, lvl = stationLevel(s);
    let state = STATE[s.state] ?? s.state;
    if (s.call) state = "Chamado aberto";
    else if (s.hold) state = "Retida (jidoka)";
    else if (s.state === "BLOCKED") state = "Bloqueada: " + (REASON[s.reason] ?? s.reason);
    const prog = s.state === "RUNNING" ? Math.min(100, (s.cycle_ms / 1000 / s.ideal_cycle_s) * 100) : 0;
    const late = s.cycle_ms / 1000 > s.ideal_cycle_s * 1.25;
    const extra = [s.temp != null ? num(s.temp, 1) + " °C" : "", s.queued ? `${s.queued} evento(s) na fila da placa` : "", s.gaps ? `${s.gaps} perdido(s)` : ""].filter(Boolean).join(" · ");
    return `<div class="buffer ${k.waiting >= 4 ? "high" : ""}" title="unidades esperando por ${esc(s.name)}"><span class="n">${k.waiting}</span><span>${i ? "→" : "entrada"}</span></div>
      <div class="station ${lvl}">
        <div class="head"><b title="${esc(s.name)}">${esc(s.name)}</b><span class="hw" title="origem dos dados desta estação">${s.hw === "esp32" ? "ESP32" : s.hw === "sim" ? "simulada" : "sem placa"}</span></div>
        <div class="state">${lamp(s)}${esc(state)}</div>
        <div class="unit">${s.unit ? `<a href="#" data-unit="${esc(s.unit)}">${esc(s.unit)}</a>` : "&nbsp;"}${s.state === "RUNNING" ? ` · ${num(s.cycle_ms / 1000, 0)} s` : ""}</div>
        <div class="progress" title="ciclo atual contra o ciclo ideal de ${num(s.ideal_cycle_s)} s"><i class="${late ? "late" : ""}" style="width:${prog}%"></i></div>
        <dl><div><dt>OEE</dt><dd>${pct(k.oee, 0)}</dd></div><div><dt>FPY</dt><dd>${pct(k.fpy, 0)}</dd></div><div><dt>ciclo médio</dt><dd>${k.avg_cycle_s == null ? "—" : num(k.avg_cycle_s, 1) + " s"}</dd></div>
        <div><dt>ciclos</dt><dd>${k.cycles}</dd></div><div><dt>reprov.</dt><dd>${k.nok}</dd></div><div><dt>parada</dt><dd>${dur(k.down_s)}</dd></div></dl>
        <div class="hint">${esc(extra) || "&nbsp;"}</div>
      </div>`;
  }).join("");
}

// ---------------------------------------------------------------- inspeção óptica por IA
const DEFECT = { ponte: "ponte de solda", ausente: "solda ausente", excesso: "excesso de solda" };
let visionPick = null, visionShown = null;
function verdictText(i) {
  if (i.ok == null) return "sem veredito" + (i.error ? ": " + i.error : "");
  return i.ok ? "✔ aprovada" : "✕ reprovada: " + (DEFECT[i.defect] ?? i.defect ?? "defeito");
}
function truthText(i) {
  if (i.truth == null) return "";
  const real = i.truth ? "tinha " + (DEFECT[i.truth_kind] ?? "defeito") : "estava boa";
  const right = i.ok == null ? "" : (i.ok === 0) === (i.truth === 1) ? " · o modelo acertou" : i.truth ? " · o modelo deixou passar" : " · reprovação indevida";
  return `gabarito do simulador: ${real}${right}`;
}
function renderVision() {
  const v = snap.vision;
  $("vision-panel").hidden = !v?.station;
  if (!v?.station) return;
  const station = snap.stations.find((s) => s.id === v.station);
  $("vision-sub").textContent = v.enabled ? `estação ${station?.name ?? v.station} · modelo ${v.model}` : `desligada: ${v.error || "sem modelo"}`;
  const t = (name, value, foot = "") => `<div class="tile"><div class="name">${name}</div><div class="value">${value}</div><div class="foot">${foot}</div></div>`;
  $("vision-stats").innerHTML =
    t("Inspecionadas", num(v.inspected), `${num(v.rejected)} reprovadas`) +
    t("Detecção", pct(v.detection, 0), "defeituosas que o modelo reprovou") +
    t("Falsa reprovação", pct(v.false_fail, 0), `${num(v.good_rejected)} boa(s) reprovada(s)`) +
    t("Escaparam", num(v.escaped), "defeituosas aprovadas") +
    t("Tempo do modelo", v.latency_ms_median == null ? "—" : num(v.latency_ms_median) + " ms", "mediana por foto");
  const c = v.card ?? {};
  $("vision-note").textContent = (v.with_truth ? `Detecção e falsa reprovação medidas em ${num(v.with_truth)} foto(s) deste turno com gabarito, que só existe porque a foto é gerada pelo simulador. ` : "") +
    (c.teste ? `No treino (${c.treinado_em}), em ${num(c.teste)} fotos sintéticas de teste: detecção ${pct(c.deteccao)}, falsa reprovação ${pct(c.falsa_reprovacao)}.` : "") +
    (v.no_verdict ? ` ${num(v.no_verdict)} foto(s) sem veredito.` : "");
  if (!v.last.length) { $("vision-shot").innerHTML = `<p class="hint empty">Nenhuma placa inspecionada ainda.</p>`; $("vision-thumbs").innerHTML = ""; return; }
  const pick = v.last.find((i) => i.id === visionPick) ?? v.last[0];
  $("vision-thumbs").innerHTML = v.last.map((i) => `<button class="thumb ${i.id === pick.id ? "sel" : ""} ${i.ok === 0 ? "nok" : ""}" data-insp="${i.id}" title="${esc(i.unit)} · ${esc(verdictText(i))}">
      <img src="/api/vision/photo/${encodeURIComponent(i.image)}" alt="" loading="lazy"><span>${i.ok == null ? "?" : i.ok ? "✔" : "✕"} ${esc(i.unit.slice(-3))}</span></button>`).join("");
  if (visionShown === pick.id) return;       // não recarrega a foto a cada segundo
  visionShown = pick.id;
  const mark = pick.x != null ? `<i class="mark" style="left:${pick.x * 100}%;top:${pick.y * 100}%"></i>` : "";
  $("vision-shot").innerHTML = `<div class="frame ${pick.ok === 0 ? "nok" : pick.ok ? "ok" : ""}"><img src="/api/vision/photo/${encodeURIComponent(pick.image)}" alt="Foto da placa ${esc(pick.unit)} na inspeção óptica">${mark}</div>
    <figcaption><b><a href="#" data-unit="${esc(pick.unit)}">${esc(pick.unit)}</a> · ${esc(verdictText(pick))}</b><span class="hint">${clock(pick.ts)} · ${pick.latency_ms ?? "—"} ms${pick.x != null ? " · o círculo marca onde o modelo viu o defeito" : ""}</span><span class="hint">${esc(truthText(pick))}</span></figcaption>`;
}
$("vision-thumbs").addEventListener("click", (e) => { const b = e.target.closest("[data-insp]"); if (b) { visionPick = +b.dataset.insp; renderVision(); } });

// ---------------------------------------------------------------- pedidos e AAS
const b64url = (t) => btoa(t).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
function renderAas() {
  const a = snap.aas, k = snap.line.kpi;
  $("aas-sub").textContent = `${num(k.planned)} unidade(s) planejada(s) aguardando fabricação`;
  $("orders").innerHTML = `<thead><tr><th>Pedido</th><th>Criado</th><th class="num">Unidades</th><th class="num">Planejadas</th><th class="num">Em produção</th><th class="num">Prontas</th><th class="num">Refugo</th></tr></thead><tbody>` +
    (snap.orders.length ? snap.orders.map((o) => `<tr><td><b>${o.id}</b> · ${esc(o.product)}</td><td>${clock(o.ts)}</td><td class="num">${o.quantity}</td><td class="num">${o.planned}</td><td class="num">${o.wip}</td><td class="num">${o.done}</td><td class="num">${o.scrap}</td></tr>`).join("")
      : `<tr><td colspan="7" class="hint">Nenhum pedido. Sem pedido, a unidade nasce na primeira estação.</td></tr>`) + `</tbody>`;
  const l = a.links, b = a.basyx;
  const sync = !b.enabled ? "sincronização com o BaSyx desligada (suba com o perfil AAS)"
    : b.ok ? `BaSyx em dia: ${num(b.synced)} envio(s), ${num(b.pending)} na fila` : `BaSyx indisponível: ${b.error || "conectando"} (${num(b.pending)} na fila)`;
  $("aas-links").innerHTML = `<p class="status ${!b.enabled ? "gray" : b.ok ? "green" : "red"}">${esc(sync)}</p>
    <dl class="links">
      <dt>Produtos · BaSyx (HTTP)</dt>
      <dd>Catálogo: <a href="${esc(l.gui)}" target="_blank" rel="noopener">${esc(l.gui)}</a></dd>
      <dd>API: <a href="${esc(l.basyx)}/shells" target="_blank" rel="noopener">${esc(l.basyx)}/shells</a></dd>
      <dd class="hint">O produto e cada unidade, inclusive as só planejadas, com a situação de fabricação.</dd>
      <dt>Estações · FA³ST (OPC UA)</dt>
      <dd>Endpoint: <code>${esc(l.opcua)}</code></dd>
      <dd>Também por HTTP: <a href="${esc(l.faaast_http)}/shells" target="_blank" rel="noopener">${esc(l.faaast_http)}/shells</a></dd>
      <dd class="hint">Máquina de estados, indicadores e capacidade de cada estação: Objects → AASEnvironment → Estado_&lt;estação&gt; → Estado → Value.</dd>
    </dl>`;
}
$("order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await fetch("/api/orders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantity: +$("order-qty").value }) });
  const d = await r.json().catch(() => ({}));
  $("order-msg").textContent = r.ok ? `Pedido ${d.id} planejado: ${d.units[0]} a ${d.units[d.units.length - 1]}.` : "Não foi possível planejar o pedido.";
});

// ---------------------------------------------------------------- gráficos (SVG)
const W = 640, H = 170, M = { l: 40, r: 12, t: 8, b: 20 };
const sx = (v, a, b) => M.l + ((v - a) / (b - a || 1)) * (W - M.l - M.r);
const sy = (v, a, b) => H - M.b - ((v - a) / (b - a || 1)) * (H - M.t - M.b);
function yAxis(lo, hi, ticks, fmt) {
  return ticks.map((t) => `<line x1="${M.l}" x2="${W - M.r}" y1="${sy(t, lo, hi)}" y2="${sy(t, lo, hi)}" stroke="var(--grid)"/><text x="${M.l - 6}" y="${sy(t, lo, hi) + 4}" text-anchor="end">${fmt(t)}</text>`).join("");
}
function spcChart(s) {
  const c = s.spc, pts = c.points;
  if (!pts.length) return "";
  const vals = pts.map((p) => p[1]);
  const lo = Math.min(c.lcl, ...vals) - c.target * 0.004, hi = Math.max(c.ucl, ...vals) + c.target * 0.004;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  const path = pts.map((p, i) => (i ? "L" : "M") + sx(p[0], t0, t1).toFixed(1) + " " + sy(p[1], lo, hi).toFixed(1)).join("");
  const out = pts.filter((p) => p[1] > c.ucl || p[1] < c.lcl).map((p) => `<rect x="${sx(p[0], t0, t1) - 4}" y="${sy(p[1], lo, hi) - 4}" width="8" height="8" rx="2" fill="var(--critical)" stroke="var(--surface)" stroke-width="2"/>`).join("");
  const lvl = c.level || "green";
  const label = c.level ? (c.level === "red" ? "fora de controle: " : "atenção: ") + c.rule : "sob controle";
  const last = pts[pts.length - 1];
  return `<div class="chart"><div class="title"><b>${esc(c.label)} · ${esc(c.unit)}</b><span class="status ${lvl}">${esc(label)}</span></div>
    <svg viewBox="0 0 ${W} ${H}" data-owntip data-chart="spc" data-station="${s.id}" role="img" aria-label="Carta de controle de ${esc(c.label)}">
      ${yAxis(lo, hi, [c.lcl, c.target, c.ucl], (v) => num(v, 1))}
      <rect x="${M.l}" y="${sy(c.ucl, lo, hi)}" width="${W - M.l - M.r}" height="${sy(c.lcl, lo, hi) - sy(c.ucl, lo, hi)}" fill="var(--band)"/>
      <line x1="${M.l}" x2="${W - M.r}" y1="${sy(c.target, lo, hi)}" y2="${sy(c.target, lo, hi)}" stroke="var(--axis)"/>
      <path d="${path}" fill="none" stroke="var(--series)" stroke-width="2" stroke-linejoin="round"/>${out}
      <circle cx="${sx(last[0], t0, t1)}" cy="${sy(last[1], lo, hi)}" r="4" fill="var(--series)" stroke="var(--surface)" stroke-width="2"/>
      <text x="${M.l}" y="${H - 4}">${clock(t0)}</text><text x="${W - M.r}" y="${H - 4}" text-anchor="end">${clock(t1)}</text>
      <line class="cross" y1="${M.t}" y2="${H - M.b}" stroke="var(--ink2)" stroke-dasharray="3 3" visibility="hidden"/>
    </svg><div class="hint">faixa = limites de controle (alvo ± 3σ); quadrados vermelhos = pontos fora dos limites</div></div>`;
}
function cycleChart() {
  // Pequenos múltiplos: um painel por estação, mesma escala relativa ao ciclo ideal (1,0 = ideal).
  const stations = snap.stations.filter((s) => s.recent.length);
  if (!stations.length) return `<p class="hint">Sem ciclos ainda.</p>`;
  const h = 86, w = W / stations.length, top = 2.2;
  const y = (r) => h - 16 - (Math.min(r, top) / top) * (h - 26);
  const panels = stations.map((s, i) => {
    const x0 = i * w + 6, x1 = (i + 1) * w - 6, n = s.recent.length;
    const dots = s.recent.map((p, j) => {
      const cx = x0 + ((j + 0.5) / Math.max(n, 12)) * (x1 - x0), cy = y(p[1] / s.ideal_cycle_s);
      const tip = `${s.name}: ${num(p[1], 1)} s · ${p[2] ? "aprovada" : "reprovada"} · ${clock(p[0])}`;
      return p[2] ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4" fill="var(--series)" stroke="var(--surface)" stroke-width="1.5" data-tip="${esc(tip)}"/>`
        : `<rect x="${(cx - 4).toFixed(1)}" y="${(cy - 4).toFixed(1)}" width="8" height="8" rx="2" fill="var(--critical)" stroke="var(--surface)" stroke-width="1.5" data-tip="${esc(tip)}"/>`;
    }).join("");
    return `<line x1="${x0}" x2="${x1}" y1="${y(1)}" y2="${y(1)}" stroke="var(--ink2)" stroke-dasharray="4 3"/><line x1="${x0}" x2="${x1}" y1="${h - 16}" y2="${h - 16}" stroke="var(--axis)"/>${dots}
      <text x="${(x0 + x1) / 2}" y="${h - 3}" text-anchor="middle">${esc(s.id)} · ideal ${num(s.ideal_cycle_s)} s</text>`;
  }).join("");
  return `<div class="chart"><div class="title"><b>Tempo de ciclo dos últimos ciclos, por estação</b></div>
    <svg viewBox="0 0 ${W} ${h}" role="img" aria-label="Tempo de ciclo por estação">${panels}</svg>
    <div class="legend"><span>aprovada</span><span class="nok">reprovada</span><span class="ideal">ciclo ideal da estação</span></div></div>`;
}
function renderCharts() {
  if (document.querySelector("#charts svg:hover")) return; // não redesenha sob o cursor
  $("charts").innerHTML = snap.stations.filter((s) => s.spc).map(spcChart).join("") + cycleChart();
}
$("charts").addEventListener("mousemove", (e) => {
  if (e.target.closest("[data-tip]")) return;
  const svg = e.target.closest('svg[data-chart="spc"]');
  if (!svg || !snap) return;
  const s = snap.stations.find((x) => x.id === svg.dataset.station), pts = s.spc.points;
  const box = svg.getBoundingClientRect(), x = ((e.clientX - box.left) / box.width) * W;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  let best = pts[0];
  for (const p of pts) if (Math.abs(sx(p[0], t0, t1) - x) < Math.abs(sx(best[0], t0, t1) - x)) best = p;
  const cross = svg.querySelector(".cross"), cx = sx(best[0], t0, t1);
  cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
  showTip(`${num(best[1], 1)} ${s.spc.unit} · ${clock(best[0])}`, e);
});
$("charts").addEventListener("mouseleave", () => { hideTip(); if (snap) { $("charts").innerHTML = ""; renderCharts(); } });

// ---------------------------------------------------------------- abas
document.querySelectorAll("#view-m3 .tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#view-m3 .tabs button").forEach((x) => x.setAttribute("aria-selected", x === b));
  document.querySelectorAll("#view-m3 .tab").forEach((t) => (t.hidden = t.id !== "tab-" + b.dataset.tab));
  if (b.dataset.tab === "trace") loadRecent();
}));
const openTab = (name) => document.querySelector(`#view-m3 .tabs button[data-tab="${name}"]`).click();

// rastreabilidade
async function loadRecent() {
  const units = await (await fetch("/api/units?limit=24")).json();
  const label = { wip: "em processo", rework: "retrabalho", done: "pronta", scrap: "refugo", removed: "retirada" };
  $("trace-recent").innerHTML = units.map((u) => `<button class="chip ${u.status}" data-unit="${esc(u.id)}" title="${label[u.status]}">${esc(u.id)}${u.status === "scrap" ? " ✕" : u.status === "rework" ? " ▲" : u.status === "done" ? " ✔" : ""}</button>`).join("");
}
async function showUnit(id) {
  location.hash = "#m3";
  openTab("trace");
  $("trace-id").value = id;
  const r = await fetch("/api/units/" + encodeURIComponent(id));
  if (!r.ok) { $("trace-out").innerHTML = `<p>Unidade <b>${esc(id)}</b> não encontrada.</p>`; return; }
  const d = await r.json(), u = d.unit;
  const label = { planned: "planejada (ainda não fabricada)", wip: "em processo", rework: "aguardando retrabalho", done: "pronta", scrap: "refugada", removed: "retirada da linha (simulador reiniciado)" }[u.status];
  const aasLink = snap?.aas?.basyx?.enabled ? ` · <a href="${esc(snap.aas.links.basyx)}/shells/${b64url("urn:sfal:aas:unit:" + u.id)}" target="_blank" rel="noopener">AAS no BaSyx</a>` : "";
  const lead = u.finished_ts && u.status !== "removed" ? dur(u.finished_ts - u.created_ts) : "—";
  let prevEnd = null;
  const rows = d.steps.map((s) => {
    const wait = prevEnd != null ? dur(Math.max(0, s.start_ts - prevEnd)) : "—";
    if (s.end_ts) prevEnd = s.end_ts;
    const res = s.end_ts == null ? "em andamento" : s.ok ? "✔ aprovada" : "✕ reprovada";
    return `<tr><td>${esc(s.station_name)}</td><td class="num">${s.attempt}</td><td>${clock(s.start_ts)}</td><td class="num">${wait}</td><td class="num">${s.dur_ms == null ? "—" : num(s.dur_ms / 1000, 1) + " s"}</td><td>${res}${s.degraded ? " · modo degradado" : ""}</td><td class="num">${s.temp == null ? "—" : num(s.temp, 1) + " °C"}</td></tr>`;
  }).join("");
  const log = d.log.map((e) => `<li><time>${clock(e.ts)}</time><span class="${e.level}"></span><span>${esc(e.message)}</span></li>`).join("");
  $("trace-out").innerHTML = `<p><b>${esc(u.id)}</b> · ${label} · entrou às ${clock(u.created_ts)} · lead time ${lead} · ${u.fails} reprovação(ões)${u.next_station ? " · esperada em <b>" + esc(u.next_station) + "</b>" : ""}${u.order_id ? " · pedido " + u.order_id : ""}${aasLink}</p>
    <div class="table-wrap"><table><thead><tr><th>Estação</th><th class="num">Tentativa</th><th>Início</th><th class="num">Espera antes</th><th class="num">Ciclo</th><th>Resultado</th><th class="num">Temp. na estação</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${d.inspections?.length ? `<div class="thumbs" style="margin-top:12px">${d.inspections.map((i) => `<a class="thumb ${i.ok === 0 ? "nok" : ""}" href="/api/vision/photo/${encodeURIComponent(i.image)}" target="_blank" rel="noopener" title="${esc(verdictText(i))}"><img src="/api/vision/photo/${encodeURIComponent(i.image)}" alt="Foto da inspeção óptica"><span>${esc(verdictText(i))}</span></a>`).join("")}</div>` : ""}
    ${log ? `<ol class="log" style="margin-top:10px">${log}</ol>` : ""}`;
}
$("trace-form").addEventListener("submit", (e) => { e.preventDefault(); const id = $("trace-id").value.trim(); if (id) showUnit(id); });
document.addEventListener("click", (e) => { const a = e.target.closest("[data-unit]"); if (a) { e.preventDefault(); showUnit(a.dataset.unit); } });

// assistente
async function stream(url, body, out) {
  out.textContent = "…";
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : null });
    if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText);
    const reader = r.body.getReader(), dec = new TextDecoder();
    out.textContent = "";
    for (;;) { const { done, value } = await reader.read(); if (done) break; out.textContent += dec.decode(value, { stream: true }); }
  } catch (err) { out.textContent = "Não foi possível obter a resposta: " + err.message; }
}
const ask = (q) => { $("ai-q").value = q; stream("/api/assistant", { question: q }, $("ai-out")); };
$("ai-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("ai-q").value.trim(); if (q) ask(q); });
$("ai-report").addEventListener("click", () => stream("/api/assistant/report", null, $("ai-out")));
$("ai-suggest").innerHTML = ["Onde está o gargalo e o que fazer?", "Por que o FPY está abaixo da meta?", "Alguma estação precisa de atenção agora?", "Resuma a última hora em três linhas."].map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
$("ai-suggest").addEventListener("click", (e) => { if (e.target.dataset.q) ask(e.target.dataset.q); });

// e se?
function renderScenarios() {
  const el = $("whatif-scenarios");
  if (el.childElementCount || !snap.scenarios) return;
  el.innerHTML = Object.entries(snap.scenarios).map(([k, label]) => `<label title="${esc(label)}"><input type="checkbox" value="${esc(k)}" checked> ${esc(k)}</label>`).join("");
}
$("whatif-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const scenarios = [...document.querySelectorAll("#whatif-scenarios input:checked")].map((i) => i.value);
  if (!scenarios.length) return;
  const out = $("whatif-out"), btn = e.target.querySelector("button");
  btn.disabled = true; out.innerHTML = `<p class="hint">Simulando…</p>`;
  try {
    const r = await fetch("/api/whatif", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenarios, hours: +$("whatif-hours").value }) });
    if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText);
    const res = await r.json(), t = snap.line.targets;
    const cell = (x, key) => `<td class="num"><span class="status ${x.levels[key]}">${pct(x.line[key])}</span></td>`;
    out.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Cenário</th><th class="num">FPY</th><th class="num">RTY</th><th class="num">OEE</th><th class="num">Prontas</th><th class="num">Refugo</th><th class="num">WIP final</th><th class="num">Lead time</th><th>Gargalo</th><th class="num">Defeitos que escaparam</th></tr></thead><tbody>
      ${res.map((x) => `<tr><td><b>${esc(x.scenario)}</b><div class="hint">${esc(x.label)}</div></td>${cell(x, "fpy")}${cell(x, "rty")}${cell(x, "oee")}<td class="num">${x.line.done}</td><td class="num">${x.line.scrap}</td><td class="num">${x.line.wip}</td><td class="num">${dur(x.line.lead_time_avg_s)}</td><td>${esc(x.stations[x.line.bottleneck]?.name ?? "—")}</td><td class="num">${x.escaped_defects}</td></tr>`).join("")}
      <tr><td class="hint">meta / referência</td>${["fpy", "rty", "oee"].map((k) => `<td class="num hint">${t[k] ? pct(t[k].goal, 0) + " / " + pct(t[k].baseline, 0) : "—"}</td>`).join("")}<td colspan="6"></td></tr>
      </tbody></table></div><p class="hint">Simulado em ${num(res.reduce((a, x) => a + x.wall_s, 0), 1)} s · semente ${res[0].seed}.</p>`;
  } catch (err) { out.innerHTML = `<p>Falha na simulação: ${esc(err.message)}</p>`; }
  btn.disabled = false;
});

// falhas provocadas (só com o simulador no ar)
function renderSim() {
  const hint = $("sim-hint"), box = $("sim-controls");
  if (!snap.sim) { hint.textContent = "O simulador não está no ar. Com placas reais, as falhas são as de verdade."; box.innerHTML = ""; return; }
  hint.textContent = "Falhas provocadas na planta simulada, para ver a linha reagir." + (snap.sim.real?.length ? ` Placas reais: ${snap.sim.real.join(", ")}.` : "");
  if (box.childElementCount) return;
  const opts = snap.sim.stations.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  box.innerHTML = `<label>Estação <select id="sim-station">${opts}</select></label><label>por <input id="sim-seconds" type="number" min="5" max="600" value="40"> s</label>` +
    Object.entries(snap.sim.faults).map(([k, label]) => `<button data-fault="${esc(k)}">${esc(label)}</button>`).join("");
}
$("sim-controls").addEventListener("click", async (e) => {
  const fault = e.target.dataset.fault;
  if (!fault) return;
  const body = { fault, station: $("sim-station").value, seconds: +$("sim-seconds").value };
  if (fault === "oven_drift" || fault === "defect_burst") delete body.station;
  const r = await fetch("/api/sim/inject", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  $("sim-hint").textContent = r.ok ? `Enviado: ${e.target.textContent}.` : "Não foi possível enviar o comando.";
});

$("btn-shift").addEventListener("click", async () => { if (confirm("Iniciar novo turno? Os indicadores passam a contar a partir de agora.")) await fetch("/api/shift", { method: "POST" }); });
export function init() {
  onSnapshot((s) => { snap = s; render(); });
  loadRecent();
  setInterval(() => { if (!$("tab-trace").hidden && !$("trace-out").innerHTML) loadRecent(); }, 5000);
}
