"""Motor da linha: liberação, genealogia, deduplicação e indicadores com resultado conhecido."""

import pytest

from sfal import kpi

from .conftest import T0, Bench


def test_primeira_estacao_cria_a_unidade_e_publica_config_retida(bench):
    cfgs = [p for t, p in bench.sent if t == "sfal/v1/smt/cmd/config"]
    assert cfgs and cfgs[0]["takt_ms"] == 20000 and cfgs[0]["interlock"] is True
    rel = bench.cycle("smt", "", T0 + 1)
    assert rel == {"req": 1, "ok": True, "unit": "U-000001"}
    u = bench.engine.unit("U-000001")
    assert u["unit"]["status"] == "wip" and u["unit"]["next_station"] == "aoi"
    assert u["steps"][0]["dur_ms"] == 10000 and u["steps"][0]["ok"] == 1


def test_unidade_completa_a_rota_e_lead_time(bench):
    uid, end = bench.through("", T0 + 1)
    u = bench.engine.unit(uid)["unit"]
    assert u["status"] == "done"
    assert u["finished_ts"] - u["created_ts"] == pytest.approx(4 * 12 + 10)
    k = kpi.compute(bench.engine, end)["line"]
    assert (k["done"], k["wip"], k["fpy"], k["rty"]) == (1, 0, 1.0, 1.0)


@pytest.mark.parametrize(
    ("setup", "station", "reason"),
    [
        (lambda b: b.through("", T0, upto="smt")[0], "asm", "skipped_step"),
        (lambda b: b.through("", T0, fail_at="aoi")[0], "asm", "upstream_fail"),
        (lambda b: b.through("", T0, upto="asm")[0], "aoi", "already_done"),
        (lambda b: b.through("", T0)[0], "pkg", "already_done"),
        (lambda b: b.through("", T0, fail_at="smt")[0], "aoi", "scrapped"),
        (lambda b: "U-999999", "tst", "unknown_unit"),
    ],
)
def test_intertravamento_recusa(bench, setup, station, reason):
    uid = setup(bench)
    bench.evt(station, "scan", T0 + 500, unit=uid)
    rel = bench.release(station)
    assert rel["ok"] is False and rel["reason"] == reason


def test_reprovada_volta_para_a_mesma_estacao_e_vira_refugo_na_terceira(bench):
    uid, t = bench.through("", T0, fail_at="aoi")
    assert bench.engine.unit(uid)["unit"]["status"] == "rework"
    assert bench.cycle("aoi", uid, t, ok=False)["ok"] is True          # 2ª tentativa liberada
    assert bench.engine.unit(uid)["unit"]["status"] == "rework"
    bench.cycle("aoi", uid, t + 20, ok=False)                           # 3ª reprovação
    u = bench.engine.unit(uid)
    assert u["unit"]["status"] == "scrap"
    assert [s["attempt"] for s in u["steps"] if s["station"] == "aoi"] == [1, 2, 3]


def test_estacao_sem_leitor_recebe_a_mais_antiga_da_fila():
    b = Bench({"stations": {"aoi": {"reader": False}}})
    first, _ = b.through("", T0, upto="smt")
    second, _ = b.through("", T0 + 30, upto="smt")
    b.evt("aoi", "scan", T0 + 100, unit="")
    assert b.release("aoi")["unit"] == first
    b.evt("aoi", "cycle", T0 + 110, unit=first, dur_ms=8000, ok=True, degraded=False)
    b.evt("aoi", "scan", T0 + 120, unit="")
    assert b.release("aoi")["unit"] == second
    b.evt("aoi", "cycle", T0 + 130, unit=second, dur_ms=8000, ok=True, degraded=False)
    b.evt("aoi", "scan", T0 + 140, unit="")
    assert b.release("aoi") == {"req": 5, "ok": False, "unit": "", "reason": "no_unit"}


def test_duplicata_e_ignorada_e_lacuna_e_contada(bench):
    bench.evt("smt", "scan", T0 + 1, unit="")
    n = len(bench.sent)
    bench.msg("smt", "evt/scan", {"seq": 1, "boot": 1, "age_ms": 0, "unit": ""}, T0 + 2)   # QoS 1 reentregue
    assert len(bench.sent) == n
    bench.msg("smt", "evt/call", {"seq": 5, "boot": 1, "age_ms": 0, "on": False}, T0 + 3)
    assert bench.engine.live["smt"].gaps == 3


def test_age_ms_corrige_o_instante_do_evento(bench):
    bench.evt("smt", "scan", T0 + 100, unit="")
    bench.msg("smt", "evt/cycle", {"seq": 2, "boot": 1, "age_ms": 30000, "unit": "U-000001", "dur_ms": 12000,
                                    "ok": True, "degraded": True}, T0 + 150)
    step = bench.engine.unit("U-000001")["steps"][0]
    assert step["end_ts"] == pytest.approx(T0 + 120) and step["degraded"] == 1


def test_ciclo_sem_liberacao_e_registrado_como_degradado(bench):
    bench.msg("asm", "evt/cycle", {"seq": 1, "boot": 1, "age_ms": 0, "unit": "U-000777", "dur_ms": 15000,
                                    "ok": True, "degraded": True}, T0 + 50)
    u = bench.engine.unit("U-000777")
    assert u["steps"][0]["start_ts"] == pytest.approx(T0 + 35)
    assert any(e["kind"] == "degraded" for e in u["log"])


def test_mensagem_invalida_e_rejeitada_sem_derrubar(bench):
    bench.engine.handle("sfal/v1/smt/evt/cycle", "isto não é json", T0)
    bench.engine.handle("sfal/v1/smt/evt/cycle", '{"seq": 1, "boot": 1}', T0)        # falta dur_ms/ok
    bench.engine.handle("sfal/v1/naoexiste/tel", "{}", T0)
    assert bench.engine.rejected == 3
    assert bench.engine.units() == []


def test_oee_e_fpy_com_resultado_conhecido(bench):
    # 100 s de janela na asm (ideal 16 s): 4 ciclos de 20 s (3 OK, 1 NOK) e 20 s de chamado.
    for i in range(4):
        bench.through("", T0, upto="aoi")
    units = [u["id"] for u in reversed(bench.engine.units())]
    bench.engine.new_shift(T0 + 1000)
    t = T0 + 1000
    for i, uid in enumerate(units):
        bench.cycle("asm", uid, t, dur_s=20, ok=i != 1)
        t += 20
    bench.evt("asm", "call", t, on=True)
    bench.evt("asm", "call", t + 20, on=False)
    s = kpi.compute(bench.engine, T0 + 1100)["stations"]["asm"]
    assert s["down_s"] == pytest.approx(20)
    assert s["availability"] == pytest.approx(0.8)
    assert s["performance"] == pytest.approx(16 * 4 / 80)
    assert s["quality"] == pytest.approx(0.75)
    assert s["oee"] == pytest.approx(0.8 * 0.8 * 0.75)
    assert s["fpy"] == pytest.approx(0.75)


def test_estacao_muda_fica_offline_e_conta_como_parada(bench):
    bench.msg("tst", "tel", {"boot": 1, "up_ms": 1, "state": "IDLE", "unit": "", "temp": None}, T0 + 1)
    bench.engine.tick(T0 + 5)
    assert bench.engine.live["tst"].online
    bench.engine.tick(T0 + 20)
    assert not bench.engine.live["tst"].online
    snap = bench.engine.snapshot(T0 + 30)
    assert any(a["kind"] == "offline" and a["station"] == "tst" for a in snap["alerts"])
    bench.msg("tst", "tel", {"boot": 1, "up_ms": 2, "state": "IDLE", "unit": "", "temp": None}, T0 + 40)
    assert bench.engine.live["tst"].online
    assert kpi.compute(bench.engine, T0 + 50)["stations"]["tst"]["down_s"] == pytest.approx(20)


def test_cep_vermelho_retem_a_estacao_e_acende_a_torre(bench):
    t = T0
    for _ in range(5):
        t += 2
        bench.msg("smt", "tel", {"boot": 1, "up_ms": 1, "state": "IDLE", "unit": "", "temp": 245.2}, t)
    assert not bench.engine.live["smt"].hold
    bench.msg("smt", "tel", {"boot": 1, "up_ms": 1, "state": "IDLE", "unit": "", "temp": 251.0}, t + 2)   # > alvo + 3σ
    bench.engine.tick(t + 3)
    assert bench.engine.live["smt"].hold
    assert bench.sent[-1] == ("sfal/v1/smt/cmd/light", {"level": "red"})
    bench.evt("smt", "scan", t + 4, unit="")
    assert bench.release("smt")["reason"] == "hold"
    for i in range(10):                                                    # processo volta ao controle
        bench.msg("smt", "tel", {"boot": 1, "up_ms": 1, "state": "IDLE", "unit": "", "temp": 245.0 + 0.1 * (-1) ** i}, t + 6 + 2 * i)
    bench.engine.tick(t + 30)
    assert not bench.engine.live["smt"].hold
    assert bench.sent[-1] == ("sfal/v1/smt/cmd/light", {"level": "auto"})


def test_sem_intertravamento_nada_e_recusado():
    b = Bench({"rules": {"interlock": False}})
    uid, t = b.through("", T0, fail_at="aoi")
    b.evt("tst", "scan", t, unit=uid)
    assert b.release("tst")["ok"] is True


def test_simulador_reiniciado_retira_as_unidades_da_execucao_anterior(bench):
    bench.engine.handle("sfal/v1/sim/status", '{"online":true,"session":1}', T0)
    uid, t = bench.through("", T0 + 1, upto="aoi")
    bench.engine.handle("sfal/v1/sim/status", '{"online":true,"session":1}', t)       # mesma sessão: nada muda
    assert bench.engine.unit(uid)["unit"]["status"] == "wip"
    bench.engine.handle("sfal/v1/sim/status", '{"online":true,"session":2}', t + 1)
    assert bench.engine.unit(uid)["unit"]["status"] == "removed"
    assert kpi.compute(bench.engine, t + 2)["line"]["wip"] == 0
