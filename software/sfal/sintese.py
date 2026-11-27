"""Síntese: os indicadores do problema (M1) ao estado atual (M3), passando pela simulação (M2).

Cada número leva a origem: M1 é diagnóstico e projeção do grupo; M2 é simulação SimPy da linha completa;
M3 é o que a linha conectada mede agora (com as estações simuladas, isso também é simulação — e é dito).
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

import yaml

from . import kpi
from .m2 import service as m2
from .paths import CONFIG_PATH

M1_PATH = CONFIG_PATH.parent / "m1.yaml"

ESCOPO = [
    {"modulo": "M1", "o_que": "Diagnóstico e projeção", "linha": "Linha inteira: SMT + 12 operadoras",
     "origem": "Estimativas do grupo para o cenário (não há dados de fábrica)"},
    {"modulo": "M2", "o_que": "Simulação SimPy", "linha": "22 estações: 10 de SMT + 12 manuais",
     "origem": "Simulação, turno de 8 h, semente 7; tempos fixos, só os defeitos são sorteados"},
    {"modulo": "M3", "o_que": "Linha conectada", "linha": "Recorte de 5 estações: SMT, AOI, montagem, teste, embalagem",
     "origem": "Eventos das estações (firmware real; hoje o mundo em volta é simulado)"},
]


class _Missing(dict):
    def __missing__(self, key: str) -> str:
        return "—"


def load_m1(path: Path | None = None) -> dict[str, Any]:
    with open(path or M1_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def evidence(engine, k: dict[str, Any], now: float) -> dict[str, Any]:
    """Números ao vivo citados nos textos do Ishikawa (config/m1.yaml, blocos m3)."""
    cfg, db = engine.cfg, engine.db
    t0 = k["line"]["window_start"]
    st = k["stations"]
    names = {s.id: s.name for s in cfg.stations}
    ev: dict[str, Any] = {f"nok_{sid}": v["nok"] for sid, v in st.items()}
    ev["cycles"] = sum(v["cycles"] for v in st.values())
    ev["wip"] = k["line"]["wip"]
    worst = max(st, key=lambda s: st[s]["waiting"])
    ev["max_waiting"] = f"{st[worst]['waiting']} antes de {names[worst]}" if st[worst]["waiting"] else "nenhuma"
    count = lambda q, *a: db.execute(q, a).fetchone()[0]  # noqa: E731
    ev["holds"] = count("SELECT COUNT(*) FROM downtime WHERE reason='hold' AND start_ts>=?", t0)
    ev["calls"] = count("SELECT COUNT(*) FROM downtime WHERE reason='call' AND start_ts>=?", t0)
    ev["blocked_route"] = count(
        "SELECT COUNT(*) FROM log WHERE ts>=? AND kind IN "
        "('blocked:upstream_fail','blocked:skipped_step','blocked:already_done','blocked:scrapped','blocked:unknown_unit')",
        t0,
    )
    manual = [s.id for s in cfg.stations if s.kind == "manual"]
    durs = [
        r[0]
        for r in db.execute(
            f"SELECT dur_ms FROM steps WHERE end_ts>=? AND station IN ({','.join('?' * len(manual))})", (t0, *manual)
        )
    ] if manual else []
    ev["cv_manual"] = f"CV de {statistics.pstdev(durs) / statistics.fmean(durs):.0%}" if len(durs) >= 5 else "sem dados ainda"
    v = kpi.vision_stats(db, t0, now)
    ev["vision_inspected"] = v["inspected"]
    ev["vision_detection"] = "sem gabarito ainda" if v["detection"] is None else f"{v['detection']:.0%}"
    live = engine.live
    online = [s.id for s in cfg.stations if live[s.id].online]
    real = sum(1 for sid in online if live[sid].hw == "esp32")
    ev["stations_online"], ev["stations_total"] = len(online), len(cfg.stations)
    ev["real"], ev["simulated"] = real, len(online) - real
    ev["hw_mix"] = (
        "nenhuma online" if not online
        else "todas simuladas" if real == 0
        else "todas com placa ESP32" if real == len(online)
        else f"{real} com placa ESP32, {len(online) - real} simulada(s)"
    )
    return ev


def build(engine, now: float) -> dict[str, Any]:
    cfg = engine.cfg
    m1 = load_m1()
    with engine.lock:
        k = kpi.compute(engine, now)
        ev = evidence(engine, k, now)
    line = k["line"]
    names = {s.id: s.name for s in cfg.stations}
    runs = {s["id"]: m2.summary(s["id"]) for s in m2.scenarios()}
    prob, sol = runs[m2.PROBLEM], runs[m2.SOLUTION]

    geracoes = []
    for ind in m1["indicadores"]:
        key = ind["id"]
        m3 = line.get(key)
        geracoes.append(
            {
                "id": key,
                "nome": ind["nome"],
                "descricao": ind["descricao"],
                "m1_atual": ind["atual"],
                "meta": ind["meta"],
                "m2_atual": prob[key],
                "m2_solucao": sol[key],
                "m2": {sid: r[key] for sid, r in runs.items()},
                "m3": m3,
                "nivel": kpi.level(m3, {"baseline": ind["atual"], "goal": ind["meta"]}),
            }
        )

    causas = []
    for c in m1["ishikawa"]["causas"]:
        m3 = c.get("m3") or {}
        causas.append({**c, "m3": {"status": m3.get("status", "pendente"),
                                   "texto": str(m3.get("texto", "")).format_map(_Missing(ev))}})

    origem = (
        "sem estação online" if not ev["stations_online"]
        else "simulação ao vivo: firmware real em cada estação, mundo em volta simulado" if ev["real"] == 0
        else f"medido em {ev['real']} estação(ões) com placa ESP32" + (f"; {ev['simulated']} simulada(s)" if ev["simulated"] else "")
    )
    return {
        "ts": now,
        "escopo": ESCOPO,
        "smart": m1["smart"],
        "geracoes": geracoes,
        "m2": {"problema": prob, "solucao": sol, "cenarios": runs},
        "m3": {
            "origem": origem,
            "medido": ev["real"] > 0,
            "window_start": line["window_start"],
            "planned_s": line["planned_s"],
            "line": line,
            "evidence": ev,
        },
        "fluxo": [
            {"id": "lead", "nome": "Lead time médio", "unidade": "min", "m1": None,
             "m2_atual": prob["lead_time_s"] / 60 if prob["lead_time_s"] else None,
             "m2_solucao": sol["lead_time_s"] / 60 if sol["lead_time_s"] else None,
             "m3": line["lead_time_avg_s"] / 60 if line["lead_time_avg_s"] else None},
            {"id": "wip", "nome": "WIP", "unidade": "unidades", "m1": None,
             "m2_atual": prob["wip"], "m2_solucao": sol["wip"], "m3": line["wip"]},
            {"id": "vazao", "nome": "Vazão", "unidade": "un/h", "m1": None,
             "m2_atual": prob["throughput_h"], "m2_solucao": sol["throughput_h"], "m3": line["throughput_h"]},
        ],
        "pareto": {
            "m1": {"titulo": "M1 · falhas por categoria", "nota": f"lote de {m1['pareto']['lote']:,} unidades (diagnóstico)".replace(",", "."),
                   "itens": [{"nome": i["categoria"], "qtd": i["qtd"]} for i in m1["pareto"]["itens"]]},
            "m2_atual": {"titulo": "M2 · problema: onde a falha é detectada", "nota": "simulação, cenário Atual, 8 h",
                         "itens": [{"nome": n, "qtd": q} for n, q in prob["rejects"].items()]},
            "m2_solucao": {"titulo": "M2 · solução: onde a falha é detectada", "nota": f"simulação, {sol['scenario']['label']}, 8 h",
                           "itens": [{"nome": n, "qtd": q} for n, q in sol["rejects"].items()]},
            "m3": {"titulo": "M3 · agora: onde a falha é detectada", "nota": origem,
                   "itens": [{"nome": names[sid], "qtd": v["nok"]} for sid, v in k["stations"].items()]},
        },
        "ishikawa": {"efeito": m1["ishikawa"]["efeito"], "causas": causas},
    }
