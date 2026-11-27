"""Controle estatístico de processo sobre um sinal contínuo (carta de valores individuais).

Regras (subconjunto das Western Electric / Nelson):
  R1  um ponto além de ±3σ ........................... vermelho
  R2  8 pontos seguidos do mesmo lado da linha central  amarelo (deslocamento da média)
  R3  6 pontos seguidos subindo ou descendo ........... amarelo (tendência)
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field

CLEAR_AFTER = 10  # pontos seguidos sem violação para encerrar o alarme


@dataclass
class Chart:
    target: float
    sigma: float
    points: deque = field(default_factory=lambda: deque(maxlen=180))  # (ts, valor)
    level: str = ""  # "", "yellow" ou "red"
    rule: str = ""
    _clean: int = 0

    def add(self, ts: float, value: float) -> tuple[str, str]:
        """Acrescenta um ponto e devolve (nível, regra) vigentes."""
        self.points.append((ts, value))
        level, rule = self._evaluate()
        if level:
            self._clean = 0
            if level == "red" or self.level != "red":
                self.level, self.rule = level, rule
        else:
            self._clean += 1
            if self._clean >= CLEAR_AFTER:
                self.level, self.rule = "", ""
        return self.level, self.rule

    def _evaluate(self) -> tuple[str, str]:
        vals = [v for _, v in self.points]
        last = vals[-1]
        if abs(last - self.target) > 3 * self.sigma:
            return "red", "ponto além de 3σ"
        if len(vals) >= 8:
            tail = vals[-8:]
            if all(v > self.target for v in tail) or all(v < self.target for v in tail):
                return "yellow", "8 pontos do mesmo lado da média"
        if len(vals) >= 6:
            t = vals[-6:]
            ups = all(b > a for a, b in itertools.pairwise(t))
            downs = all(b < a for a, b in itertools.pairwise(t))
            if ups or downs:
                return "yellow", "tendência de 6 pontos"
        return "", ""

    @property
    def ucl(self) -> float:
        return self.target + 3 * self.sigma

    @property
    def lcl(self) -> float:
        return self.target - 3 * self.sigma
