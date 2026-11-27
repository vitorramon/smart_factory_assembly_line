"""Mede o inspetor contra um gabarito: N placas sintéticas, metade com defeito de solda.

O resultado (taxa de detecção e de falsa reprovação) é o que justifica usar o modelo na estação e é o número
que deve alimentar `detect_p` e `false_fail_p` da AOI em config/line.yaml para o "E se?".
"""

from __future__ import annotations

from typing import Any

from .board import DEFECT_KINDS, render
from .inspector import inspect


def run(url: str, model: str, n: int = 60, first_serial: int = 5000) -> dict[str, Any]:
    tp = fp = tn = fn = failed = 0
    latency: list[int] = []
    by_kind = {k: [0, 0] for k in DEFECT_KINDS}      # [detectados, total]
    kind_ok = 0
    for i in range(n):
        defect = i % 2 == 1
        photo = render(first_serial + i, defect, DEFECT_KINDS[(i // 2) % 3] if defect else None)
        v = inspect(url, model, photo.jpeg)
        if v.ok is None:
            failed += 1
            continue
        latency.append(v.latency_ms)
        if defect:
            by_kind[photo.defect][1] += 1
            if not v.ok:
                tp += 1
                by_kind[photo.defect][0] += 1
                kind_ok += v.defect == photo.defect
            else:
                fn += 1
        elif v.ok:
            tn += 1
        else:
            fp += 1
    done = tp + fp + tn + fn
    return {
        "model": model,
        "boards": n,
        "judged": done,
        "failed": failed,
        "accuracy": (tp + tn) / done if done else None,
        "detection": tp / (tp + fn) if tp + fn else None,          # defeituosas reprovadas
        "false_fail": fp / (fp + tn) if fp + tn else None,         # boas reprovadas
        "escaped": fn,
        "defect_named_right": kind_ok / tp if tp else None,
        "by_kind": {k: f"{d}/{t}" for k, (d, t) in by_kind.items()},
        "latency_ms_median": sorted(latency)[len(latency) // 2] if latency else None,
        "latency_ms_max": max(latency) if latency else None,
    }
