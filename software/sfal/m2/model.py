"""Modelo SimPy do M2: placas concorrentes, inspeções SPI/AOI e forno contínuo com nove posições.

Hipóteses didáticas (não calibradas com equipamentos reais), as mesmas da entrega do M2:
  - chegadas a cada 20 s; filas ilimitadas; sem quebras; tempos de processo fixos;
  - três origens de defeito (pasta, colocação, refusão), cada uma com probabilidade independente (padrão 2 %);
  - SPI vê só defeito de pasta; AOI vê qualquer um; ambos detectam 95 %, sem falso positivo;
  - retidas no SPI/AOI saem da linha, sem retorno; o teste funcional detecta 100 % do que escapou;
  - cinco sorteios por placa, iguais em todos os cenários, para a comparação ser justa.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import simpy

SMT_PROCESS = [
    ("Impressora de pasta", 15), ("SPI", 5),
    ("Pick & Place 1", 12), ("Pick & Place 2", 12), ("Pick & Place 3", 12), ("Pick & Place 4", 12),
    ("Pick & Place 5", 12), ("Forno de refusão", 180), ("AOI", 5), ("Saída SMT", 1),
]
MANUAL_PROCESS = [
    ("Gravação de FW", 14), ("PCBA no chassi", 18), ("Display", 16), ("Bateria", 27), ("Alto-falante", 15),
    ("Microfone", 21), ("Câmera traseira", 24), ("Câmera frontal", 13), ("Botões e vibra", 22),
    ("Tampa traseira", 17), ("Teste funcional", 26), ("Embalagem", 19),
]
PROCESS = SMT_PROCESS + MANUAL_PROCESS
STATIONS = [name for name, _ in PROCESS]
MANUAL = [name for name, _ in MANUAL_PROCESS]
OVEN = "Forno de refusão"
CAPACITIES = {name: (9 if name == OVEN else 1) for name in STATIONS}
ARRIVAL_S = 20

# Balanceamentos hipotéticos dos cenários Lean (tempos em segundos).
LEAN_TIMES = {"Bateria": 19, "Alto-falante": 19, "Microfone": 19}
LEAN_FULL_TIMES = {**LEAN_TIMES, "Câmera traseira": 19, "Câmera frontal": 18, "Botões e vibra": 19,
                   "Tampa traseira": 20, "Teste funcional": 19, "Embalagem": 20}

FILA, ENTRADA, SAIDA = 0, 1, 2
PENDENTE, APROVADA, REPROVADA = 0, 1, 2


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    resumo: str
    papel: str                     # "problema" ou "solucao"
    spi: bool = True
    aoi: bool = True
    times: dict = field(default_factory=dict)


SCENARIOS = {
    s.id: s
    for s in (
        Scenario("atual", "Atual", "Sem SPI nem AOI: o defeito só aparece no teste funcional. Tempos manuais originais.",
                 "problema", spi=False, aoi=False),
        Scenario("spi_aoi", "SPI/AOI", "Inspeção na fonte: SPI após a impressora e AOI após o forno.", "solucao"),
        Scenario("lean", "SPI/AOI + Lean local", "Inspeção na fonte + bateria, alto-falante e microfone com 19 s cada.",
                 "solucao", times=LEAN_TIMES),
        Scenario("lean_ampliado", "SPI/AOI + Lean ampliado",
                 "Inspeção na fonte + todas as estações manuais balanceadas em torno do takt de 20 s.", "solucao",
                 times=LEAN_FULL_TIMES),
    )
}


@dataclass
class Run:
    scenario: Scenario
    horizon: float                 # segundos simulados
    seed: int
    stations: list[str]            # estações ativas, na ordem da linha
    durations: list[float]
    capacities: list[int]
    events: list[tuple]            # (t, peça, índice da estação, tipo, resultado)
    reasons: dict[int, str]        # índice do evento -> defeitos que causaram a reprovação


def simulate(scenario_id: str = "atual", hours: float = 8.0, seed: int = 7, defect_rate: float = 0.02,
             spi_detection: float = 0.95, aoi_detection: float = 0.95) -> Run:
    sc = SCENARIOS[scenario_id]
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("Duração do turno deve ser positiva e finita")
    horizon = hours * 3600
    count = math.ceil(horizon / ARRIVAL_S)
    times = {**dict(PROCESS), **sc.times}
    process = [(n, times[n]) for n in STATIONS if not (n == "SPI" and not sc.spi) and not (n == "AOI" and not sc.aoi)]
    index = {name: i for i, (name, _) in enumerate(process)}

    env = simpy.Environment()
    rng = random.Random(seed)
    resources = {name: simpy.Resource(env, capacity=CAPACITIES[name]) for name, _ in process}
    oven_gate = simpy.Resource(env, capacity=1)   # distância mínima entre placas na entrada do forno
    events: list[tuple] = []
    reasons: dict[int, str] = {}

    def record(piece: int, station: str, kind: int, result: int = PENDENTE, reason: str | None = None) -> None:
        if reason:
            reasons[len(events)] = reason
        events.append((env.now, piece, index[station], kind, result))

    def piece_flow(piece: int, draws: list[float]):
        defects: list[str] = []
        for station, duration in process:
            record(piece, station, FILA)
            if station == OVEN:
                # Forno contínuo: entrada espaçada em 20 s, permanência de `duration`, até nove placas juntas.
                with oven_gate.request() as gate:
                    yield gate
                    request = resources[station].request()
                    yield request
                    record(piece, station, ENTRADA)
                    start = env.now
                    yield env.timeout(20)
                yield env.timeout(max(0, duration - (env.now - start)))
                if draws[2] < defect_rate:
                    defects.append("refusão")
                record(piece, station, SAIDA)
                resources[station].release(request)
                continue
            with resources[station].request() as request:
                yield request
                record(piece, station, ENTRADA)
                yield env.timeout(duration)
                if station == "Impressora de pasta" and draws[0] < defect_rate:
                    defects.append("pasta")
                if station == "Pick & Place 5" and draws[1] < defect_rate:
                    defects.append("colocação")
                rejected = (
                    (station == "SPI" and "pasta" in defects and draws[3] < spi_detection)
                    or (station == "AOI" and bool(defects) and draws[4] < aoi_detection)
                    or (station == "Teste funcional" and bool(defects))
                )
                inspected = station in ("SPI", "AOI", "Teste funcional", "Embalagem")
                record(piece, station, SAIDA, REPROVADA if rejected else APROVADA if inspected else PENDENTE,
                       ", ".join(defects) if rejected else None)
                if rejected:
                    return

    def source():
        for n in range(1, count + 1):
            env.process(piece_flow(n, [rng.random() for _ in range(5)]))
            yield env.timeout(ARRIVAL_S)

    env.process(source())
    env.run(until=horizon)
    return Run(sc, horizon, seed, [n for n, _ in process], [d for _, d in process],
               [CAPACITIES[n] for n, _ in process], events, reasons)
