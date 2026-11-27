"""Indicadores do M2, calculados dos eventos em ordem temporal (mesmas definições do metrics.js da entrega).

  FPY        aprovadas no teste funcional ÷ testadas
  RTY        produto das frações aprovadas no SPI, AOI e teste funcional ativos
  OEE        aprovadas na embalagem × ciclo ideal comum (20 s) ÷ tempo transcorrido; disponibilidade assumida 100 %
  1 − COPQ   1 − custo estimado das ocorrências ÷ (placas iniciadas × valor de referência)
  WIP        iniciadas − concluídas − retidas/reprovadas; "filas" conta só as que aguardam
"""

from __future__ import annotations

from typing import Any

from .model import FILA, REPROVADA, SAIDA, Run

INSPECTIONS = ("SPI", "AOI", "Teste funcional")
# Hipóteses de custo por ocorrência (R$), as mesmas do painel do M2.
COSTS = {"SPI": 15.0, "AOI": 60.0, "Teste funcional": 240.0}
UNIT_VALUE = 240.0
IDEAL_CYCLE_S = 20.0
SAMPLES = 240


def compute(run: Run) -> dict[str, Any]:
    names = run.stations
    insp = [i for i, n in enumerate(names) if n in INSPECTIONS]
    pack, test = names.index("Embalagem"), names.index("Teste funcional")
    total = {i: 0 for i in insp}
    passed = {i: 0 for i in insp}
    rejected = {i: 0 for i in insp}
    latest: dict[int, int] = {}
    starts: dict[int, float] = {}
    by_defect: dict[str, int] = {}
    good = bad = queue = queue_max = 0
    cost = lead = queue_area = previous = 0.0
    step = run.horizon / SAMPLES
    next_sample = step
    series: list[dict[str, Any]] = []

    def point(t: float) -> dict[str, Any]:
        ready = bool(insp) and all(total[i] for i in insp)
        rty = 1.0
        for i in insp:
            if total[i]:
                rty *= passed[i] / total[i]
        started = len(starts)
        return {
            "t": t,
            "started": started,
            "done": good,
            "rejected": bad,
            "wip": started - good - bad,
            "queue": queue,
            "cost": cost,
            "fpy": passed[test] / total[test] if total[test] else None,
            "rty": rty if ready else None,
            "oee": good * IDEAL_CYCLE_S / t if t > 0 else None,
            "copq": 1 - cost / (started * UNIT_VALUE) if started else None,
            "lead_time_s": lead / good if good else None,
            "rejects": {names[i]: rejected[i] for i in insp},
        }

    for n, (t, piece, s, kind, result) in enumerate(run.events):
        while t > next_sample and len(series) < SAMPLES - 1:
            series.append(point(next_sample))
            next_sample += step
        queue_area += queue * (t - previous)
        previous = t
        if latest.get(piece) == FILA:
            queue -= 1
        if kind == FILA:
            queue += 1
        latest[piece] = kind
        starts.setdefault(piece, t)
        if kind == SAIDA:
            if s in total:
                total[s] += 1
                if result == REPROVADA:
                    rejected[s] += 1
                else:
                    passed[s] += 1
            if result == REPROVADA:
                bad += 1
                cost += COSTS.get(names[s], 0.0)
                for d in run.reasons.get(n, "").split(", "):
                    if d:
                        by_defect[d] = by_defect.get(d, 0) + 1
            if s == pack:
                good += 1
                lead += t - starts[piece]
        queue_max = max(queue_max, queue)
    while len(series) < SAMPLES - 1:
        series.append(point(next_sample))
        next_sample += step
    final = point(run.horizon)
    series.append(final)
    queue_area += queue * (run.horizon - previous)
    summary = {
        **final,
        "queue_mean": queue_area / run.horizon,
        "queue_max": queue_max,
        "throughput_h": good * 3600 / run.horizon,
        "tested": total[test],
        "test_rejected": rejected[test],
        "defects_found": by_defect,       # tipos de defeito presentes nas placas retidas ou reprovadas
    }
    return {"series": series, "summary": summary}
