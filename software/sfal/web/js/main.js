// Ponto de entrada: quatro abas, cada uma um módulo carregado na primeira visita.
//   #m1 problema e metas · #m2 simulação · #m3 linha conectada · #sintese do problema ao resultado
import { connect } from "./live.js";
import { $ } from "./util.js";

const VIEWS = {
  m1: () => import("./m1.js"),
  m2: () => import("./m2.js"),
  m3: () => import("./m3.js"),
  sintese: () => import("./sintese.js"),
};
const loaded = {};

async function open(name) {
  if (!VIEWS[name]) name = "m3";
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + name));
  document.querySelectorAll(".views button").forEach((b) => b.setAttribute("aria-selected", b.dataset.view === name));
  for (const [k, mod] of Object.entries(loaded)) if (k !== name) (await mod).show?.(false);
  if (!loaded[name]) {
    loaded[name] = VIEWS[name]().then(async (mod) => { await mod.init(); return mod; });
    loaded[name].catch((err) => { $("view-" + name).insertAdjacentHTML("afterbegin", `<p class="panel">Não foi possível abrir esta aba: ${err.message}</p>`); });
  }
  (await loaded[name]).show?.(true);
  window.scrollTo(0, 0);
}

document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => (location.hash = b.dataset.view)));
addEventListener("hashchange", () => open(location.hash.slice(1)));
connect();
open(location.hash.slice(1) || "m1");
