"""E se?: roda um turno inteiro em segundos.

Liga a planta simulada (com o firmware real de cada estação) direto ao motor da linha, sem
broker e com relógio virtual. Os indicadores saem do mesmo cálculo usado no painel ao vivo.
"""

from __future__ import annotations

import time
from typing import Any

from .. import kpi
from ..config import Config, with_scenario
from ..engine import Engine
from ..store import open_db
from .plant import Plant

EPOCH = 1_700_000_000.0   # origem arbitrária do relógio virtual
STEP_MS = 100


def run(cfg: Config, scenario: str = "padrao", hours: float = 2.0, seed: int | None = None) -> dict[str, Any]:
    cfg = with_scenario(cfg, scenario)
    clock = {"ms": 0}
    plant_ref: list[Plant] = []

    def to_plant(topic: str, payload: str, qos: int, retain: bool) -> None:
        plant_ref[0].deliver(topic, payload)

    engine = Engine(cfg, open_db(":memory:"), to_plant)

    def to_engine(topic: str, payload: str, qos: int, retain: bool) -> bool:
        engine.handle(topic, payload, EPOCH + clock["ms"] / 1000.0)
        return True

    plant = Plant(cfg, to_engine, seed=seed, dt=STEP_MS)
    plant_ref.append(plant)
    engine.start(EPOCH)
    t0 = time.perf_counter()
    total = int(hours * 3600 * 1000)
    engine.db.execute("BEGIN")
    while clock["ms"] < total:
        clock["ms"] += STEP_MS
        plant.step(clock["ms"])
        if clock["ms"] % 1000 == 0:
            engine.tick(EPOCH + clock["ms"] / 1000.0)
    engine.db.execute("COMMIT")
    now = EPOCH + total / 1000.0
    k = kpi.compute(engine, now)
    line = k["line"]
    result = {
        "scenario": scenario,
        "label": cfg.scenarios.get(scenario, {}).get("label", scenario),
        "hours": hours,
        "seed": cfg.simulation["seed"] if seed is None else seed,
        "wall_s": round(time.perf_counter() - t0, 2),
        "line": line,
        "levels": {key: kpi.level(line[key], cfg.targets.get(key)) for key in ("fpy", "rty", "oee", "copq")},
        "stations": {
            s.id: {"name": s.name, **k["stations"][s.id]} for s in cfg.stations
        },
        "blocked": dict(plant.blocked),
        "escaped_defects": sum(1 for u in plant.finished if u.defects),
    }
    plant.close()
    return result


def compare(cfg: Config, scenarios: list[str], hours: float = 2.0, seed: int | None = None) -> list[dict[str, Any]]:
    return [run(cfg, s, hours, seed) for s in scenarios]
