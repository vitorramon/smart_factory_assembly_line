from sfal import kpi, sintese

from .conftest import T0


def test_m1_tem_os_seis_m_e_os_indicadores():
    m1 = sintese.load_m1()
    assert [c["m"] for c in m1["ishikawa"]["causas"]] == ["Máquina", "Método", "Mão de obra", "Material", "Medida", "Meio ambiente"]
    assert all(len(c["porques"]) == 5 for c in m1["ishikawa"]["causas"])
    assert {i["id"]: (i["atual"], i["meta"]) for i in m1["indicadores"]}["fpy"] == (0.78, 0.92)
    assert sum(i["qtd"] for i in m1["pareto"]["itens"]) == 245


def test_sintese_junta_as_tres_geracoes(bench):
    uid, t = bench.through("", T0, fail_at="aoi")
    bench.evt("tst", "scan", t, unit=uid)                    # tentativa de avanço barrada
    bench.through("", t + 5)
    s = sintese.build(bench.engine, t + 200)
    g = {x["id"]: x for x in s["geracoes"]}
    assert g["oee"]["m1_atual"] == 0.68 and g["oee"]["meta"] == 0.80
    assert round(g["oee"]["m2_atual"] * 100, 2) == 68.47 and round(g["oee"]["m2_solucao"] * 100, 2) == 92.15
    assert g["fpy"]["m3"] == 1.0                              # uma unidade encerrada, sem reprovação
    assert s["m3"]["evidence"]["blocked_route"] == 1 and s["m3"]["evidence"]["nok_aoi"] == 1
    assert s["m3"]["origem"].startswith("medido") is False    # estações do teste não são ESP32
    assert all("{" not in c["m3"]["texto"] for c in s["ishikawa"]["causas"])
    assert [i["qtd"] for i in s["pareto"]["m3"]["itens"]] == [0, 1, 0, 0, 0]


def test_copq_com_resultado_conhecido(bench):
    bench.through("", T0, fail_at="aoi")                      # 1 reprovação na AOI = R$ 60
    bench.through("", T0 + 100, fail_at="smt")                # refugo na SMT = R$ 240 + R$ 60 de tratamento
    k = kpi.compute(bench.engine, T0 + 300)["line"]
    assert k["cost"] == 60 + 240 + 60
    assert k["copq"] == 1 - 360 / (2 * 240)
