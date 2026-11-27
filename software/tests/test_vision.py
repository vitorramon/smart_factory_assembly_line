"""Inspeção óptica por IA: foto → veredito → resultado na estação (firmware real) → genealogia."""

import json

import pytest

from sfal import kpi
from sfal.config import load
from sfal.engine import Engine
from sfal.paths import ROOT
from sfal.sim.plant import Plant
from sfal.store import open_db
from sfal.vision.board import DEFECT_KINDS, render

from .conftest import T0

MODEL = ROOT / "models" / "aoi.onnx"


class Done:
    """Veredito já pronto, com a interface de um Future."""

    def __init__(self, value):
        self.value = value

    def done(self):
        return True

    def result(self):
        return self.value


def line_with_camera(decide, minutes=20):
    cfg = load()
    clock = {"ms": 0}
    box = []
    engine = Engine(cfg, open_db(), lambda t, p, q, r: box[0].deliver(t, p))
    now = lambda: 1e9 + clock["ms"] / 1000  # noqa: E731
    plant = Plant(cfg, lambda t, p, q, r: engine.handle(t, p, now()) or True, dt=100, seed=5)
    box.append(plant)

    def camera(station, unit, jpeg, truth):
        assert jpeg[:2] == b"\xff\xd8"                      # é um JPEG
        verdict = decide(truth)
        if verdict["ok"] is not None or True:
            engine.record_inspection(station, unit, verdict, truth, "foto.jpg", now())
        return Done(verdict)

    plant.camera = camera
    engine.start(now())
    while clock["ms"] < minutes * 60 * 1000:
        clock["ms"] += 100
        plant.step(clock["ms"])
    return engine, plant, now()


def test_foto_sintetica_e_reprodutivel_e_mostra_o_defeito():
    a, b = render(77, True, "ponte"), render(77, True, "ponte")
    assert a.jpeg == b.jpeg and a.defect == "ponte" and "ponte" in a.where
    assert render(77, False).defect is None
    assert render(77, False).jpeg != a.jpeg


def test_estacao_aoi_decide_pelo_veredito_do_modelo():
    engine, plant, now = line_with_camera(lambda truth: {"ok": not truth["defect"], "defect": truth["kind"] or "", "model": "gabarito"})
    rows = [dict(r) for r in engine.db.execute("SELECT * FROM inspections")]
    assert len(rows) > 30 and plant.vision_fallbacks == 0
    bad = [r for r in rows if r["ok"] == 0]
    assert bad and all(r["truth"] == 1 for r in bad)
    # cada veredito virou um ciclo da AOI com o mesmo resultado, encerrado pelo firmware
    steps = engine.db.execute("SELECT COUNT(*) n, SUM(ok=0) nok FROM steps WHERE station='aoi' AND end_ts IS NOT NULL").fetchone()
    assert steps["nok"] == len(bad) and abs(steps["n"] - len(rows)) <= 1
    v = kpi.vision_stats(engine.db, 0, now)
    assert v["detection"] == 1.0 and v["false_fail"] == 0.0 and v["escaped"] == 0
    assert not any(u.defects & {"solda"} for u in plant.finished)   # nenhuma solda defeituosa saiu da linha


def test_sem_veredito_a_linha_nao_para():
    engine, plant, _ = line_with_camera(lambda truth: {"ok": None, "error": "modelo fora do ar"}, minutes=10)
    assert plant.vision_fallbacks > 10
    assert engine.db.execute("SELECT COUNT(*) FROM steps WHERE station='aoi' AND end_ts IS NOT NULL").fetchone()[0] > 10
    assert engine.db.execute("SELECT COUNT(*) FROM inspections WHERE ok IS NULL").fetchone()[0] == plant.vision_fallbacks


def test_registro_publica_o_resultado_para_a_estacao(bench):
    uid, t = bench.through("", T0, upto="smt")
    bench.evt("aoi", "scan", t, unit=uid)
    bench.engine.record_inspection("aoi", uid, {"ok": False, "defect": "ponte", "x": 0.4, "y": 0.3}, {"defect": True, "kind": "ponte"}, "f.jpg", t + 2)
    assert bench.sent[-1] == ("sfal/v1/aoi/cmd/result", {"unit": uid, "ok": False})
    insp = bench.engine.unit(uid)["inspections"]
    assert insp[0]["defect"] == "ponte" and insp[0]["truth"] == 1
    assert json.dumps(bench.engine.snapshot(t + 3)["vision"]["last"][0]["x"]) == "0.4"


@pytest.mark.skipif(not MODEL.exists(), reason="modelo não treinado (tools/train_aoi.py)")
def test_classificador_treinado_detecta_os_tres_defeitos():
    from sfal.vision.cnn import CnnInspector

    cnn = CnnInspector(MODEL)
    hits = clean_ok = 0
    for i in range(60):                                   # séries fora do treino e do teste do treino
        kind = DEFECT_KINDS[i % 3]
        v = cnn.inspect(render(400_000 + i, True, kind).jpeg)
        hits += v.ok is False
        if v.ok is False:
            assert v.x is not None and 0 <= v.x <= 1
        clean_ok += cnn.inspect(render(500_000 + i, False).jpeg).ok is True
    assert hits >= 57 and clean_ok >= 57
