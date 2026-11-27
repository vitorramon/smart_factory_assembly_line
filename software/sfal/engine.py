"""Motor da linha: recebe as mensagens das estações e mantém o estado da fábrica.

Não conhece MQTT nem relógio de parede: `handle(topic, payload, now)` e `tick(now)` recebem o
instante, e os comandos saem por `publish`. Assim o mesmo motor serve à linha ao vivo
(sfal/mqtt.py) e ao "E se?" em tempo acelerado (sfal/sim/whatif.py).

Responsabilidades: carimbar o instante dos eventos (o dispositivo só manda `age_ms`), descartar
duplicatas, decidir a liberação de cada unidade (rota, qualidade na fonte, jidoka), registrar a
genealogia, as paradas e os alertas, e comandar a torre luminosa.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import kpi
from .config import Config, Station
from .spc import Chart

PREFIX = "sfal/v1/"
Publish = Callable[[str, str, int, bool], Any]

REASONS = {
    "upstream_fail": "reprovada em estação anterior",
    "skipped_step": "pulou uma estação da rota",
    "already_done": "já passou por esta estação",
    "unknown_unit": "unidade desconhecida",
    "scrapped": "unidade refugada",
    "in_process": "unidade em processo em outra estação",
    "no_unit": "não há unidade aguardando esta estação",
    "hold": "estação retida por alarme de processo",
    "no_server": "servidor não respondeu",
    "no_link": "sem rede",
}


@dataclass
class Live:
    """Estado ao vivo de uma estação (o que a telemetria e o status dizem)."""

    online: bool = False
    seen: bool = False
    hw: str = ""
    fw: str = ""
    boot: int | None = None
    last_seq: int = 0
    gaps: int = 0
    last_seen: float = 0.0
    state: str = "?"
    unit: str = ""
    cycle_ms: int = 0
    cycle_at: float = 0.0
    call: bool = False
    temp: float | None = None
    rssi: int = 0
    queued: int = 0
    dropped: int = 0
    reason: str = ""
    light: str = "auto"
    hold: bool = False
    last_block: tuple[str, str] | None = None  # evita repetir a mesma recusa no diário
    recent: deque = field(default_factory=lambda: deque(maxlen=40))  # (ts, dur_s, ok)


class Engine:
    def __init__(self, cfg: Config, db: sqlite3.Connection, publish: Publish):
        self.cfg = cfg
        self.db = db
        self.publish = publish
        self.lock = threading.RLock()
        self.live = {s.id: Live() for s in cfg.stations}
        self.charts = {
            s.id: Chart(target=float(s.spc["target"]), sigma=float(s.spc["sigma"])) for s in cfg.stations if s.spc
        }
        self.dirty_units: set[str] = set()   # unidades alteradas desde a última sincronização com o AAS
        self.sim_status: dict[str, Any] | None = None
        self.rejected = 0
        row = db.execute("SELECT value FROM meta WHERE key='window_start'").fetchone()
        self.window_start: float | None = float(row["value"]) if row else None
        row = db.execute("SELECT value FROM meta WHERE key='unit_counter'").fetchone()
        self._counter = int(row["value"]) if row else 0
        # Estado que não sobrevive a um reinício do servidor: nada está em processo.
        db.execute("UPDATE units SET busy=0 WHERE busy=1")
        db.execute("DELETE FROM steps WHERE end_ts IS NULL")

    # ------------------------------------------------------------------ partida

    def start(self, now: float) -> None:
        """Publica a configuração retida de cada estação e encerra o que ficou aberto."""
        with self.lock:
            if self.window_start is None:
                self._set_window(now)
            self.db.execute("UPDATE downtime SET end_ts=? WHERE end_ts IS NULL", (now,))
            self._auto_order(now)
            self.db.execute("UPDATE alerts SET closed_ts=? WHERE closed_ts IS NULL", (now,))
            r = self.cfg.rules
            for s in self.cfg.stations:
                cfg = {
                    "takt_ms": int(self.cfg.takt_s * 1000),
                    "tel_ms": int(r["tel_ms"]),
                    "release_timeout_ms": int(r["release_timeout_ms"]),
                    "interlock": bool(r["interlock"]),
                    "fail_open": bool(r["fail_open"]),
                }
                self.publish(f"{PREFIX}{s.id}/cmd/config", json.dumps(cfg), 1, True)
                self.publish(f"{PREFIX}{s.id}/cmd/light", '{"level":"auto"}', 1, True)

    def _set_window(self, now: float) -> None:
        self.window_start = now
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('window_start', ?)", (str(now),))

    # ------------------------------------------------------------------ pedidos e unidades planejadas

    def plan_order(self, quantity: int, now: float) -> dict[str, Any]:
        """Planeja um lote: as unidades passam a existir (com número de série) antes de serem fabricadas."""
        with self.lock:
            product = str(self.cfg.product["id"])
            cur = self.db.execute("INSERT INTO orders (ts, product, quantity) VALUES (?,?,?)", (now, product, quantity))
            first = self.cfg.stations[0].id
            units = []
            for _ in range(quantity):
                uid = self._new_unit_id()
                self.db.execute(
                    "INSERT INTO units (id, created_ts, planned_ts, status, next_station, ready_ts, order_id) "
                    "VALUES (?,?,?,?,?,?,?)", (uid, now, now, "planned", first, now, cur.lastrowid))
                units.append(uid)
            self.dirty_units.update(units)
            self._log(now, "info", None, None, "order", f"Pedido {cur.lastrowid}: {quantity} unidade(s) de {product} planejada(s) ({units[0]} a {units[-1]})")
            return {"id": cur.lastrowid, "product": product, "quantity": quantity, "units": units}

    def planned(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM units WHERE status='planned'").fetchone()[0]

    def _auto_order(self, now: float) -> None:
        o = self.cfg.orders
        if o.get("auto") and self.planned() <= max(1, int(o["lot_size"]) // 4):
            self.plan_order(int(o["lot_size"]), now)

    def _start_planned(self, st: Station, ts: float) -> str | None:
        """Primeira estação sem leitor: inicia a unidade planejada mais antiga."""
        row = self.db.execute("SELECT id FROM units WHERE status='planned' ORDER BY rowid LIMIT 1").fetchone()
        if not row:
            return None
        self.db.execute("UPDATE units SET status='wip', created_ts=?, ready_ts=?, next_station=? WHERE id=?",
                        (ts, ts, st.id, row["id"]))
        return row["id"]

    def orders(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT o.*, COALESCE(SUM(u.status='planned'),0) planned, COALESCE(SUM(u.status IN ('wip','rework')),0) wip, "
                "COALESCE(SUM(u.status='done'),0) done, COALESCE(SUM(u.status='scrap'),0) scrap "
                "FROM orders o LEFT JOIN units u ON u.order_id=o.id GROUP BY o.id ORDER BY o.id DESC LIMIT 20")]

    def new_shift(self, now: float) -> None:
        with self.lock:
            self._set_window(now)
            self._log(now, "info", None, None, "shift", "Novo turno: indicadores zerados a partir de agora")

    # ------------------------------------------------------------------ entrada

    def handle(self, topic: str, payload: str | bytes, now: float) -> None:
        if not topic.startswith(PREFIX):
            return
        parts = topic[len(PREFIX) :].split("/")
        if len(parts) < 2 or parts[1] == "cmd":
            return
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("payload não é objeto")
        except (ValueError, UnicodeDecodeError):
            self.rejected += 1
            return
        with self.lock:
            if parts[0] == "sim":
                if parts[1] == "status":
                    self.sim_status = data if data.get("online") else None
                    if data.get("online"):
                        self._sim_session(str(data.get("session", "")), now)
                return
            st = self.cfg.station(parts[0])
            if st is None:
                self.rejected += 1
                return
            try:
                if parts[1] == "status":
                    self._on_status(st, data, now)
                elif parts[1] == "tel":
                    self._on_tel(st, data, now)
                elif parts[1] == "evt" and len(parts) == 3:
                    self._on_event(st, parts[2], data, now)
            except (KeyError, TypeError, ValueError) as e:
                self.rejected += 1
                self._log(now, "warn", st.id, None, "rejected", f"Mensagem inválida em {topic}: {e}")

    def tick(self, now: float) -> None:
        """Chamado periodicamente: detecta estação muda e atualiza retenções e torres."""
        with self.lock:
            limit = float(self.cfg.rules["offline_after_s"])
            for s in self.cfg.stations:
                lv = self.live[s.id]
                if lv.online and now - lv.last_seen > limit:
                    self._set_online(s, False, now, "sem telemetria")
                self._update_light(s, now)
            self._auto_order(now)

    def _sim_session(self, session: str, now: float) -> None:
        """Simulador reiniciado: as unidades que ele tinha na linha deixaram de existir."""
        row = self.db.execute("SELECT value FROM meta WHERE key='sim_session'").fetchone()
        if not session or (row and row["value"] == session):
            return
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('sim_session', ?)", (session,))
        self.dirty_units.update(r["id"] for r in self.db.execute("SELECT id FROM units WHERE status IN ('wip','rework')"))
        n = self.db.execute(
            "UPDATE units SET status='removed', busy=0, next_station=NULL, finished_ts=? WHERE status IN ('wip','rework')",
            (now,),
        ).rowcount
        self.db.execute("DELETE FROM steps WHERE end_ts IS NULL")
        if n:
            self._log(now, "info", None, None, "sim", f"Simulador reiniciado: {n} unidade(s) da execução anterior retirada(s) da linha")

    # ------------------------------------------------------------------ status e telemetria

    def _set_online(self, st: Station, online: bool, now: float, why: str = "") -> None:
        lv = self.live[st.id]
        if online == lv.online:
            return
        lv.online = online
        if online:
            self._close_downtime(st.id, "offline", now)
            self._close_alert(st.id, "offline", now)
            if lv.seen:
                self._log(now, "info", st.id, None, "online", f"{st.name} voltou a ficar online")
            lv.seen = True
        else:
            lv.state = "?"
            self._open_downtime(st.id, "offline", now)
            self._open_alert(now, st.id, "offline", "red", f"{st.name} offline" + (f" ({why})" if why else ""))

    def _on_status(self, st: Station, d: dict, now: float) -> None:
        lv = self.live[st.id]
        if d.get("online"):
            lv.hw, lv.fw = str(d.get("hw", "")), str(d.get("fw", ""))
            boot = int(d["boot"])
            if lv.boot is not None and boot != lv.boot:
                self._log(now, "warn", st.id, None, "reboot", f"{st.name} reiniciou")
            if boot != lv.boot:
                lv.boot, lv.last_seq = boot, 0
            lv.last_seen = now
            self._set_online(st, True, now)
        else:
            self._set_online(st, False, now, "conexão perdida")

    def _on_tel(self, st: Station, d: dict, now: float) -> None:
        lv = self.live[st.id]
        lv.last_seen = now
        if not lv.online:
            self._set_online(st, True, now)
        lv.state = str(d.get("state", "?"))
        lv.unit = str(d.get("unit", ""))
        lv.cycle_ms, lv.cycle_at = int(d.get("cycle_ms", 0)), now
        lv.rssi = int(d.get("rssi", 0))
        lv.queued, lv.dropped = int(d.get("queued", 0)), int(d.get("dropped", 0))
        lv.reason = str(d.get("reason", ""))
        temp = d.get("temp")
        lv.temp = float(temp) if isinstance(temp, (int, float)) and -50 < temp < 500 else None
        chart = self.charts.get(st.id)
        # Amostragem regular: a telemetria extra enviada a cada mudança de estado não entra na carta.
        period = float(self.cfg.rules["tel_ms"]) / 1000.0 * 0.9
        if chart and lv.temp is not None and (not chart.points or now - chart.points[-1][0] >= period):
            before = chart.level
            level, rule = chart.add(now, lv.temp)
            if level != before:
                self._close_alert(st.id, "spc", now)
                if level:
                    label = st.spc.get("label", st.name)
                    unit = st.spc.get("unit", "")
                    self._open_alert(
                        now, st.id, "spc", level, f"{label}: {rule} ({lv.temp:.1f} {unit}, alvo {chart.target:g})"
                    )
                else:
                    self._log(now, "info", st.id, None, "spc", f"{st.spc.get('label', st.name)} voltou ao controle")
            self._update_hold(st, now)

    # ------------------------------------------------------------------ eventos

    def _fresh(self, st: Station, d: dict, now: float) -> bool:
        """Deduplicação por (boot, seq). Conta lacunas."""
        lv = self.live[st.id]
        boot, seq = int(d["boot"]), int(d["seq"])
        if boot != lv.boot:
            lv.boot, lv.last_seq = boot, 0
        if seq <= lv.last_seq:
            return False
        if lv.last_seq and seq > lv.last_seq + 1:
            lv.gaps += seq - lv.last_seq - 1
            self._log(now, "warn", st.id, None, "gap", f"{st.name}: {seq - lv.last_seq - 1} evento(s) perdido(s)")
        lv.last_seq = seq
        return True

    def _on_event(self, st: Station, kind: str, d: dict, now: float) -> None:
        if not self._fresh(st, d, now):
            return
        ts = now - max(0, int(d.get("age_ms", 0))) / 1000.0
        if kind == "scan":
            self._on_scan(st, d, ts, now)
        elif kind == "cycle":
            self._on_cycle(st, d, ts)
        elif kind == "call":
            self._on_call(st, bool(d["on"]), ts)

    def _on_call(self, st: Station, on: bool, ts: float) -> None:
        self.live[st.id].call = on
        if on:
            self._open_downtime(st.id, "call", ts)
            self._open_alert(ts, st.id, "call", "red", f"Chamado aberto em {st.name}")
        else:
            dur = self._close_downtime(st.id, "call", ts)
            self._close_alert(st.id, "call", ts)
            self._log(ts, "info", st.id, None, "call", f"Chamado encerrado em {st.name} ({dur:.0f} s parada)")

    def _new_unit_id(self) -> str:
        while True:
            self._counter += 1
            uid = f"U-{self._counter:06d}"
            if not self.db.execute("SELECT 1 FROM units WHERE id=?", (uid,)).fetchone():
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('unit_counter', ?)", (str(self._counter),))
                return uid

    def _create_unit(self, uid: str, st: Station, ts: float) -> None:
        self.db.execute(
            "INSERT INTO units (id, created_ts, status, next_station, ready_ts) VALUES (?,?,?,?,?)",
            (uid, ts, "wip", st.id, ts),
        )

    def _fifo(self, st: Station) -> str | None:
        row = self.db.execute(
            "SELECT id FROM units WHERE next_station=? AND busy=0 AND status IN ('wip','rework') "
            "ORDER BY ready_ts LIMIT 1",
            (st.id,),
        ).fetchone()
        return row["id"] if row else None

    def _decide(self, st: Station, uid: str, ts: float) -> tuple[bool, str, str]:
        """Decide a liberação: (ok, unidade, motivo da recusa)."""
        strict = bool(self.cfg.rules["interlock"])
        if strict and self.live[st.id].hold:
            return False, uid, "hold"
        if not uid:  # estação sem leitor: o servidor escolhe
            if st.index == 0:
                uid = self._start_planned(st, ts)
                if uid is None:                       # sem pedido planejado: a unidade nasce aqui, como antes
                    uid = self._new_unit_id()
                    self._create_unit(uid, st, ts)
                return True, uid, ""
            uid = self._fifo(st) or ""
            if uid:
                return True, uid, ""
            if strict:
                return False, "", "no_unit"
            uid = self._new_unit_id()
            self._create_unit(uid, st, ts)
            return True, uid, ""
        u = self.db.execute("SELECT * FROM units WHERE id=?", (uid,)).fetchone()
        if u is None:
            if st.index == 0 or not strict:
                self._create_unit(uid, st, ts)
                return True, uid, ""
            return False, uid, "unknown_unit"
        if u["status"] == "planned":                  # etiqueta de uma unidade planejada lida na primeira estação
            if st.index == 0 or not strict:
                self.db.execute("UPDATE units SET status='wip', created_ts=?, ready_ts=?, next_station=? WHERE id=?",
                                (ts, ts, st.id, uid))
                return True, uid, ""
            return False, uid, "skipped_step"
        if not strict:
            return True, uid, ""
        if u["status"] == "scrap":
            return False, uid, "scrapped"
        if u["status"] == "done":
            return False, uid, "already_done"
        if u["busy"]:
            open_here = self.db.execute(
                "SELECT 1 FROM steps WHERE unit=? AND station=? AND end_ts IS NULL", (uid, st.id)
            ).fetchone()
            if not open_here:
                return False, uid, "in_process"
        expected = self.cfg.station(u["next_station"])
        if expected is None or expected.id == st.id:
            return True, uid, ""
        if st.index < expected.index:
            return False, uid, "already_done"
        return False, uid, "upstream_fail" if u["status"] == "rework" else "skipped_step"

    def _open_step(self, st: Station, uid: str, start_ts: float) -> int:
        # Uma estação processa uma unidade por vez: passo aberto de outra unidade foi abandonado.
        for row in self.db.execute(
            "SELECT id, unit FROM steps WHERE station=? AND end_ts IS NULL", (st.id,)
        ).fetchall():
            self.db.execute("DELETE FROM steps WHERE id=?", (row["id"],))
            self.db.execute("UPDATE units SET busy=0 WHERE id=?", (row["unit"],))
        attempt = self.db.execute(
            "SELECT COUNT(*) c FROM steps WHERE unit=? AND station=?", (uid, st.id)
        ).fetchone()["c"]
        cur = self.db.execute(
            "INSERT INTO steps (unit, station, attempt, start_ts) VALUES (?,?,?,?)", (uid, st.id, attempt + 1, start_ts)
        )
        self.db.execute("UPDATE units SET busy=1 WHERE id=?", (uid,))
        self.dirty_units.add(uid)
        return cur.lastrowid

    def _on_scan(self, st: Station, d: dict, ts: float, now: float) -> None:
        uid = str(d.get("unit", ""))[:31]
        ok, uid, reason = self._decide(st, uid, ts)
        lv = self.live[st.id]
        if ok:
            self._open_step(st, uid, ts)
            lv.last_block = None
            reply = {"req": int(d["seq"]), "ok": True, "unit": uid}
        else:
            reply = {"req": int(d["seq"]), "ok": False, "unit": uid, "reason": reason}
        if not ok and lv.last_block != (uid, reason):
            lv.last_block = (uid, reason)
            self._log(
                ts, "warn", st.id, uid or None, f"blocked:{reason}",
                f"{st.name} bloqueou {uid or 'o início'}: {REASONS.get(reason, reason)}",
            )
        self.publish(f"{PREFIX}{st.id}/cmd/release", json.dumps(reply), 1, False)

    def _on_cycle(self, st: Station, d: dict, ts: float) -> None:
        uid = str(d.get("unit", ""))[:31]
        dur_ms = int(d["dur_ms"])
        ok = bool(d["ok"])
        degraded = bool(d.get("degraded", False))
        step = None
        if uid:
            step = self.db.execute(
                "SELECT id FROM steps WHERE unit=? AND station=? AND end_ts IS NULL ORDER BY id DESC LIMIT 1",
                (uid, st.id),
            ).fetchone()
        else:
            step = self.db.execute(
                "SELECT id, unit FROM steps WHERE station=? AND end_ts IS NULL ORDER BY id DESC LIMIT 1", (st.id,)
            ).fetchone()
            if step:
                uid = step["unit"]
        if step is None:
            # Ciclo sem liberação registrada (modo degradado, ou servidor reiniciado no meio do ciclo).
            if not uid:
                uid = self._fifo(st) or self._new_unit_id()
            if not self.db.execute("SELECT 1 FROM units WHERE id=?", (uid,)).fetchone():
                self._create_unit(uid, st, ts - dur_ms / 1000.0)
            step_id = self._open_step(st, uid, ts - dur_ms / 1000.0)
            if self.cfg.rules["interlock"]:
                self._log(ts, "warn", st.id, uid, "degraded", f"{st.name} processou {uid} sem liberação do servidor")
        else:
            step_id = step["id"]
        lv = self.live[st.id]
        self.db.execute(
            "UPDATE steps SET end_ts=?, dur_ms=?, ok=?, degraded=?, temp=? WHERE id=?",
            (ts, dur_ms, int(ok), int(degraded), lv.temp, step_id),
        )
        lv.recent.append((ts, dur_ms / 1000.0, ok))
        self._advance_unit(st, uid, ok, ts)

    def _advance_unit(self, st: Station, uid: str, ok: bool, ts: float) -> None:
        self.dirty_units.add(uid)
        if ok:
            if st.index == len(self.cfg.stations) - 1:
                self.db.execute(
                    "UPDATE units SET status='done', busy=0, next_station=NULL, finished_ts=?, ready_ts=? WHERE id=?",
                    (ts, ts, uid),
                )
            else:
                nxt = self.cfg.stations[st.index + 1].id
                self.db.execute(
                    "UPDATE units SET status='wip', busy=0, next_station=?, ready_ts=? WHERE id=?", (nxt, ts, uid)
                )
            return
        fails = self.db.execute(
            "SELECT COUNT(*) c FROM steps WHERE unit=? AND station=? AND ok=0", (uid, st.id)
        ).fetchone()["c"]
        scrap = st.on_fail == "scrap" or fails >= int(self.cfg.rules["max_attempts"])
        if scrap:
            self.db.execute(
                "UPDATE units SET status='scrap', busy=0, next_station=NULL, finished_ts=?, fails=fails+1 WHERE id=?",
                (ts, uid),
            )
            self._log(ts, "error", st.id, uid, "scrap", f"{uid} refugada em {st.name}")
        else:
            self.db.execute(
                "UPDATE units SET status='rework', busy=0, next_station=?, ready_ts=?, fails=fails+1 WHERE id=?",
                (st.id, ts, uid),
            )
            self._log(ts, "warn", st.id, uid, "nok", f"{uid} reprovada em {st.name}: vai para retrabalho")

    # ------------------------------------------------------------------ inspeção óptica por IA

    def record_inspection(self, station: str, unit: str, verdict: dict, truth: dict | None, image: str, now: float) -> int:
        """Registra o veredito do modelo e, havendo veredito, manda o resultado à estação (que encerra o ciclo)."""
        with self.lock:
            st = self.cfg.station(station)
            if st is None:
                raise ValueError(f"estação desconhecida: {station}")
            ok = verdict.get("ok")
            t = truth or {}
            cur = self.db.execute(
                "INSERT INTO inspections (ts, station, unit, ok, defect, place, x, y, score, model, latency_ms, error, "
                "truth, truth_kind, image) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now, station, unit, None if ok is None else int(ok), verdict.get("defect") or None,
                 verdict.get("where") or None, verdict.get("x"), verdict.get("y"), verdict.get("score"),
                 verdict.get("model"), verdict.get("latency_ms"), verdict.get("error") or None,
                 None if "defect" not in t else int(bool(t["defect"])), t.get("kind"), image),
            )
            self.dirty_units.add(unit)
            if ok is None:
                self._log(now, "warn", station, unit, "vision", f"Inspeção óptica sem veredito para {unit}: {verdict.get('error', '')}")
            else:
                if not ok:
                    self._log(now, "warn", station, unit, "vision",
                              f"Inspeção óptica reprovou {unit}: {verdict.get('defect') or 'defeito'}")
                self.publish(f"{PREFIX}{station}/cmd/result", json.dumps({"unit": unit, "ok": bool(ok)}), 1, False)
            return cur.lastrowid

    # ------------------------------------------------------------------ paradas, alertas, torre

    def _open_downtime(self, station: str, reason: str, ts: float) -> None:
        if not self.db.execute(
            "SELECT 1 FROM downtime WHERE station=? AND reason=? AND end_ts IS NULL", (station, reason)
        ).fetchone():
            self.db.execute("INSERT INTO downtime (station, reason, start_ts) VALUES (?,?,?)", (station, reason, ts))

    def _close_downtime(self, station: str, reason: str, ts: float) -> float:
        row = self.db.execute(
            "SELECT id, start_ts FROM downtime WHERE station=? AND reason=? AND end_ts IS NULL", (station, reason)
        ).fetchone()
        if not row:
            return 0.0
        self.db.execute("UPDATE downtime SET end_ts=? WHERE id=?", (max(ts, row["start_ts"]), row["id"]))
        return max(0.0, ts - row["start_ts"])

    def _open_alert(self, ts: float, station: str | None, kind: str, level: str, message: str) -> None:
        self.db.execute(
            "INSERT INTO alerts (ts, station, kind, level, message) VALUES (?,?,?,?,?)", (ts, station, kind, level, message)
        )
        self._log(ts, "error" if level == "red" else "warn", station, None, kind, message)

    def _close_alert(self, station: str, kind: str, ts: float) -> None:
        self.db.execute(
            "UPDATE alerts SET closed_ts=? WHERE station=? AND kind=? AND closed_ts IS NULL", (ts, station, kind)
        )

    def _update_hold(self, st: Station, now: float) -> None:
        chart = self.charts.get(st.id)
        hold = bool(self.cfg.rules["jidoka"] and chart and chart.level == "red")
        lv = self.live[st.id]
        if hold == lv.hold:
            return
        lv.hold = hold
        if hold:
            self._open_downtime(st.id, "hold", now)
            self._log(now, "error", st.id, None, "hold", f"Jidoka: {st.name} retida até o processo voltar ao controle")
        else:
            self._close_downtime(st.id, "hold", now)
            self._log(now, "info", st.id, None, "hold", f"{st.name} liberada")

    def _update_light(self, st: Station, now: float) -> None:
        lv = self.live[st.id]
        chart = self.charts.get(st.id)
        want = "red" if lv.hold else "yellow" if chart and chart.level else "auto"
        if want != lv.light:
            lv.light = want
            self.publish(f"{PREFIX}{st.id}/cmd/light", json.dumps({"level": want}), 1, True)

    def _log(self, ts: float, level: str, station: str | None, unit: str | None, kind: str, message: str) -> None:
        self.db.execute(
            "INSERT INTO log (ts, level, station, unit, kind, message) VALUES (?,?,?,?,?,?)",
            (ts, level, station, unit, kind, message),
        )

    # ------------------------------------------------------------------ leitura

    def snapshot(self, now: float) -> dict[str, Any]:
        with self.lock:
            return kpi.snapshot(self, now)

    def unit(self, uid: str) -> dict[str, Any] | None:
        with self.lock:
            u = self.db.execute("SELECT * FROM units WHERE id=?", (uid,)).fetchone()
            if not u:
                return None
            names = {s.id: s.name for s in self.cfg.stations}
            steps = [
                {**dict(r), "station_name": names.get(r["station"], r["station"])}
                for r in self.db.execute("SELECT * FROM steps WHERE unit=? ORDER BY start_ts, id", (uid,))
            ]
            log = [dict(r) for r in self.db.execute("SELECT * FROM log WHERE unit=? ORDER BY ts, id", (uid,))]
            insp = [dict(r) for r in self.db.execute("SELECT * FROM inspections WHERE unit=? ORDER BY ts, id", (uid,))]
            return {"unit": dict(u), "steps": steps, "log": log, "inspections": insp}

    def units(self, limit: int = 30, status: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            q = "SELECT * FROM units"
            args: list[Any] = []
            if status:
                q += " WHERE status=?"
                args.append(status)
            else:
                q += " WHERE status!='planned'"      # planejadas só aparecem quando pedidas
            q += " ORDER BY created_ts DESC LIMIT ?"
            args.append(limit)
            return [dict(r) for r in self.db.execute(q, args)]
