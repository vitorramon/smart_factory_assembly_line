from sfal.spc import Chart


def feed(chart, values):
    for i, v in enumerate(values):
        level, rule = chart.add(float(i), v)
    return level, rule


def test_processo_estavel_nao_alarma():
    assert feed(Chart(100, 1), [100.2, 99.7, 100.4, 99.9, 100.1, 99.6, 100.3, 99.8, 100.2, 99.9]) == ("", "")


def test_ponto_alem_de_3_sigma_e_vermelho():
    assert feed(Chart(100, 1), [100.1, 99.9, 103.1])[0] == "red"


def test_oito_pontos_do_mesmo_lado_e_amarelo():
    level, rule = feed(Chart(100, 1), [100.5, 100.2, 100.6, 100.3, 100.7, 100.2, 100.4, 100.3])
    assert level == "yellow" and "mesmo lado" in rule


def test_tendencia_de_seis_pontos_e_amarelo():
    level, rule = feed(Chart(100, 1), [99.0, 99.3, 99.6, 99.9, 100.2, 100.5])
    assert level == "yellow" and "tendência" in rule


def test_alarme_so_encerra_apos_dez_pontos_limpos():
    c = Chart(100, 1)
    feed(c, [100.1, 99.9, 104.0])
    vals = [99.9, 100.1] * 5
    for i, v in enumerate(vals[:-1]):
        assert c.add(10.0 + i, v)[0] == "red"
    assert c.add(30.0, vals[-1]) == ("", "")
