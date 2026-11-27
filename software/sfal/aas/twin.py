"""Gêmeo das estações e da linha: os campos publicados em MQTT e espelhados no FA³ST.

A tabela de campos é a fonte única: dela saem a mensagem MQTT (`payload_*`), o modelo AAS e as conexões do
FA³ST (`faaast.py`). Tópicos fora de `sfal/v1/` para o motor não receber de volta o que o servidor publica.

  sfal/twin/v1/station/<id>/<grupo>   estado, processo ou indicadores de uma estação
  sfal/twin/v1/line/indicadores       indicadores da linha
"""

from __future__ import annotations

from typing import Any

from ..config import Config, Station

TOPIC_STATION = "sfal/twin/v1/station/{id}/{group}"
TOPIC_LINE = "sfal/twin/v1/line/{group}"

# Grupos por ritmo de mudança. O FA³ST reprocessa todas as propriedades de um tópico a cada mensagem; publicar
# tudo a cada segundo (mais de 100 atualizações por segundo) o deixava minutos atrás da linha.
#   estado        só quando muda (transições da máquina de estados chegam na hora)
#   processo      no máximo a cada 5 s
#   indicadores   no máximo a cada 10 s
MIN_INTERVAL_S = {"estado": 0.0, "processo": 5.0, "indicadores": 10.0}
GROUP = {"cycle_ms": "processo", "temp": "processo"}       # campos do submodelo Estado que mudam o tempo todo


def group_of(submodel: str, key: str) -> str:
    return GROUP.get(key, "indicadores" if submodel == "Indicadores" else "estado")


# (submodelo, idShort, chave no JSON, tipo, descrição)
STATION_FIELDS = [
    ("Estado", "Estado", "state", "xs:string", "Máquina de estados: IDLE, WAIT, RUNNING, BLOCKED ou OFFLINE"),
    ("Estado", "Online", "online", "xs:boolean", "A estação está conectada ao broker"),
    ("Estado", "Unidade", "unit", "xs:string", "Número de série da unidade em processo"),
    ("Estado", "CicloMs", "cycle_ms", "xs:int", "Tempo decorrido do ciclo atual, em milissegundos"),
    ("Estado", "Chamado", "call", "xs:boolean", "Chamado (andon) aberto"),
    ("Estado", "Retida", "hold", "xs:boolean", "Retida por alarme de processo (jidoka)"),
    ("Estado", "MotivoBloqueio", "reason", "xs:string", "Motivo do último bloqueio pelo intertravamento"),
    ("Estado", "TorreLuminosa", "light", "xs:string", "Comando do servidor para a torre: auto, yellow ou red"),
    ("Estado", "Fila", "waiting", "xs:int", "Unidades esperando por esta estação"),
    ("Estado", "Temperatura", "temp", "xs:double", "Temperatura do processo em °C (0 se a estação não mede)"),
    ("Indicadores", "OEE", "oee", "xs:double", "Disponibilidade × desempenho × qualidade, de 0 a 1"),
    ("Indicadores", "FPY", "fpy", "xs:double", "Aprovadas na primeira tentativa, de 0 a 1"),
    ("Indicadores", "Disponibilidade", "availability", "xs:double", ""),
    ("Indicadores", "Desempenho", "performance", "xs:double", ""),
    ("Indicadores", "Qualidade", "quality", "xs:double", ""),
    ("Indicadores", "Ciclos", "cycles", "xs:int", "Ciclos no turno"),
    ("Indicadores", "Reprovacoes", "nok", "xs:int", "Ciclos reprovados no turno"),
    ("Indicadores", "CicloMedioS", "avg_cycle_s", "xs:double", "Tempo médio de ciclo, em segundos"),
    ("Indicadores", "ParadaS", "down_s", "xs:double", "Tempo parado no turno, em segundos"),
]
LINE_FIELDS = [
    ("Indicadores", "FPY", "fpy", "xs:double", "Unidades sem nenhuma reprovação ÷ unidades encerradas"),
    ("Indicadores", "RTY", "rty", "xs:double", "Produto dos FPY das estações"),
    ("Indicadores", "OEE", "oee", "xs:double", "Unidades boas × takt ÷ tempo planejado"),
    ("Indicadores", "COPQ", "copq", "xs:double", "1 − custo da não qualidade"),
    ("Indicadores", "Planejadas", "planned", "xs:int", "Unidades planejadas ainda não iniciadas"),
    ("Indicadores", "EmProcesso", "wip", "xs:int", ""),
    ("Indicadores", "Prontas", "done", "xs:int", ""),
    ("Indicadores", "Refugo", "scrap", "xs:int", ""),
    ("Indicadores", "LeadTimeMedioS", "lead_time_avg_s", "xs:double", "Lead time médio das prontas, em segundos"),
    ("Indicadores", "VazaoPorHora", "throughput_h", "xs:double", ""),
    ("Indicadores", "Gargalo", "bottleneck", "xs:string", "Estação de ciclo médio mais longo"),
]
_ZERO = {"xs:string": "", "xs:boolean": False, "xs:int": 0, "xs:double": 0.0}


def _clean(fields, source: dict[str, Any]) -> dict[str, Any]:
    """Todo campo sempre presente e do tipo certo: o FA³ST descarta a mensagem se o JSONPath não acha o valor."""
    out = {}
    for _, _, key, vtype, _ in fields:
        v = source.get(key)
        if v is None:
            v = _ZERO[vtype]
        elif vtype == "xs:int":
            v = int(v)
        elif vtype == "xs:double":
            v = round(float(v), 4)
        elif vtype == "xs:boolean":
            v = bool(v)
        else:
            v = str(v)
        out[key] = v
    return out


def payloads_station(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Mensagens de uma estação, por grupo. `row` é uma estação do retrato do motor (kpi.snapshot)."""
    flat = _clean(STATION_FIELDS, {**row["kpi"], **{k: v for k, v in row.items() if k != "kpi"}})
    out: dict[str, dict[str, Any]] = {}
    for sub, _, key, _, _ in STATION_FIELDS:
        out.setdefault(group_of(sub, key), {})[key] = flat[key]
    return out


def payloads_line(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {"indicadores": _clean(LINE_FIELDS, snap["line"]["kpi"])}


def capabilities(st: Station, cfg: Config) -> list[tuple[str, Any, str]]:
    """Submodelo estático Capacidade: o que a estação (provedor) oferece."""
    return [
        ("Capacidade", st.skill, "xs:string"),
        ("Nome", st.name, "xs:string"),
        ("PosicaoNaRota", st.index + 1, "xs:int"),
        ("CicloIdealS", st.ideal_cycle_s, "xs:double"),
        ("TemLeitor", st.reader, "xs:boolean"),
        ("PostoManual", st.kind == "manual", "xs:boolean"),
        ("AoReprovar", "retrabalho" if st.on_fail == "rework" else "refugo", "xs:string"),
        ("InspecaoPorIA", st.id == (cfg.vision or {}).get("station"), "xs:boolean"),
    ]
