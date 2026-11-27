// Desenho da linha do M2 em canvas: máquinas da SMT e as 12 estações manuais, cada uma com seu pictograma.
// Portado do painel da entrega do M2; os desenhos são os mesmos, agora separados do resto da interface.

const MC = { body: "#d6dbde", mid: "#aab2b8", dark: "#454b52", red: "#c4262d", scr: "#16222b", glow: "#5fd0e0", blk: "#1f2327" };
const PH = { frame: "#2b3138", pcb: "#2f9e6a", disp: "#101820", batt: "#5b9bd5", gold: "#e6b422", cover: "#8d99ae" };
const LAMP = { r: "#d03b3b", y: "#fab219", g: "#0ca30c" };
const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Ferramentas de desenho relativas à caixa (px, py, w, h): frações de 0 a 1.
function tools(x, px, py, w, h) {
  const X = (f) => px + w * f, Y = (f) => py + h * f, W = (f) => w * f, H = (f) => h * f;
  return {
    X, Y, W, H,
    R: (a, b, c, d, fill) => { x.fillStyle = fill; x.fillRect(X(a), Y(b), W(c), H(d)); },
    C: (a, b, r, fill) => { x.fillStyle = fill; x.beginPath(); x.arc(X(a), Y(b), r, 0, 6.283); x.fill(); },
  };
}

// Máquinas da SMT. kind: imp | spi | pp | oven | aoi | out; lamp: r | y | g
function drawMachine(x, kind, px, py, w, h, lamp) {
  const { X, Y, W, H, R, C } = tools(x, px, py, w, h);
  const tower = (f) => { R(f, 0.04, 0.03, 0.14, MC.dark); R(f - 0.05, 0, 0.1, 0.07, LAMP[lamp]); };
  R(0.04, 0.94, 0.92, 0.06, MC.dark);
  if (kind === "imp") {
    R(0.06, 0.22, 0.88, 0.72, MC.dark); R(0.06, 0.22, 0.16, 0.72, MC.body); R(0.06, 0.54, 0.88, 0.05, MC.red);
    R(0.3, 0.3, 0.4, 0.18, MC.mid); R(0.62, 0.66, 0.26, 0.2, MC.scr); R(0.65, 0.7, 0.2, 0.1, MC.glow); tower(0.5);
  } else if (kind === "spi") {
    R(0.06, 0.22, 0.88, 0.72, MC.mid); R(0.06, 0.22, 0.88, 0.1, MC.dark); R(0.06, 0.54, 0.88, 0.05, MC.red);
    R(0.14, 0.64, 0.34, 0.24, MC.dark); R(0.56, 0.62, 0.3, 0.22, MC.scr); R(0.6, 0.67, 0.22, 0.12, MC.glow); tower(0.5);
  } else if (kind === "pp") {
    R(0.06, 0.18, 0.88, 0.5, MC.body); R(0.06, 0.18, 0.88, 0.14, MC.dark); R(0.14, 0.36, 0.72, 0.16, MC.scr);
    R(0.06, 0.54, 0.88, 0.05, MC.red); R(0.1, 0.66, 0.8, 0.28, MC.blk);
    const reels = ["#e6b422", "#3a86d6", "#d8dde0", "#3ddc84"], r = Math.min(W(0.07), H(0.1));
    for (let i = 0; i < 4; i++) C(0.22 + i * 0.19, 0.8, r, reels[i]);
    tower(0.5);
  } else if (kind === "oven") {
    R(0.02, 0.4, 0.96, 0.54, MC.body);
    for (let i = 0; i < 3; i++) { x.fillStyle = MC.mid; x.beginPath(); x.ellipse(X(0.18 + i * 0.32), Y(0.4), W(0.15), H(0.14), 0, Math.PI, 0); x.fill(); }
    x.strokeStyle = MC.mid; x.lineWidth = 1;
    for (let i = 1; i < 6; i++) { x.beginPath(); x.moveTo(X(i / 6), Y(0.4)); x.lineTo(X(i / 6), Y(0.94)); x.stroke(); }
    R(0.46, 0.04, 0.08, 0.2, MC.dark); R(0.34, 0, 0.32, 0.14, MC.scr); R(0.37, 0.03, 0.26, 0.08, MC.glow); R(0.04, 0.66, 0.92, 0.04, MC.red);
  } else if (kind === "aoi") {
    R(0.06, 0.2, 0.88, 0.74, MC.body); R(0.06, 0.2, 0.88, 0.22, MC.dark); C(0.5, 0.31, Math.min(W(0.07), H(0.07)), MC.glow);
    R(0.06, 0.54, 0.88, 0.05, MC.red); R(0.14, 0.64, 0.5, 0.26, MC.mid); R(0.68, 0.62, 0.2, 0.22, MC.scr); R(0.7, 0.66, 0.16, 0.1, MC.glow); tower(0.2);
  } else { // saída da SMT: esteira com magazine
    R(0.08, 0.5, 0.84, 0.08, MC.dark); R(0.1, 0.58, 0.04, 0.36, MC.dark); R(0.86, 0.58, 0.04, 0.36, MC.dark);
    for (let i = 0; i < 7; i++) R(0.12 + i * 0.11, 0.46, 0.06, 0.04, MC.mid);
    x.strokeStyle = MC.dark; x.lineWidth = 2; C(0.72, 0.28, Math.min(W(0.2), H(0.22)), MC.body); x.stroke(); x.lineWidth = 1;
    R(0.2, 0.2, 0.3, 0.22, MC.body); R(0.22, 0.24, 0.2, 0.1, MC.scr);
  }
}

// Estações manuais, na ordem da linha: o desenho mostra o que entra no aparelho naquele posto.
// o: {busy, reject, progress (0..1)}
function drawManual(x, k, px, py, w, h, o) {
  const { X, Y, W, H, R, C } = tools(x, px, py, w, h);
  const arrow = (a, b) => { x.fillStyle = PH.gold; x.beginPath(); x.moveTo(X(a), Y(b + 0.1)); x.lineTo(X(a - 0.06), Y(b)); x.lineTo(X(a + 0.06), Y(b)); x.fill(); };
  const r1 = Math.min(W(0.1), H(0.1)), r2 = Math.min(W(0.05), H(0.05));
  const frame = () => R(0.3, 0.08, 0.4, 0.78, PH.frame);
  R(0, 0.92, 1, 0.08, MC.mid);
  if (k === 0) { // gravação de firmware: placa, cabo, gravador com barra de progresso
    R(0.06, 0.3, 0.34, 0.4, PH.pcb); R(0.12, 0.38, 0.1, 0.1, "#222"); R(0.26, 0.52, 0.08, 0.1, "#222"); R(0.4, 0.48, 0.2, 0.03, MC.dark);
    R(0.6, 0.24, 0.34, 0.5, MC.dark); R(0.63, 0.28, 0.28, 0.22, MC.scr); R(0.63, 0.6, 0.28, 0.07, "#3a424b"); R(0.63, 0.6, 0.28 * (o.busy ? o.progress : 0), 0.07, MC.glow);
  } else if (k === 1) { frame(); R(0.35, 0.16, 0.3, 0.56, PH.pcb); R(0.4, 0.22, 0.1, 0.1, "#222"); R(0.52, 0.42, 0.08, 0.1, "#222");
    [[0.36, 0.17], [0.62, 0.17], [0.36, 0.68], [0.62, 0.68]].forEach((p) => C(p[0], p[1], r2, PH.gold)); arrow(0.84, 0.2);
  } else if (k === 2) { frame(); R(0.33, 0.12, 0.34, 0.56, PH.disp); R(0.36, 0.15, 0.28, 0.04, MC.glow); R(0.45, 0.68, 0.1, 0.12, PH.gold); arrow(0.84, 0.2);
  } else if (k === 3) { frame(); R(0.35, 0.16, 0.3, 0.52, PH.batt); R(0.47, 0.2, 0.06, 0.1, "#fff"); R(0.4, 0.5, 0.2, 0.03, "#fff"); arrow(0.84, 0.2);
  } else if (k === 4) { frame(); C(0.5, 0.66, r1 * 1.2, PH.gold); C(0.5, 0.66, r1 * 0.7, MC.dark); R(0.4, 0.2, 0.2, 0.02, MC.mid); arrow(0.84, 0.4);
  } else if (k === 5) { frame(); C(0.4, 0.78, r2 * 1.4, PH.gold); C(0.4, 0.78, r2 * 0.6, MC.dark); R(0.45, 0.2, 0.1, 0.02, MC.mid); arrow(0.84, 0.5);
  } else if (k === 6) { frame(); R(0.34, 0.12, 0.32, 0.22, MC.dark); C(0.43, 0.23, r1 * 0.8, "#0b0f14"); C(0.57, 0.23, r1 * 0.8, "#0b0f14"); C(0.43, 0.23, r1 * 0.35, PH.gold); C(0.57, 0.23, r1 * 0.35, PH.gold); arrow(0.84, 0.1);
  } else if (k === 7) { frame(); R(0.33, 0.12, 0.34, 0.66, PH.disp); C(0.5, 0.17, r1 * 0.6, "#0b0f14"); C(0.5, 0.17, r1 * 0.25, PH.gold); R(0.4, 0.17, 0.06, 0.012, MC.mid); arrow(0.84, 0.1);
  } else if (k === 8) { frame(); R(0.7, 0.22, 0.05, 0.14, PH.gold); R(0.7, 0.42, 0.05, 0.14, PH.gold); C(0.46, 0.34, r1 * 0.7, MC.mid); C(0.46, 0.34, r2 * 0.5, MC.dark); arrow(0.86, 0.05);
  } else if (k === 9) { R(0.28, 0.02, 0.44, 0.3, PH.cover); arrow(0.5, 0.34); R(0.3, 0.48, 0.4, 0.42, PH.frame); R(0.34, 0.52, 0.32, 0.3, PH.pcb);
  } else if (k === 10) { // teste funcional: ✓ ou ✕ na tela
    frame(); R(0.33, 0.12, 0.34, 0.62, PH.disp);
    x.strokeStyle = o.reject ? LAMP.r : "#3ddc84"; x.lineWidth = 2; x.beginPath();
    if (o.reject) { x.moveTo(X(0.4), Y(0.3)); x.lineTo(X(0.6), Y(0.55)); x.moveTo(X(0.6), Y(0.3)); x.lineTo(X(0.4), Y(0.55)); }
    else { x.moveTo(X(0.4), Y(0.42)); x.lineTo(X(0.48), Y(0.55)); x.lineTo(X(0.62), Y(0.28)); }
    x.stroke(); x.lineWidth = 1; R(0.14, 0.34, 0.16, 0.03, PH.gold); R(0.7, 0.52, 0.16, 0.03, PH.gold);
  } else { R(0.4, 0.1, 0.2, 0.3, PH.frame); R(0.14, 0.36, 0.72, 0.5, "#c89b6d"); R(0.1, 0.28, 0.8, 0.12, "#b5855a"); R(0.2, 0.56, 0.24, 0.12, "#fff"); }
}

const machineKind = (name) => (name === "SPI" ? "spi" : name === "AOI" ? "aoi" : name.startsWith("Pick") ? "pp" : name.startsWith("Forno") ? "oven" : name === "Saída SMT" ? "out" : "imp");

// run: resposta de /api/m2/run · state: saída de snapshot() em m2.js · manualOrder: nomes das 12 estações manuais
export function drawLine(canvas, run, state, manualOrder) {
  const names = run.stations, narrow = canvas.clientWidth < 650;
  const isManual = (n) => run.manual.includes(n);
  const groups = [
    { title: "SMT · impressão, inspeção, colocação e refusão", ids: names.map((n, i) => (isManual(n) ? -1 : i)).filter((i) => i >= 0), cols: narrow ? 3 : 5 },
    { title: "Montagem manual · 12 estações em sequência", ids: names.map((n, i) => (isManual(n) ? i : -1)).filter((i) => i >= 0), cols: narrow ? 3 : 6 },
  ];
  const ROW = 150, height = groups.reduce((h, g) => h + 34 + Math.ceil(g.ids.length / g.cols) * ROW, 0);
  const w = canvas.clientWidth, d = devicePixelRatio || 1;
  canvas.style.height = height + "px";
  if (canvas.width !== Math.round(w * d) || canvas.height !== Math.round(height * d)) { canvas.width = Math.round(w * d); canvas.height = Math.round(height * d); }
  const x = canvas.getContext("2d");
  x.setTransform(d, 0, 0, d, 0, 0);
  x.clearRect(0, 0, w, height);
  const ink = token("--ink"), mut = token("--muted"), cell = token("--page"), line = token("--axis");
  const good = token("--good"), gold = token("--warning"), bad = token("--critical"), piece = token("--series");
  let base = 0;
  for (const group of groups) {
    x.fillStyle = mut; x.font = "12px system-ui"; x.textAlign = "left"; x.fillText(group.title, 0, base + 16);
    base += 34;
    const gap = 12, cw = (w - gap * (group.cols - 1)) / group.cols;
    group.ids.forEach((i, pos) => {
      const a = state[i], n = names[i];
      const px = (pos % group.cols) * (cw + gap), py = base + Math.floor(pos / group.cols) * ROW, sw = cw - 10;
      x.fillStyle = cell; x.fillRect(px, py, cw, 87);
      x.strokeStyle = a.reject ? bad : a.busy != null ? gold : line; x.lineWidth = a.reject || a.busy != null ? 2 : 1;
      x.strokeRect(px + 0.5, py + 0.5, cw - 1, 86);
      const k = manualOrder.indexOf(n);
      if (k < 0) drawMachine(x, machineKind(n), px + 10, py + 9, sw - 10, 66, a.reject ? "r" : a.busy != null ? "y" : "g");
      else drawManual(x, k, px + 12, py + 10, sw - 14, 64, { busy: a.busy != null, reject: a.reject, progress: a.progress });
      x.font = "10px system-ui"; x.textAlign = "left"; x.fillStyle = mut; x.fillText(String(i + 1).padStart(2, "0"), px + 5, py + 12);
      x.textAlign = "center"; x.fillStyle = ink; x.font = "11px system-ui"; x.fillText(n, px + cw / 2, py + 103, cw);
      x.fillStyle = mut; x.font = "10px system-ui";
      const cap = run.capacities[i];
      x.fillText(cap > 1 ? `${a.busyCount}/${cap} posições ocupadas` : a.busy != null ? "P" + String(a.busy).padStart(4, "0") : "Livre", px + cw / 2, py + 117);
      for (let j = 0; j < Math.min(a.queue, 6); j++) { x.fillStyle = piece; x.fillRect(px + 5 + j * 9, py + 124, 6, 6); }
      if (a.queue > 6) { x.fillStyle = a.queue > 30 ? bad : mut; x.textAlign = "left"; x.fillText("+" + (a.queue - 6), px + 62, py + 130); x.textAlign = "center"; }
      if (pos < group.ids.length - 1 && pos % group.cols !== group.cols - 1) { x.fillStyle = mut; x.fillText("→", px + cw + gap / 2, py + 50); }
    });
    base += Math.ceil(group.ids.length / group.cols) * ROW;
  }
}
