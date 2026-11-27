"""Execuções do M2 prontas para a API: eventos compactos para a reprodução + indicadores."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from . import metrics
from .model import MANUAL, SCENARIOS, simulate

SOLUTION = "lean_ampliado"   # cenário de solução usado como padrão na síntese
PROBLEM = "atual"


def scenarios() -> list[dict[str, str]]:
    return [{"id": s.id, "label": s.label, "resumo": s.resumo, "papel": s.papel} for s in SCENARIOS.values()]


@lru_cache(maxsize=24)
def run(scenario: str, hours: float = 8.0, seed: int = 7) -> dict[str, Any]:
    """Simula e devolve tudo o que o painel precisa. O resultado é determinístico, por isso fica em cache."""
    r = simulate(scenario, hours, seed)
    m = metrics.compute(r)
    sc = r.scenario
    return {
        "scenario": {"id": sc.id, "label": sc.label, "resumo": sc.resumo, "papel": sc.papel},
        "horizon": r.horizon,
        "seed": seed,
        "stations": r.stations,
        "durations": r.durations,
        "capacities": r.capacities,
        "manual": [n for n in r.stations if n in MANUAL],
        "costs": {**metrics.COSTS, "unit": metrics.UNIT_VALUE},
        "ideal_cycle_s": metrics.IDEAL_CYCLE_S,
        # eventos em colunas: instante (s), peça, índice da estação, tipo (0 fila, 1 entrada, 2 saída),
        # resultado (0 pendente, 1 aprovada, 2 reprovada)
        "events": {
            "t": [round(e[0], 1) for e in r.events],
            "p": [e[1] for e in r.events],
            "s": [e[2] for e in r.events],
            "k": [e[3] for e in r.events],
            "r": [e[4] for e in r.events],
        },
        **m,
    }


def summary(scenario: str, hours: float = 8.0, seed: int = 7) -> dict[str, Any]:
    full = run(scenario, hours, seed)
    return {"scenario": full["scenario"], "hours": hours, "seed": seed, **full["summary"]}
