"""Indicadores da linha, calculados sobre o banco para uma janela de tempo.

Definições (as mesmas no painel, no "E se?" e nos testes):
  FPY da estação   unidades aprovadas na 1ª tentativa ÷ unidades que tiveram 1ª tentativa
  RTY              produto dos FPY das estações
  FPY da linha     unidades que saíram sem nenhuma reprovação ÷ unidades encerradas (prontas + refugo)
  OEE da estação   disponibilidade × desempenho × qualidade
                   D = (tempo planejado − paradas) ÷ tempo planejado     (paradas: chamado, offline, retenção)
                   P = ciclo ideal × ciclos ÷ tempo em operação, limitado a 1
                   Q = ciclos aprovados ÷ ciclos
  OEE da linha     unidades boas × takt ÷ tempo planejado   (quanto do ritmo do cliente a linha entregou)
  1 − COPQ         1 − (reprovações × custo de tratamento + refugos × custo da unidade) ÷ (iniciadas × valor da unidade)
  Lead time        da entrada na primeira estação à saída da última, por unidade pronta
"""

from __future__ import annotations

from typing import Any


def _union_seconds(intervals: list[tuple[float, float]]) -> float:
    total, end = 0.0, float("-inf")
    for a, b in sorted(intervals):
        if b <= end:
            continue
        total += b - max(a, end)
        end = b
    return total


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    i = min(len(v) - 1, max(0, round(p * (len(v) - 1))))
    return v[i]


def level(value: float | None, target: dict[str, float] | None) -> str:
    if value is None or not target:
        return "gray"
    if value >= target["goal"]:
        return "green"
    return "yellow" if value >= target["baseline"] else "red"


def compute(engine, now: float) -> dict[str, Any]:
    cfg, db = engine.cfg, engine.db
    t0 = engine.window_start or now
    if cfg.kpi_window_min > 0:
        t0 = max(t0, now - cfg.kpi_window_min * 60)
    planned = max(0.0, now - t0)

    stations: dict[str, dict[str, Any]] = {}
    rty = 1.0
    rty_valid = False
    busiest, slowest_cycle = None, 0.0
    for s in cfg.stations:
        r = db.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(ok),0) good, COALESCE(SUM(dur_ms),0) busy_ms, "
            "COALESCE(SUM(attempt=1),0) first, COALESCE(SUM(attempt=1 AND ok=1),0) first_ok, "
            "COALESCE(SUM(degraded),0) degraded FROM steps WHERE station=? AND end_ts>=? AND end_ts<=?",
            (s.id, t0, now),
        ).fetchone()
        down = _union_seconds(
            [
                (max(d["start_ts"], t0), min(d["end_ts"] if d["end_ts"] is not None else now, now))
                for d in db.execute(
                    "SELECT start_ts, end_ts FROM downtime WHERE station=? AND start_ts<=? AND (end_ts IS NULL OR end_ts>=?)",
                    (s.id, now, t0),
                )
            ]
        )
        down = min(down, planned)
        run = planned - down
        n, good = r["n"], r["good"]
        a = run / planned if planned > 0 else None
        p = min(1.0, s.ideal_cycle_s * n / run) if run > 0 else None
        q = good / n if n else None
        oee = a * p * q if None not in (a, p, q) else None
        fpy = r["first_ok"] / r["first"] if r["first"] else None
        if fpy is not None:
            rty *= fpy
            rty_valid = True
        util = (r["busy_ms"] / 1000.0) / planned if planned > 0 else 0.0
        avg = r["busy_ms"] / 1000.0 / n if n else 0.0
        if n >= 3 and avg > slowest_cycle:   # gargalo de linha em série = estação de ciclo mais longo
            busiest, slowest_cycle = s.id, avg
        waiting = db.execute(
            "SELECT COUNT(*) c FROM units WHERE next_station=? AND busy=0 AND status IN ('wip','rework')", (s.id,)
        ).fetchone()["c"]
        stations[s.id] = {
            "cycles": n,
            "good": good,
            "nok": n - good,
            "degraded": r["degraded"],
            "avg_cycle_s": (r["busy_ms"] / 1000.0 / n) if n else None,
            "down_s": down,
            "availability": a,
            "performance": p,
            "quality": q,
            "oee": oee,
            "fpy": fpy,
            "utilization": util,
            "waiting": waiting,
        }

    u = db.execute(
        "SELECT COALESCE(SUM(status='done'),0) done, COALESCE(SUM(status='scrap'),0) scrap, "
        "COALESCE(SUM(status='done' AND fails=0),0) clean FROM units WHERE finished_ts>=? AND finished_ts<=?",
        (t0, now),
    ).fetchone()
    leads = [
        r["lt"]
        for r in db.execute(
            "SELECT finished_ts-created_ts lt FROM units WHERE status='done' AND finished_ts>=? AND finished_ts<=?",
            (t0, now),
        )
    ]
    started = db.execute("SELECT COUNT(*) c FROM units WHERE created_ts>=? AND created_ts<=?", (t0, now)).fetchone()["c"]
    wip = db.execute("SELECT COUNT(*) c FROM units WHERE status IN ('wip','rework')").fetchone()["c"]
    rework_now = db.execute("SELECT COUNT(*) c FROM units WHERE status='rework'").fetchone()["c"]
    reworked = db.execute(
        "SELECT COUNT(DISTINCT unit) c FROM steps WHERE ok=0 AND end_ts>=? AND end_ts<=?", (t0, now)
    ).fetchone()["c"]
    done, scrap = u["done"], u["scrap"]
    closed = done + scrap
    costs = cfg.costs
    cost = scrap * float(costs["scrap"]) + sum(
        v["nok"] * float(costs["nok"].get(sid, costs["nok_default"])) for sid, v in stations.items()
    )
    line = {
        "window_start": t0,
        "planned_s": planned,
        "started": started,
        "done": done,
        "scrap": scrap,
        "wip": wip,
        "in_rework": rework_now,
        "failed_units": reworked,
        "fpy": u["clean"] / closed if closed else None,
        "rty": rty if rty_valid else None,
        "oee": min(1.0, done * cfg.takt_s / planned) if planned > 0 else None,
        "copq": 1 - cost / (started * float(costs["unit"])) if started else None,
        "cost": cost,
        "throughput_h": done / (planned / 3600.0) if planned > 0 else None,
        "pace_s": planned / done if done else None,
        "lead_time_avg_s": sum(leads) / len(leads) if leads else None,
        "lead_time_p95_s": _percentile(leads, 0.95),
        "bottleneck": busiest,
    }
    return {"line": line, "stations": stations}


def insights(cfg, k: dict[str, Any], alerts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Diagnóstico por regras (sempre disponível, com ou sem IA)."""
    out: list[dict[str, str]] = []
    names = {s.id: s.name for s in cfg.stations}
    line, st = k["line"], k["stations"]
    for a in alerts:
        out.append({"level": a["level"], "text": a["message"]})
    if line["planned_s"] < 60 or not any(v["cycles"] for v in st.values()):
        return out or [{"level": "gray", "text": "Aguardando produção para diagnosticar."}]
    b = line["bottleneck"]
    if b:
        avg = st[b]["avg_cycle_s"]
        out.append(
            {
                "level": "yellow" if avg > 0.9 * cfg.takt_s else "green",
                "text": f"Gargalo: {names[b]} (ciclo médio de {avg:.1f} s, o mais longo da linha; takt de {cfg.takt_s:g} s; "
                f"ocupada {st[b]['utilization']:.0%} do tempo).",
            }
        )
    worst = min((s for s in st if st[s]["fpy"] is not None), key=lambda s: st[s]["fpy"], default=None)
    if worst and st[worst]["fpy"] < 0.97:
        out.append(
            {
                "level": "yellow",
                "text": f"Maior perda de qualidade: {names[worst]} (FPY {st[worst]['fpy']:.1%}, "
                f"{st[worst]['nok']} reprovação(ões)).",
            }
        )
    q = max(st, key=lambda s: st[s]["waiting"])
    if st[q]["waiting"] >= 4:
        out.append({"level": "yellow", "text": f"Acúmulo antes de {names[q]}: {st[q]['waiting']} unidades esperando."})
    down = max(st, key=lambda s: st[s]["down_s"])
    if st[down]["down_s"] > 0.05 * line["planned_s"]:
        out.append(
            {"level": "yellow", "text": f"{names[down]} ficou parada {st[down]['down_s']:.0f} s "
             f"({st[down]['down_s'] / line['planned_s']:.0%} do tempo)."}
        )
    if line["done"] >= 10 and line["pace_s"] > cfg.takt_s * 1.1:
        out.append(
            {"level": "red", "text": f"Ritmo real de {line['pace_s']:.1f} s por unidade, acima do takt de {cfg.takt_s:g} s."}
        )
    deg = sum(v["degraded"] for v in st.values())
    if deg:
        out.append({"level": "yellow", "text": f"{deg} ciclo(s) em modo degradado (sem liberação do servidor)."})
    return out


def vision_stats(db, t0: float, now: float) -> dict[str, Any]:
    """Desempenho do inspetor no turno. Com gabarito (simulador), mede detecção e falsa reprovação."""
    r = db.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(ok=0),0) rejected, COALESCE(SUM(ok IS NULL),0) no_verdict, "
        "COALESCE(SUM(truth=1 AND ok=0),0) tp, COALESCE(SUM(truth=1 AND ok=1),0) fn, "
        "COALESCE(SUM(truth=0 AND ok=0),0) fp, COALESCE(SUM(truth=0 AND ok=1),0) tn, "
        "COALESCE(SUM(truth=1 AND ok=0 AND defect=truth_kind),0) kind_ok "
        "FROM inspections WHERE ts>=? AND ts<=?",
        (t0, now),
    ).fetchone()
    lat = [x[0] for x in db.execute(
        "SELECT latency_ms FROM inspections WHERE ts>=? AND ts<=? AND ok IS NOT NULL ORDER BY latency_ms", (t0, now))]
    judged = r["tp"] + r["fn"] + r["fp"] + r["tn"]
    return {
        "inspected": r["n"],
        "rejected": r["rejected"],
        "no_verdict": r["no_verdict"],
        "with_truth": judged,
        "accuracy": (r["tp"] + r["tn"]) / judged if judged else None,
        "detection": r["tp"] / (r["tp"] + r["fn"]) if r["tp"] + r["fn"] else None,
        "false_fail": r["fp"] / (r["fp"] + r["tn"]) if r["fp"] + r["tn"] else None,
        "escaped": r["fn"],
        "good_rejected": r["fp"],
        "kind_right": r["kind_ok"] / r["tp"] if r["tp"] else None,
        "latency_ms_median": lat[len(lat) // 2] if lat else None,
        "last": [dict(x) for x in db.execute("SELECT * FROM inspections ORDER BY id DESC LIMIT 10")],
    }


COUNT_LABELS = {
    "blocked": "inicios_bloqueados_pelo_intertravamento",
    "nok": "reprovacoes_enviadas_a_retrabalho",
    "scrap": "unidades_refugadas",
    "offline": "quedas_de_estacao",
    "degraded": "ciclos_sem_liberacao",
    "gap": "avisos_de_eventos_perdidos",
    "reboot": "reinicios_de_placa",
    "hold": "eventos_de_retencao_jidoka",
    "call": "chamados_andon",
}


def snapshot(engine, now: float) -> dict[str, Any]:
    cfg, db = engine.cfg, engine.db
    k = compute(engine, now)
    alerts = [dict(r) for r in db.execute("SELECT * FROM alerts WHERE closed_ts IS NULL ORDER BY ts DESC")]
    log = [dict(r) for r in db.execute("SELECT * FROM log ORDER BY ts DESC, id DESC LIMIT 40")]
    stations = []
    for s in cfg.stations:
        lv = engine.live[s.id]
        cycle_ms = lv.cycle_ms + int((now - lv.cycle_at) * 1000) if lv.online and lv.state == "RUNNING" else 0
        row: dict[str, Any] = {
            "id": s.id,
            "name": s.name,
            "ideal_cycle_s": s.ideal_cycle_s,
            "reader": s.reader,
            "kind": s.kind,
            "online": lv.online,
            "seen": lv.seen,
            "hw": lv.hw,
            "fw": lv.fw,
            "state": lv.state if lv.online else "OFFLINE",
            "unit": lv.unit,
            "cycle_ms": cycle_ms,
            "call": lv.call,
            "hold": lv.hold,
            "temp": lv.temp,
            "rssi": lv.rssi,
            "queued": lv.queued,
            "dropped": lv.dropped,
            "gaps": lv.gaps,
            "reason": lv.reason,
            "light": lv.light,
            "recent": [[round(t, 1), round(d, 2), ok] for t, d, ok in lv.recent],
            "kpi": k["stations"][s.id],
        }
        chart = engine.charts.get(s.id)
        if chart:
            row["spc"] = {
                "label": s.spc.get("label", s.name),
                "unit": s.spc.get("unit", ""),
                "target": chart.target,
                "ucl": chart.ucl,
                "lcl": chart.lcl,
                "level": chart.level,
                "rule": chart.rule,
                "points": [[round(t, 1), round(v, 2)] for t, v in chart.points],
            }
        stations.append(row)
    line = k["line"]
    return {
        "ts": now,
        "line": {
            "name": cfg.name,
            "takt_s": cfg.takt_s,
            "interlock": bool(cfg.rules["interlock"]),
            "kpi": line,
            "targets": cfg.targets,
            "levels": {key: level(line[key], cfg.targets.get(key)) for key in ("fpy", "rty", "oee", "copq")},
        },
        "stations": stations,
        "alerts": alerts,
        "log": log,
        "insights": insights(cfg, k, alerts),
        "vision": vision_stats(db, line["window_start"], now),
        # Onde está cada unidade, para a vista do chão de fábrica.
        "floor": {
            "units": [
                dict(r)
                for r in db.execute(
                    "SELECT id, status, next_station, busy, fails FROM units WHERE status IN ('wip','rework') "
                    "ORDER BY busy DESC, ready_ts LIMIT 80"
                )
            ],
            "exits": {
                r["id"]: r["status"]
                for r in db.execute(
                    "SELECT id, status FROM units WHERE finished_ts IS NOT NULL ORDER BY finished_ts DESC LIMIT 20"
                )
            },
        },
        "counts": {
            COUNT_LABELS.get(r["kind"], r["kind"]): r["c"]
            for r in db.execute(
                "SELECT CASE WHEN kind LIKE 'blocked:%' THEN 'blocked' ELSE kind END kind, COUNT(*) c FROM log WHERE ts>=? AND (kind IN ('nok','scrap','offline','degraded','gap','reboot','hold') OR kind LIKE 'blocked:%') "
                "GROUP BY 1 UNION ALL SELECT 'call', COUNT(*) FROM downtime WHERE reason='call' AND start_ts>=?",
                (line["window_start"], line["window_start"]),
            )
        },
        "sim": engine.sim_status,
        "rejected": engine.rejected,
    }
