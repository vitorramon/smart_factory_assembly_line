"""Planta simulada: o mundo físico em volta das estações.

Cada estação é uma instância do firmware real (firmware_lib.FirmwareStation). O que este módulo
simula é o que fica do lado de fora da placa: as unidades andando pela linha, o operador ou a
máquina apertando os botões, o leitor lendo a etiqueta, o forno aquecendo, defeitos e quebras.
Quem decide o que fazer com esses estímulos é o firmware.

O relógio é virtual (`step(now_ms)`), então a mesma planta roda em tempo real contra um broker
MQTT (live.py) ou em tempo acelerado contra o motor em memória (whatif.py).
"""

from __future__ import annotations

import json
import math
import random
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import Config, Station
from .firmware_lib import BTN_CALL, BTN_FAIL, BTN_START, FirmwareStation

Publish = Callable[[str, str, int, bool], bool]
PRESS_MS = 250  # tempo que um botão fica apertado


@dataclass
class Unit:
    serial: int
    label: str = ""                     # etiqueta gravada (número de série dado pelo servidor)
    defects: set[str] = field(default_factory=set)
    fails_here: int = 0
    shots: int = 0                     # quantas vezes foi fotografada (cada foto é diferente)


class Actor:
    """Operador/máquina de uma estação: age sobre as entradas do firmware e observa as saídas."""

    def __init__(self, plant: Plant, st: Station, fw: FirmwareStation):
        self.plant, self.st, self.fw = plant, st, fw
        self.p = st.sim
        self.queue: deque[Unit] = deque()
        self.arrivals: list[tuple[int, Unit, bool]] = []  # (instante, unidade, entra na frente?)
        self.unit: Unit | None = None
        self.phase = "idle"       # idle | requested | working | ack
        self.t_next = 0
        self.t_done = 0
        self.result_ok = True
        self.release: list[tuple[int, int]] = []          # (instante, botão) a soltar
        self.link_down_until = 0
        self.slow_until, self.slow_factor = 0, 1.0
        self.call_until = 0
        self.inspection = None    # veredito pendente da inspeção por IA (objeto com .done() e .result())
        self.t_inspect_limit = 0
        self.temp = self.p.get("temp")
        self.temp_offset = 0.0
        mtbf = self.p.get("mtbf_s")
        self.t_break = int(plant.rng.expovariate(1 / mtbf) * 1000) if mtbf else None

    # -- auxiliares
    def press(self, button: int, now: int) -> None:
        self.fw.set_button(button, True)
        self.release.append((now + PRESS_MS, button))

    def arrive(self, unit: Unit, at: int, front: bool = False) -> None:
        self.arrivals.append((at, unit, front))

    def _duration_ms(self, now: int) -> int:
        mean = float(self.p.get("mean_s", self.st.ideal_cycle_s))
        cv = float(self.p.get("cv", 0.1))
        s2 = math.log(1 + cv * cv)
        d = self.plant.rng.lognormvariate(math.log(mean) - s2 / 2, math.sqrt(s2))
        if now < self.slow_until:
            d *= self.slow_factor
        return int(max(1.0, d) * 1000)

    def _judge(self, unit: Unit) -> bool:
        """Processa a unidade: pode introduzir defeito; se a estação inspeciona, decide OK/NOK."""
        rng, p = self.plant.rng, self.p
        if p.get("defect") and rng.random() < float(p.get("defect_p", 0)) * self.plant.defect_factor:
            unit.defects.add(p["defect"])
        detects = p.get("detects")
        if not detects:
            return True
        found = any(d in detects and rng.random() < float(p.get("detect_p", 1)) for d in unit.defects)
        return not (found or rng.random() < float(p.get("false_fail_p", 0)))

    # -- passo de simulação
    def step(self, now: int) -> None:
        fw = self.fw
        for item in [r for r in self.release if r[0] <= now]:
            self.release.remove(item)
            fw.set_button(item[1], False)
        for item in [a for a in self.arrivals if a[0] <= now]:
            self.arrivals.remove(item)
            (self.queue.appendleft if item[2] else self.queue.append)(item[1])

        # sensor de temperatura: ruído autorregressivo em torno do ponto de operação
        if self.temp is not None:
            noise = float(self.p.get("temp_noise", 0.3))
            self.temp_offset = 0.9 * self.temp_offset + self.plant.rng.gauss(0, noise * 0.45)
            fw.set_temp(self.temp + self.temp_offset + self.plant.temp_fault(self.st.id, now))

        # quebras: abre chamado, espera o reparo, fecha
        if self.t_break is not None and now >= self.t_break and not fw.call_active and not self.release:
            repair = int(self.plant.rng.expovariate(1 / float(self.p.get("mttr_s", 30))) * 1000) + 3000
            self.call_until = now + repair
            self.t_break = None
            self.press(BTN_CALL, now)
        if self.call_until:
            if self.phase in ("working", "capturing"):
                self.t_done += self.plant.dt   # trabalho parado durante o chamado
            if now >= self.call_until and fw.call_active and not self.release:
                self.press(BTN_CALL, now)
                self.call_until = 0
                mtbf = self.p.get("mtbf_s")
                self.t_break = now + int(self.plant.rng.expovariate(1 / mtbf) * 1000) if mtbf else None
            return

        if self.phase == "idle":
            if now >= self.t_next and self.queue and fw.state == "IDLE" and not fw.call_active and not self.release:
                self.unit = self.queue.popleft()
                if self.st.reader and self.unit.label:
                    fw.push_scan(self.unit.label)
                else:
                    self.press(BTN_START, now)
                self.phase = "requested"
                self.t_next = now + 5000
        elif self.phase == "requested":
            if fw.state == "RUNNING":
                if not self.unit.label:
                    self.unit.label = fw.unit
                if self.plant.camera and self.st.id == self.plant.vision_station:
                    # Inspeção por IA: a máquina posiciona e ilumina a placa (o tempo de ciclo da estação) e só
                    # então fotografa. Sem esse tempo o ciclo duraria milissegundos, o que nenhuma AOI faz.
                    self.t_done = now + self._duration_ms(now)
                    self.phase = "capturing"
                else:
                    self.result_ok = self._judge(self.unit)
                    self.t_done = now + self._duration_ms(now)
                    self.phase = "working"
            elif fw.state == "BLOCKED":
                self._blocked(now)
            elif fw.state == "IDLE" and now >= self.t_next:   # pedido não pegou: tenta de novo
                self.queue.appendleft(self.unit)
                self.unit, self.phase = None, "idle"
        elif self.phase == "capturing":
            if now >= self.t_done:
                # A "câmera" fotografa e manda ao servidor; quem decide é o modelo, e quem encerra o ciclo é o
                # firmware, ao receber o resultado.
                photo = self.plant.photograph(self.unit)
                self.inspection = self.plant.camera(self.st.id, self.unit.label, photo.jpeg,
                                                    {"defect": photo.defect is not None, "kind": photo.defect})
                self.t_inspect_limit = now + self.plant.vision_timeout_ms
                self.phase = "inspecting"
        elif self.phase == "inspecting":
            verdict = self.inspection.result() if self.inspection.done() else None
            if verdict is not None and verdict.get("ok") is not None:
                if fw.state != "RUNNING":                       # o firmware recebeu o resultado e encerrou o ciclo
                    self.result_ok = bool(verdict["ok"])
                    self._finished(now)
                    self.inspection, self.phase, self.t_next = None, "idle", now + 400
                elif now >= self.t_inspect_limit + 5000:        # veredito existe mas o comando não chegou à estação
                    self.result_ok = bool(verdict["ok"])
                    self.inspection, self.t_done, self.phase = None, now, "working"
            elif (verdict is not None) or now >= self.t_inspect_limit:
                # Sem veredito (servidor ou modelo fora do ar): volta ao critério antigo, como um inspetor manual.
                self.plant.vision_fallbacks += 1
                self.result_ok = self._judge(self.unit)
                self.inspection, self.t_done, self.phase = None, now, "working"
        elif self.phase == "working":
            if now >= self.t_done and not self.release:
                self.press(BTN_START if self.result_ok else BTN_FAIL, now)
                self._finished(now)
                self.phase, self.t_next = "idle", now + PRESS_MS + 150
        elif self.phase == "ack" and now >= self.t_next and not self.release:
            if fw.state == "BLOCKED":
                self.press(BTN_START, now)
            self.phase, self.t_next = "idle", now + PRESS_MS + 150

    def _blocked(self, now: int) -> None:
        reason, unit = self.fw.block_reason, self.unit
        self.plant.blocked[reason] = self.plant.blocked.get(reason, 0) + 1
        if reason in ("hold", "no_unit", "no_server", "no_link", "in_process"):
            self.queue.appendleft(unit)             # nada errado com a unidade: espera e tenta de novo
            self.t_next = now + 3000
        elif reason == "scrapped":
            self.plant.scrapped.append(unit)
            self.t_next = now + 1500
        else:                                        # intertravamento de rota: unidade sai do fluxo
            self.plant.diverted.append(unit)
            self.t_next = now + 1500
        self.unit, self.phase = None, "ack"

    def _finished(self, now: int) -> None:
        unit, plant = self.unit, self.plant
        self.unit = None
        if self.result_ok:
            unit.fails_here = 0
            plant.forward(self.st, unit, now)
            return
        unit.fails_here += 1
        if self.st.on_fail == "scrap" or unit.fails_here >= plant.max_attempts:
            plant.scrapped.append(unit)
            return
        # bancada de retrabalho: tenta corrigir os defeitos que esta estação enxerga e devolve a unidade
        detects = set(self.p.get("detects") or unit.defects)
        if plant.rng.random() < float(self.p.get("fix_p", 0.9)):
            unit.defects -= detects
        self.arrive(unit, now + int(float(self.p.get("rework_s", 60)) * 1000), front=True)


class RemoteActor:
    """Estação com placa real: a planta só acompanha os eventos dela para mover as unidades."""

    def __init__(self, plant: Plant, st: Station):
        self.plant, self.st = plant, st
        self.queue: deque[Unit] = deque()
        self.arrivals: list[tuple[int, Unit, bool]] = []
        self.fw = None

    def arrive(self, unit: Unit, at: int, front: bool = False) -> None:
        self.arrivals.append((at, unit, front))

    def step(self, now: int) -> None:
        for item in [a for a in self.arrivals if a[0] <= now]:
            self.arrivals.remove(item)
            (self.queue.appendleft if item[2] else self.queue.append)(item[1])

    def observed_cycle(self, label: str, ok: bool, now: int) -> None:
        unit = next((u for u in self.queue if u.label == label), None) or (self.queue[0] if self.queue else None)
        if unit is None:
            unit = Unit(serial=self.plant.next_serial(), label=label)   # unidade criada na própria bancada
        else:
            self.queue.remove(unit)
        unit.label = unit.label or label
        if ok:
            unit.fails_here = 0
            self.plant.forward(self.st, unit, now)
        else:
            unit.fails_here += 1
            if self.st.on_fail == "scrap" or unit.fails_here >= self.plant.max_attempts:
                self.plant.scrapped.append(unit)
            else:
                self.queue.appendleft(unit)


class Plant:
    def __init__(self, cfg: Config, publish: Publish, seed: int | None = None, real: tuple[str, ...] = (), dt: int = 50):
        self.cfg = cfg
        self.rng = random.Random(cfg.simulation["seed"] if seed is None else seed)
        self.dt = dt
        self.max_attempts = int(cfg.rules["max_attempts"])
        self.transfer_ms = int(float(cfg.simulation["transfer_s"]) * 1000)
        self.arrival_ms = int(float(cfg.simulation["arrival_s"]) * 1000)
        self._serial = 0
        self._next_arrival = 0
        self.inbox: deque[tuple[str, str]] = deque()
        self.finished: list[Unit] = []
        self.scrapped: list[Unit] = []
        self.diverted: list[Unit] = []
        self.blocked: dict[str, int] = {}
        self.defect_factor = 1.0
        self._defect_until = 0
        self._drift: dict[str, tuple[int, int, float]] = {}   # estação -> (início, fim, °C/s)
        # Inspeção por IA: `camera(estação, unidade, jpeg, gabarito)` devolve um objeto tipo Future com o veredito.
        # Sem câmera ligada (testes e "E se?"), a estação decide pelo sorteio de detect_p.
        self.camera = None
        self.vision_station = (cfg.vision or {}).get("station")
        self.vision_timeout_ms = int(float((cfg.vision or {}).get("timeout_s", 15)) * 1000)
        self.vision_fallbacks = 0
        self.stations: dict[str, FirmwareStation] = {}
        self.actors: dict[str, Actor | RemoteActor] = {}
        self._link_ok: dict[str, Callable[[], bool]] = {}
        for st in cfg.stations:
            if st.id in real:
                self.actors[st.id] = RemoteActor(self, st)
                continue
            fw = FirmwareStation(st.id, publish, boot_id=self.rng.getrandbits(31) | 1)
            self.stations[st.id] = fw
            self.actors[st.id] = Actor(self, st, fw)
            self._link_ok[st.id] = lambda: True

    def photograph(self, unit: Unit):
        """Foto sintética da placa; o defeito de solda da unidade, se houver, aparece nela."""
        from ..vision.board import render

        unit.shots += 1
        return render(unit.serial * 16 + unit.shots, "solda" in unit.defects)

    def next_serial(self) -> int:
        self._serial += 1
        return self._serial

    def set_link_source(self, station: str, fn: Callable[[], bool]) -> None:
        """Quem diz se o enlace MQTT da estação está de pé (o transporte ao vivo)."""
        self._link_ok[station] = fn

    def deliver(self, topic: str, payload: str) -> None:
        """Mensagem MQTT recebida. Fica numa caixa de entrada, como no ESP32, e é entregue no próximo passo."""
        self.inbox.append((topic, payload))

    def forward(self, st: Station, unit: Unit, now: int) -> None:
        if st.index == len(self.cfg.stations) - 1:
            self.finished.append(unit)
        else:
            self.actors[self.cfg.stations[st.index + 1].id].arrive(unit, now + self.transfer_ms)

    def temp_fault(self, station: str, now: int) -> float:
        d = self._drift.get(station)
        if not d:
            return 0.0
        start, end, rate = d
        if now >= end:
            del self._drift[station]
            return 0.0
        ramp_end = start + (end - start) * 0.5       # sobe na primeira metade, fica no patamar na segunda
        return rate * (min(now, ramp_end) - start) / 1000.0

    # -- falhas provocadas (demonstração e testes)
    def inject(self, fault: str, station: str | None, now: int, seconds: float = 30, factor: float = 2.5) -> str:
        ms = int(seconds * 1000)
        first_spc = next((s.id for s in self.cfg.stations if s.spc), None)
        if fault == "oven_drift":
            sid = station or first_spc
            if sid not in self.stations:
                return "estação sem sensor simulado"
            sigma = float(self.cfg.station(sid).spc["sigma"]) if self.cfg.station(sid).spc else 1.0
            self._drift[sid] = (now, now + ms, 6 * sigma / (seconds * 0.5))   # chega a +6σ
            return f"deriva de temperatura em {sid} por {seconds:g} s"
        if fault == "defect_burst":
            self.defect_factor, self._defect_until = factor * 2, now + ms
            return f"surto de defeitos (×{factor * 2:g}) por {seconds:g} s"
        actor = self.actors.get(station or "")
        if not isinstance(actor, Actor):
            return "estação inexistente ou real (não simulada)"
        if fault == "link_drop":
            actor.link_down_until = now + ms
            return f"{station} sem rede por {seconds:g} s"
        if fault == "slow":
            actor.slow_until, actor.slow_factor = now + ms, factor
            return f"{station} {factor:g}× mais lenta por {seconds:g} s"
        if fault == "call":
            actor.t_break = now
            return f"quebra em {station}"
        return f"falha desconhecida: {fault}"

    def link_dropped(self, station: str, now: int) -> bool:
        a = self.actors.get(station)
        return isinstance(a, Actor) and now < a.link_down_until

    def observe(self, topic: str, payload: str, now: int) -> None:
        """Evento de uma estação real (modo híbrido)."""
        parts = topic.split("/")
        if len(parts) == 5 and parts[3] == "evt" and parts[4] == "cycle":
            actor = self.actors.get(parts[2])
            if isinstance(actor, RemoteActor):
                try:
                    d = json.loads(payload)
                    actor.observed_cycle(str(d.get("unit", "")), bool(d.get("ok")), now)
                except (ValueError, TypeError):
                    return

    def step(self, now: int) -> None:
        while self.inbox:
            topic, payload = self.inbox.popleft()
            parts = topic.split("/")
            fw = self.stations.get(parts[2]) if len(parts) > 3 else None
            if fw:
                fw.on_message(topic, payload)
        if self._defect_until and now >= self._defect_until:
            self.defect_factor, self._defect_until = 1.0, 0
        first = self.actors[self.cfg.stations[0].id]
        while now >= self._next_arrival:
            if len(first.queue) < 3:                 # a placa nova só entra se houver espaço no alimentador
                first.queue.append(Unit(serial=self.next_serial()))
            self._next_arrival += self.arrival_ms
        for sid, actor in self.actors.items():
            fw = self.stations.get(sid)
            if fw is None:
                actor.step(now)
                continue
            fw.set_time(now)
            fw.set_link(self._link_ok[sid]() and not self.link_dropped(sid, now))
            actor.step(now)
            fw.loop()

    def close(self) -> None:
        for fw in self.stations.values():
            fw.close()
