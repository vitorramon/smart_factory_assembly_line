#!/usr/bin/env python3
"""Treina o classificador da inspeção óptica (AOI) e exporta para ONNX.

    uv run --no-project --python 3.12 --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --with torch --with onnx --with pillow --with numpy python tools/train_aoi.py

Rede convolucional pequena e totalmente convolucional: a saída é um mapa (12 × 16) com três canais, um por tipo de
defeito de solda (ponte, ausente, excesso). O treino ensina a rede a acender a célula onde o defeito está (o gerador
de fotos sabe a posição). A nota da placa é o MÁXIMO do mapa; acima do limiar, reprova, e a posição do máximo diz onde.

Treino e teste usam fotos sintéticas (software/sfal/vision/board.py) com números de série disjuntos. PyTorch só é
necessário aqui; em produção a inferência usa onnxruntime (software/sfal/vision/cnn.py).
"""

import io
import json
import sys
import time
from datetime import date
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))
from sfal.vision.board import DEFECT_KINDS, render  # noqa: E402

IN_W, IN_H = 256, 192
MAP_W, MAP_H = 16, 12
N_TRAIN, N_TEST, EPOCHS = 5000, 1000, 8
TRAIN_FIRST, TEST_FIRST = 100_000, 900_000       # séries disjuntas das usadas pelo simulador (1, 2, 3…)


def to_array(jpeg: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(jpeg)).convert("RGB").resize((IN_W, IN_H), Image.BILINEAR)
    return np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)      # uint8 para caber na memória; vira float por lote


def sample(serial: int):
    """Foto + mapa-alvo: 1 na célula do defeito (no canal do seu tipo), −1 nas vizinhas (ignoradas na perda)."""
    defect = serial % 2 == 1
    photo = render(serial, defect, DEFECT_KINDS[(serial // 2) % 3] if defect else None)
    target = np.zeros((3, MAP_H, MAP_W), dtype=np.int8)
    if photo.defect:
        k = DEFECT_KINDS.index(photo.defect)
        col, row = min(MAP_W - 1, int(photo.x * MAP_W)), min(MAP_H - 1, int(photo.y * MAP_H))
        target[k, max(0, row - 1) : row + 2, max(0, col - 1) : col + 2] = -1
        target[k, row, col] = 1
    return to_array(photo.jpeg), target


def dataset(first: int, n: int):
    with Pool(8) as pool:
        rows = pool.map(sample, range(first, first + n), chunksize=64)
    return torch.from_numpy(np.stack([r[0] for r in rows])), torch.from_numpy(np.stack([r[1] for r in rows]))


def batch(x: torch.Tensor) -> torch.Tensor:
    return x.float() / 255.0


def block(i: int, o: int) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))


class AoiNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.BatchNorm2d(16), nn.ReLU(),     # 128 × 96
            block(16, 32), block(32, 64), block(64, 64),                                  # 16 × 12
            nn.Conv2d(64, 64, 3, padding=1), nn.ReLU(),
        )
        self.head = nn.Conv2d(64, 3, 1)

    def forward(self, x):                 # devolve o mapa de defeitos (N, 3, 12, 16), em logits
        return self.head(self.features(x))


def board_scores(net, x) -> torch.Tensor:
    with torch.no_grad():
        return torch.cat([net(batch(x[i : i + 200])).amax(dim=(2, 3)) for i in range(0, len(x), 200)])


def main() -> None:
    torch.manual_seed(0)
    torch.set_num_threads(10)
    t0 = time.time()
    print("gerando fotos…", flush=True)
    xtr, ytr = dataset(TRAIN_FIRST, N_TRAIN)
    xte, yte = dataset(TEST_FIRST, N_TEST)
    print(f"  {N_TRAIN} de treino + {N_TEST} de teste em {time.time() - t0:.0f} s", flush=True)

    net = AoiNet()
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=EPOCHS * (N_TRAIN // 64 + 1))
    pos_weight = torch.tensor(40.0)       # uma célula com defeito para dezenas sem
    yte_bad = (yte == 1).flatten(1).any(dim=1)
    for epoch in range(EPOCHS):
        net.train()
        perm = torch.randperm(N_TRAIN)
        total = 0.0
        for i in range(0, N_TRAIN, 64):
            idx = perm[i : i + 64]
            y = ytr[idx]
            mask = (y >= 0).float()
            opt.zero_grad()
            loss = nn.functional.binary_cross_entropy_with_logits(
                net(batch(xtr[idx])), (y == 1).float(), weight=mask, pos_weight=pos_weight, reduction="sum") / mask.sum()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(idx)
        net.eval()
        bad = (board_scores(net, xte) > 0).any(dim=1)
        print(f"  época {epoch + 1}/{EPOCHS}  perda {total / N_TRAIN:.4f}  acerto no teste {(bad == yte_bad).float().mean():.3f}  ({time.time() - t0:.0f} s)", flush=True)

    # Limiar: escolhido numa metade do teste, medido na outra metade.
    net.eval()
    scores = board_scores(net, xte)
    half = N_TEST // 2
    top = scores.amax(dim=1)
    candidates = torch.linspace(float(top.min()), float(top.max()), 200)
    errors = torch.stack([((top[:half] > c) != yte_bad[:half]).sum() for c in candidates])
    best = candidates[errors == errors.min()]
    threshold = float(best[len(best) // 2])
    scores, true_bad = scores[half:], yte_bad[half:]
    kinds = (yte[half:] == 1).flatten(2).any(dim=2).float().argmax(dim=1)
    pred_bad = scores.amax(dim=1) > threshold
    n = len(scores)
    tp = int((pred_bad & true_bad).sum()); fn = int((~pred_bad & true_bad).sum())
    fp = int((pred_bad & ~true_bad).sum()); tn = int((~pred_bad & ~true_bad).sum())
    hit = pred_bad & true_bad
    kind_ok = int((scores.argmax(dim=1)[hit] == kinds[hit]).sum())
    by_kind = {}
    for k, name in enumerate(DEFECT_KINDS):
        sel = true_bad & (kinds == k)
        by_kind[name] = f"{int((pred_bad & sel).sum())}/{int(sel.sum())}"
    card = {
        "modelo": "aoi-cnn",
        "treinado_em": date.today().isoformat(),
        "dados": "fotos sintéticas de placa (software/sfal/vision/board.py); séries de treino e de teste disjuntas",
        "treino": N_TRAIN, "teste": n, "entrada": [IN_W, IN_H], "classes": list(DEFECT_KINDS), "limiar": threshold,
        "acuracia": (tp + tn) / n, "deteccao": tp / (tp + fn), "falsa_reprovacao": fp / (fp + tn),
        "defeitos_que_escaparam": fn, "boas_reprovadas": fp, "tipo_certo": kind_ok / tp if tp else None,
        "por_tipo": by_kind,
    }
    print(json.dumps(card, ensure_ascii=False, indent=2))
    if card["deteccao"] < 0.9 or card["falsa_reprovacao"] > 0.1:
        sys.exit("modelo ruim demais para a estação: nada foi gravado")

    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    torch.onnx.export(net, torch.zeros(1, 3, IN_H, IN_W), str(out / "aoi.onnx"), input_names=["foto"],
                      output_names=["mapa"], dynamic_axes={"foto": {0: "n"}, "mapa": {0: "n"}}, opset_version=17, dynamo=False)
    (out / "aoi.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n")
    print(f"gravado: models/aoi.onnx ({(out / 'aoi.onnx').stat().st_size // 1024} KiB) e models/aoi.json")


if __name__ == "__main__":
    main()
