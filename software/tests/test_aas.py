"""AAS: pedidos e unidades planejadas, gêmeo das estações, modelo do FA³ST e shells do BaSyx."""

import json

from sfal import kpi
from sfal.aas import faaast, ids, product, twin

from .conftest import T0


def test_pedido_planeja_unidades_antes_de_fabricar(bench):
    planned0 = bench.engine.planned()
    assert planned0 == bench.cfg.orders["lot_size"]                 # lote automático na partida
    order = bench.engine.plan_order(3, T0)
    assert len(order["units"]) == 3 and bench.engine.planned() == planned0 + 3
    assert kpi.compute(bench.engine, T0 + 1)["line"]["started"] == 0   # planejada não conta como iniciada
    first = "U-000001"                                                # a mais antiga das planejadas
    rel = bench.cycle("smt", "", T0 + 5)                              # a primeira estação inicia a mais antiga
    assert rel["unit"] == first
    u = bench.engine.unit(first)["unit"]
    assert u["status"] == "wip" and u["created_ts"] == T0 + 5 and u["planned_ts"] == T0 and u["order_id"] == 1
    assert bench.engine.orders()[-1]["wip"] == 1


def test_lote_automatico_e_reposto_quando_acaba(bench):
    lot = bench.cfg.orders["lot_size"]
    for i in range(lot):
        bench.cycle("smt", "", T0 + 20 * i)
    bench.engine.tick(T0 + 20 * lot)
    assert bench.engine.planned() >= lot - 1 and len(bench.engine.orders()) == 2


def test_etiqueta_de_unidade_planejada_so_entra_pela_primeira_estacao(bench):
    uid = bench.engine.units(status="planned", limit=500)[0]["id"]
    bench.evt("asm", "scan", T0 + 1, unit=uid)
    assert bench.release("asm")["reason"] == "skipped_step"
    assert bench.cycle("smt", uid, T0 + 2)["ok"] is True


def test_gemeo_separa_por_ritmo_e_nunca_manda_nulo(bench):
    bench.msg("smt", "tel", {"boot": 1, "up_ms": 1, "state": "RUNNING", "unit": "U-1", "cycle_ms": 900, "temp": 245.1}, T0 + 1)
    snap = bench.engine.snapshot(T0 + 2)
    groups = twin.payloads_station(snap["stations"][0])
    assert set(groups) == {"estado", "processo", "indicadores"}
    assert groups["estado"]["state"] == "RUNNING" and groups["estado"]["unit"] == "U-1"
    assert set(groups["processo"]) == {"cycle_ms", "temp"} and groups["processo"]["temp"] == 245.1
    idle = twin.payloads_station(snap["stations"][1])                # estação sem dados: zeros, nunca null
    assert None not in [v for g in idle.values() for v in g.values()] and idle["indicadores"]["oee"] == 0.0
    assert twin.payloads_line(snap)["indicadores"]["planned"] == bench.engine.planned()


def test_modelo_e_configuracao_do_faaast(bench):
    m, c = faaast.model(bench.cfg), faaast.config(bench.cfg, "tcp://broker:1883")
    assert [a["idShort"] for a in m["assetAdministrationShells"]] == ["Estacao_smt", "Estacao_aoi", "Estacao_asm", "Estacao_tst", "Estacao_pkg", "Linha"]
    shorts = [s["idShort"] for s in m["submodels"]]
    assert len(shorts) == len(set(shorts)) and "Estado_aoi" in shorts       # nomes únicos no OPC UA
    sm_ids = {s["id"] for s in m["submodels"]}
    subs = c["assetConnections"][0]["subscriptionProviders"]
    for key, prov in subs.items():                                           # toda assinatura aponta para algo que existe
        sm_id, short = key.removeprefix("(Submodel)").split(", (Property)")
        sm = next(s for s in m["submodels"] if s["id"] == sm_id)
        assert sm_id in sm_ids and any(e["idShort"] == short for e in sm["submodelElements"])
        assert prov["topic"].startswith("sfal/twin/v1/") and prov["query"].startswith("$.")
    assert subs[f"(Submodel){ids.station_sm('asm', 'estado')}, (Property)Estado"]["topic"] == "sfal/twin/v1/station/asm/estado"
    assert subs[f"(Submodel){ids.station_sm('asm', 'estado')}, (Property)CicloMs"]["topic"] == "sfal/twin/v1/station/asm/processo"
    assert "clientId" not in c["assetConnections"][0]
    opc = c["endpoints"][0]
    assert opc["tcpPort"] == 4840 and opc["supportedAuthentications"] == ["Anonymous"]
    cap = next(s for s in m["submodels"] if s["idShort"] == "Capacidade_aoi")
    assert {e["idShort"]: e["value"] for e in cap["submodelElements"]}["InspecaoPorIA"] == "true"


def test_shell_do_produto_lista_as_capacidades_pedidas(bench):
    shell, sms = product.product_type(bench.cfg)
    assert shell["assetInformation"]["assetKind"] == "Type" and len(shell["submodels"]) == 2
    steps = next(e for e in sms[1]["submodelElements"] if e["idShort"] == "Etapas")["value"]
    row = {e["idShort"]: e["value"] for e in steps[1]["value"]}
    assert row["Capacidade"] == "Inspeção óptica por IA" and row["Provedor"] == ids.station_aas("aoi")


def test_shell_da_unidade_acompanha_a_fabricacao(bench):
    uid = "U-000001"
    shell, sm = product.unit(bench.cfg, bench.engine.unit(uid), "http://x")
    v = {e["idShort"]: e.get("value") for e in sm["submodelElements"]}
    assert v["Status"] == "planejada" and v["Passos"] == [] and "IniciadaEm" not in v and v["Pedido"] == "1"
    assert shell["derivedFrom"]["keys"][0]["value"] == ids.product_aas("SFAL-X1")

    bench.engine.dirty_units.clear()
    done, _ = bench.through("", T0 + 10, fail_at="aoi")
    assert done == uid and uid in bench.engine.dirty_units                # o sincronizador fica sabendo
    _, sm = product.unit(bench.cfg, bench.engine.unit(uid), "http://x")
    v = {e["idShort"]: e.get("value") for e in sm["submodelElements"]}
    assert v["Status"] == "retrabalho" and v["ProximaEstacao"] == "aoi" and v["Reprovacoes"] == "1"
    last = {e["idShort"]: e["value"] for e in v["Passos"][-1]["value"]}
    assert last["Estacao"] == "aoi" and last["Resultado"] == "reprovada" and last["Fim"].endswith("Z")
    json.dumps(sm)                                                          # serializável
    assert ids.b64("urn:sfal:aas:unit:U-000001") == "dXJuOnNmYWw6YWFzOnVuaXQ6VS0wMDAwMDE"
