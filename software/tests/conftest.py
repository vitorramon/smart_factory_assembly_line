import json

import pytest

from sfal.config import load
from sfal.engine import Engine
from sfal.store import open_db

T0 = 1_000_000.0


class Bench:
    """Motor em memória com as mensagens que ele publica guardadas em `sent`."""

    def __init__(self, patch=None):
        from sfal.config import deep_merge, from_dict

        cfg = load()
        if patch:
            cfg = from_dict(deep_merge(cfg.raw, patch))
        self.cfg = cfg
        self.sent: list[tuple[str, dict]] = []
        self.engine = Engine(cfg, open_db(), lambda t, p, q, r: self.sent.append((t, json.loads(p))))
        self.engine.start(T0)
        self.seq = {s.id: 0 for s in cfg.stations}
        for s in cfg.stations:
            self.msg(s.id, "status", {"online": True, "fw": "t", "hw": "test", "boot": 1}, T0)

    def msg(self, station, suffix, data, now):
        self.engine.handle(f"sfal/v1/{station}/{suffix}", json.dumps(data), now)

    def evt(self, station, kind, now, **data):
        self.seq[station] += 1
        self.msg(station, f"evt/{kind}", {"seq": self.seq[station], "boot": 1, "age_ms": 0, **data}, now)

    def release(self, station):
        return next(p for t, p in reversed(self.sent) if t == f"sfal/v1/{station}/cmd/release")

    def cycle(self, station, unit, now, dur_s=10.0, ok=True):
        """Leitura + ciclo completo. Devolve a resposta de liberação."""
        self.evt(station, "scan", now, unit=unit)
        rel = self.release(station)
        if rel["ok"]:
            self.evt(station, "cycle", now + dur_s, unit=rel["unit"], dur_ms=int(dur_s * 1000), ok=ok, degraded=False)
        return rel

    def through(self, unit, now, upto=None, fail_at=None):
        """Passa a unidade pela rota até `upto` (inclusive); `fail_at` reprova nessa estação."""
        for s in self.cfg.stations:
            rel = self.cycle(s.id, unit, now, ok=s.id != fail_at)
            unit = rel["unit"]
            now += 12
            if s.id in (upto, fail_at):
                break
        return unit, now


@pytest.fixture
def bench():
    return Bench()
