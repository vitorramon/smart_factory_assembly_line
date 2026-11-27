"""Inferência do classificador da AOI (models/aoi.onnx, treinado por tools/train_aoi.py).

A rede devolve um mapa com um canal por tipo de defeito de solda. A nota de cada tipo é o máximo do canal; se a
maior nota passa do limiar, a placa é reprovada, e a posição do máximo indica onde o defeito está na foto.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from .inspector import Verdict

THRESHOLD = 0.0   # logit usado se a ficha do modelo não trouxer o limiar calibrado no treino


class CnnInspector:
    def __init__(self, path: Path):
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        card = path.with_suffix(".json")
        self.card = json.loads(card.read_text(encoding="utf-8")) if card.exists() else {}
        self.classes = self.card.get("classes", ["ponte", "ausente", "excesso"])
        self.size = tuple(self.card.get("entrada", [256, 192]))
        self.name = f"{self.card.get('modelo', 'aoi-cnn')} ({self.card.get('treinado_em', 's/ data')})"
        self.threshold = float(self.card.get("limiar", THRESHOLD))

    def inspect(self, jpeg: bytes) -> Verdict:
        t0 = time.monotonic()
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB").resize(self.size, Image.BILINEAR)
        except OSError as e:
            return Verdict(None, model=self.name, error=f"imagem inválida: {e}")
        x = (np.asarray(img, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
        heat = self.session.run(None, {"foto": x})[0][0]            # (tipos, linhas, colunas)
        flat = heat.reshape(heat.shape[0], -1)
        k = int(flat.max(axis=1).argmax())
        score = float(flat[k].max())
        ms = int((time.monotonic() - t0) * 1000)
        if score <= self.threshold:
            return Verdict(True, model=self.name, latency_ms=ms, score=score)
        row, col = divmod(int(flat[k].argmax()), heat.shape[2])
        return Verdict(False, self.classes[k], "", self.name, ms, score=score,
                       x=(col + 0.5) / heat.shape[2], y=(row + 0.5) / heat.shape[1])
