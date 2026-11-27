"""O simulador executa o firmware real: paridade com o teste nativo e turno completo de ponta a ponta."""

from sfal.config import load
from sfal.paths import FIRMWARE_DIR
from sfal.sim import whatif
from sfal.sim.golden import run_script


def test_biblioteca_do_simulador_reproduz_o_traco_de_referencia():
    # O mesmo arquivo é conferido pelo teste nativo em C++ (firmware/test/test_core).
    for script in sorted((FIRMWARE_DIR / "test" / "golden").glob("*.script")):
        assert run_script(script) == script.with_suffix(".trace").read_text(), script.name


def test_turno_simulado_e_coerente_e_reprodutivel():
    cfg = load()
    a = whatif.run(cfg, "padrao", hours=0.5, seed=7)
    b = whatif.run(cfg, "padrao", hours=0.5, seed=7)
    assert a["line"] == b["line"]                                  # mesma semente, mesmo resultado
    k = a["line"]
    assert k["done"] > 60
    assert k["started"] == k["done"] + k["scrap"] + k["wip"]       # nenhuma unidade some
    assert a["escaped_defects"] <= 1
    assert all(s["degraded"] == 0 for s in a["stations"].values())  # servidor respondeu a tempo


def test_qualidade_na_fonte_melhora_os_indicadores():
    cfg = load()
    atual = whatif.run(cfg, "atual", hours=1, seed=3)["line"]
    futuro = whatif.run(cfg, "futuro", hours=1, seed=3)["line"]
    assert futuro["fpy"] > atual["fpy"]
    assert futuro["lead_time_avg_s"] < atual["lead_time_avg_s"]
    assert futuro["wip"] < atual["wip"]


def test_modo_hibrido_estacao_real_no_meio_da_linha():
    """`asm` fica fora do simulador; quem faz o papel da placa real é o próprio teste."""
    import json

    from sfal.engine import Engine
    from sfal.sim.plant import Plant, RemoteActor
    from sfal.store import open_db

    cfg = load()
    clock = {"ms": 0}
    box = []
    engine = Engine(cfg, open_db(), lambda t, p, q, r: box[0].deliver(t, p))
    now = lambda: 1e9 + clock["ms"] / 1000  # noqa: E731
    plant = Plant(cfg, lambda t, p, q, r: engine.handle(t, p, now()) or True, real=("asm",), dt=100, seed=1)
    box.append(plant)
    engine.start(now())
    assert isinstance(plant.actors["asm"], RemoteActor) and "asm" not in plant.stations
    engine.handle("sfal/v1/asm/status", '{"online":true,"fw":"t","hw":"esp32","boot":9}', now())
    seq = 0
    while clock["ms"] < 15 * 60 * 1000:
        clock["ms"] += 100
        plant.step(clock["ms"])
        if clock["ms"] % 20000 == 0 and plant.actors["asm"].queue:     # "operador" da placa real: um ciclo de 10 s
            sent = []
            engine.publish = lambda t, p, q, r: sent.append((t, json.loads(p)))
            seq += 1
            engine.handle("sfal/v1/asm/evt/scan", json.dumps({"seq": seq, "boot": 9, "age_ms": 0, "unit": ""}), now())
            engine.publish = lambda t, p, q, r: box[0].deliver(t, p)
            rel = next(p for t, p in sent if t.endswith("cmd/release"))
            assert rel["ok"], rel
            seq += 1
            msg = json.dumps({"seq": seq, "boot": 9, "age_ms": 0, "unit": rel["unit"], "dur_ms": 10000, "ok": True,
                              "degraded": False})
            engine.handle("sfal/v1/asm/evt/cycle", msg, now() + 10)
            plant.observe("sfal/v1/asm/evt/cycle", msg, clock["ms"])
    done = engine.db.execute("SELECT COUNT(*) c FROM units WHERE status='done'").fetchone()["c"]
    assert done >= 20 and len(plant.finished) == done
    plant.close()
