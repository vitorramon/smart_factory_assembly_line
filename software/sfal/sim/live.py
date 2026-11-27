"""Simulador ao vivo: a planta simulada em tempo real, falando MQTT com o broker de verdade.

Cada estação simulada tem a própria conexão MQTT (com Last Will), como uma placa. Para o servidor
não há diferença entre isto e um ESP32, a não ser o campo `hw` do status ("sim" × "esp32").

Modo híbrido: `--real asm` deixa a estação `asm` para uma placa de verdade; a planta acompanha os
eventos dela para continuar movendo as unidades pelas outras estações.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .. import mqtt as bus
from ..config import Config
from .plant import Plant

log = logging.getLogger("sfal.sim")
STEP_MS = 20
SIM_STATUS = "sfal/v1/sim/status"
SIM_CMD = "sfal/v1/sim/cmd"
FAULTS = {
    "oven_drift": "Deriva de temperatura do forno",
    "defect_burst": "Surto de defeitos",
    "link_drop": "Queda de rede da estação",
    "slow": "Operador lento",
    "call": "Quebra / chamado",
}


def run(cfg: Config, real: tuple[str, ...] = (), stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    clients: dict[str, object] = {}
    commands: list[dict] = []
    observed: list[tuple[str, str]] = []
    plant_box: list[Plant] = []

    def station_publish(topic: str, payload: str, qos: int, retain: bool) -> bool:
        sid = topic.split("/")[2]
        return bus.publish(clients[sid], topic, payload, qos, retain)

    plant = Plant(cfg, station_publish, real=real, dt=STEP_MS)
    plant_box.append(plant)

    # Câmera da inspeção óptica: envia a foto ao servidor e recebe o veredito do modelo.
    backend = os.environ.get("SFAL_BACKEND_URL", "http://localhost:8000").rstrip("/")
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="camera")

    def shoot(station: str, unit: str, jpeg: bytes, truth: dict) -> dict:
        body = {"station": station, "unit": unit, "image_b64": base64.b64encode(jpeg).decode(), "truth": truth}
        try:
            r = httpx.post(f"{backend}/api/vision/inspect", json=body, timeout=float(cfg.vision.get("timeout_s", 15)))
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("inspeção óptica sem veredito para %s: %s", unit, e)
            return {"ok": None, "error": str(e)}

    if plant.vision_station in plant.stations:
        plant.camera = lambda *a: pool.submit(shoot, *a)
        log.info("inspeção óptica por IA em %s (fotos para %s)", plant.vision_station, backend)

    for sid, fw in plant.stations.items():
        def on_connect(client, fw=fw):
            client.subscribe(fw.command_filter, qos=1)

        clients[sid] = bus.make_client(f"sfal-sim-{sid}", on_connect, plant.deliver, will=fw.will)
        plant.set_link_source(sid, clients[sid].is_connected)

    session = int(time.time() * 1000)   # identifica esta execução: o servidor descarta as unidades da anterior

    def status(online: bool = True) -> str:
        return json.dumps(
            {"online": online, "session": session, "stations": sorted(plant.stations), "real": sorted(real),
             "faults": FAULTS}
        )

    def on_ctrl_connect(client):
        client.subscribe(SIM_CMD, qos=1)
        for sid in real:
            client.subscribe(f"sfal/v1/{sid}/evt/cycle", qos=1)
        client.publish(SIM_STATUS, status(), qos=1, retain=True)

    def on_ctrl_message(topic: str, payload: str):
        if topic == SIM_CMD:
            try:
                commands.append(json.loads(payload))
            except ValueError:
                log.warning("comando inválido: %s", payload)
        else:
            observed.append((topic, payload))

    ctrl = bus.make_client("sfal-sim", on_ctrl_connect, on_ctrl_message, will=(SIM_STATUS, '{"online":false}'))

    log.info("simulando %s%s", ", ".join(plant.stations), f" (placas reais: {', '.join(real)})" if real else "")
    t0 = time.monotonic()
    dropped: set[str] = set()
    try:
        while not stop.is_set():
            now = int((time.monotonic() - t0) * 1000)
            while commands:
                c = commands.pop(0)
                msg = plant.inject(
                    str(c.get("fault", "")), c.get("station"), now,
                    seconds=float(c.get("seconds", 30)), factor=float(c.get("factor", 2.5)),
                )
                log.info("falha provocada: %s", msg)
            while observed:
                plant.observe(*observed.pop(0), now)
            # queda de rede provocada: publica o que o broker publicaria (Last Will) ao perder a placa
            for sid, fw in plant.stations.items():
                down = plant.link_dropped(sid, now)
                if down and sid not in dropped:
                    dropped.add(sid)
                    bus.publish(clients[sid], fw.will[0], fw.will[1], 1, True)
                elif not down:
                    dropped.discard(sid)
            plant.step(now)
            time.sleep(max(0.0, (now + STEP_MS) / 1000.0 - (time.monotonic() - t0)))
    finally:
        ctrl.publish(SIM_STATUS, '{"online":false}', qos=1, retain=True)
        for sid, fw in plant.stations.items():
            clients[sid].publish(fw.will[0], fw.will[1], qos=1, retain=True)
        time.sleep(0.3)
        for c in [ctrl, *clients.values()]:
            c.loop_stop()
            c.disconnect()
        pool.shutdown(wait=False, cancel_futures=True)
        plant.close()
