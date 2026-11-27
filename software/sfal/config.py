"""Leitura e validação de config/line.yaml."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import CONFIG_PATH


@dataclass
class Station:
    id: str
    index: int
    name: str
    ideal_cycle_s: float
    reader: bool = True
    kind: str = "auto"  # auto | manual (só para o desenho do chão de fábrica)
    skill: str = ""     # capacidade que a estação oferece (o que o produto pede em cada etapa)
    on_fail: str = "rework"  # rework | scrap
    spc: dict[str, Any] | None = None
    sim: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    raw: dict[str, Any]
    name: str
    takt_s: float
    kpi_window_min: float
    rules: dict[str, Any]
    targets: dict[str, dict[str, float]]
    stations: list[Station]
    assistant: dict[str, Any]
    simulation: dict[str, Any]
    scenarios: dict[str, dict[str, Any]]
    costs: dict[str, Any] = field(default_factory=dict)
    vision: dict[str, Any] = field(default_factory=dict)
    product: dict[str, Any] = field(default_factory=dict)
    orders: dict[str, Any] = field(default_factory=dict)

    def station(self, station_id: str) -> Station | None:
        return self._by_id.get(station_id)

    def __post_init__(self):
        self._by_id = {s.id: s for s in self.stations}


RULE_DEFAULTS = {
    "interlock": True,
    "fail_open": True,
    "release_timeout_ms": 1500,
    "max_attempts": 3,
    "jidoka": True,
    "offline_after_s": 10,
    "tel_ms": 2000,
}


def deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def from_dict(raw: dict[str, Any]) -> Config:
    line = raw.get("line") or {}
    stations_raw = raw.get("stations") or {}
    if not stations_raw:
        raise ValueError("config: nenhuma estação em `stations`")
    stations = []
    for i, (sid, s) in enumerate(stations_raw.items()):
        if not str(sid).replace("-", "").replace("_", "").isalnum() or len(str(sid)) > 20:
            raise ValueError(f"config: id de estação inválido: {sid!r} (use letras, números, - e _)")
        on_fail = s.get("on_fail", "rework")
        if on_fail not in ("rework", "scrap"):
            raise ValueError(f"config: {sid}.on_fail deve ser rework ou scrap")
        stations.append(
            Station(
                id=str(sid),
                index=i,
                name=s.get("name", str(sid)),
                ideal_cycle_s=float(s["ideal_cycle_s"]),
                reader=bool(s.get("reader", True)),
                kind=str(s.get("kind", "auto")),
                skill=str(s.get("skill", s.get("name", sid))),
                on_fail=on_fail,
                spc=s.get("spc"),
                sim=s.get("sim") or {},
            )
        )
    assistant = dict(raw.get("assistant") or {})
    assistant["url"] = os.environ.get("SFAL_OLLAMA_URL", assistant.get("url", "http://localhost:11434"))
    assistant["model"] = os.environ.get("SFAL_OLLAMA_MODEL", assistant.get("model", "qwen2.5:7b"))
    return Config(
        raw=raw,
        name=line.get("name", "Linha"),
        takt_s=float(line.get("takt_s", 20)),
        kpi_window_min=float(line.get("kpi_window_min", 0)),
        rules={**RULE_DEFAULTS, **(raw.get("rules") or {})},
        targets=raw.get("targets") or {},
        stations=stations,
        assistant=assistant,
        simulation={"seed": 42, "arrival_s": 20, "transfer_s": 2, **(raw.get("simulation") or {})},
        scenarios=raw.get("scenarios") or {"padrao": {"label": "Configuração atual", "patch": {}}},
        vision=raw.get("vision") or {},
        product={"id": "PRODUTO", "name": "Produto", **(raw.get("product") or {})},
        orders={"auto": False, "lot_size": 20, **(raw.get("orders") or {})},
        costs={"unit": 240, "scrap": 240, "nok_default": 60, "nok": {}, **(raw.get("costs") or {})},
    )


def load(path: Path | None = None) -> Config:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return from_dict(yaml.safe_load(f))


def with_scenario(cfg: Config, scenario: str) -> Config:
    if scenario not in cfg.scenarios:
        raise KeyError(f"cenário desconhecido: {scenario} (existem: {', '.join(cfg.scenarios)})")
    return from_dict(deep_merge(cfg.raw, cfg.scenarios[scenario].get("patch") or {}))
