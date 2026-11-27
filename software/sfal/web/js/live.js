// Estado ao vivo da linha (M3): um WebSocket, vários assinantes.
import { $ } from "./util.js";

let snap = null;
const subscribers = new Set();
export const current = () => snap;
export function onSnapshot(fn) {
  subscribers.add(fn);
  if (snap) fn(snap);
}

function pill(id, on, text) {
  const el = $(id);
  el.className = "pill " + (on == null ? "" : on ? "on" : "off");
  if (text) el.textContent = text;
}

export function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => pill("pill-server", true);
  ws.onmessage = (e) => {
    snap = JSON.parse(e.data);
    pill("pill-broker", snap.broker);
    pill("pill-sim", snap.sim ? true : null, snap.sim ? "simulador no ar" : "sem simulador");
    pill("pill-ai", snap.assistant.available ? true : null, snap.assistant.available ? "IA local: " + snap.assistant.model : "IA local indisponível");
    for (const fn of subscribers) fn(snap);
  };
  ws.onclose = () => {
    pill("pill-server", false);
    setTimeout(connect, 2000);
  };
}
