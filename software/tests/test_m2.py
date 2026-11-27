"""O modelo portado do M2 reproduz os números publicados na entrega (turno de 8 h, semente 7)."""

import pytest

from sfal.m2 import metrics, model, service

# cenário: concluídas, NG no teste, WIP final, lead time (min), OEE %, FPY %, RTY %, 1 − COPQ %
PUBLICADO = {
    "atual": (986, 63, 391, 69.43, 68.47, 94.00, 94.00, 95.6),
    "spi_aoi": (1047, 2, 303, 57.91, 72.71, 99.81, 93.67, 98.7),
    "lean": (1087, 2, 263, 50.73, 75.49, 99.82, 93.68, 98.7),
    "lean_ampliado": (1327, 2, 23, 8.10, 92.15, 99.85, 93.71, 98.7),
}


@pytest.mark.parametrize("scenario", list(PUBLICADO))
def test_reproduz_os_resultados_do_m2(scenario):
    done, ng, wip, lead, oee, fpy, rty, copq = PUBLICADO[scenario]
    m = metrics.compute(model.simulate(scenario, 8, 7))["summary"]
    assert (m["done"], m["test_rejected"], m["wip"]) == (done, ng, wip)
    assert m["lead_time_s"] / 60 == pytest.approx(lead, abs=0.005)
    assert m["oee"] * 100 == pytest.approx(oee, abs=0.005)
    assert m["fpy"] * 100 == pytest.approx(fpy, abs=0.005)
    assert m["rty"] * 100 == pytest.approx(rty, abs=0.005)
    assert m["copq"] * 100 == pytest.approx(copq, abs=0.05)


def test_serie_termina_no_resumo_e_payload_e_coerente():
    r = service.run("atual", 1.0, 7)
    assert len(r["series"]) == metrics.SAMPLES
    assert r["series"][-1]["done"] == r["summary"]["done"]
    n = len(r["events"]["t"])
    assert all(len(col) == n for col in r["events"].values())
    assert "SPI" not in r["stations"] and "AOI" not in r["stations"]
    assert r["events"]["t"] == sorted(r["events"]["t"])
