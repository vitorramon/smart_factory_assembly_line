// Utilitários compartilhados pelas quatro abas.
export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const num = (v, d = 0) => (v == null ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const pct = (v, d = 1) => (v == null ? "—" : num(v * 100, d) + " %");
export const pp = (v, d = 1) => (v == null ? "—" : (v >= 0 ? "+" : "−") + num(Math.abs(v) * 100, d) + " p.p.");
export const dur = (s) => (s == null ? "—" : s >= 90 ? num(s / 60, 1) + " min" : num(s, 0) + " s");
export const clock = (ts) => new Date(ts * 1000).toLocaleTimeString("pt-BR");
export const hm = (s) => `${Math.floor(s / 3600)} h ${String(Math.floor(s / 60) % 60).padStart(2, "0")} min`;

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}
export async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : null });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r;
}

// Situação contra referência e meta: mesma regra em todas as abas.
export const STATUS = { green: "na meta", yellow: "entre referência e meta", red: "abaixo da referência", gray: "sem dado" };
export const level = (v, base, goal) => (v == null ? "gray" : v >= goal ? "green" : v >= base ? "yellow" : "red");

// Dica flutuante: qualquer elemento com data-tip mostra o texto ao passar o cursor.
const tip = $("tip");
export function showTip(text, e) {
  tip.textContent = text;
  tip.hidden = false;
  tip.style.left = Math.max(8, Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8)) + "px";
  tip.style.top = Math.max(8, e.clientY - 34) + "px";
}
export const hideTip = () => (tip.hidden = true);
document.addEventListener("mousemove", (e) => {
  const mark = e.target.closest?.("[data-tip]");
  if (mark) showTip(mark.dataset.tip, e);
  else if (!e.target.closest?.("[data-owntip]")) hideTip();
});
