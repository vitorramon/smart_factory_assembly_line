"""Escolhe e chama o inspetor configurado em `vision` (config/line.yaml).

  engine: cnn      classificador treinado (models/aoi.onnx) — padrão
  engine: ollama   modelo de visão genérico no Ollama; medido em 2026-11-26 com 40 placas: qwen2.5vl:7b detectou
                   35 % dos defeitos e gemma3:4b reprovou todas as placas. Fica como alternativa para experimentar.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..paths import ROOT
from . import inspector
from .inspector import Verdict

DEFECT_LABEL = {"ponte": "ponte de solda", "ausente": "solda ausente", "excesso": "excesso de solda"}


class VisionService:
    def __init__(self, cfg: dict[str, Any], ollama_url: str):
        self.cfg = cfg
        self.station = cfg.get("station")
        self.engine = cfg.get("engine", "cnn")
        self.ollama_url = ollama_url
        self.cnn = None
        self.error = ""
        if self.engine == "cnn":
            path = ROOT / cfg.get("model_path", "models/aoi.onnx")
            try:
                from .cnn import CnnInspector

                self.cnn = CnnInspector(path)
            except Exception as e:  # modelo ausente ou corrompido: a estação segue sem inspeção automática
                self.error = f"classificador indisponível ({path.name}): {e}"

    @property
    def enabled(self) -> bool:
        return bool(self.station) and (self.cnn is not None or self.engine == "ollama")

    def info(self) -> dict[str, Any]:
        card = self.cnn.card if self.cnn else {}
        return {
            "station": self.station,
            "engine": self.engine,
            "enabled": self.enabled,
            "model": self.cnn.name if self.cnn else self.cfg.get("ollama_model", "") if self.engine == "ollama" else "",
            "error": self.error,
            "card": card,
        }

    async def inspect(self, jpeg: bytes) -> Verdict:
        if self.cnn is not None:
            return await asyncio.to_thread(self.cnn.inspect, jpeg)
        if self.engine == "ollama":
            return await inspector.inspect_async(
                self.ollama_url, self.cfg.get("ollama_model", "qwen2.5vl:7b"), jpeg, float(self.cfg.get("timeout_s", 15))
            )
        return Verdict(None, error=self.error or "inspeção automática desligada")
