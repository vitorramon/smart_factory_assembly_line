"""Servidor da linha: liga o motor ao broker MQTT e expõe o painel, a API e o WebSocket."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import mqtt as bus
from . import sintese
from .assistant import REPORT, Assistant
from .config import load
from .engine import Engine
from .m2 import service as m2
from .paths import DATA_DIR, WEB_DIR
from .sim import whatif
from .store import open_db
from .vision.service import DEFECT_LABEL, VisionService

log = logging.getLogger("sfal.api")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=600)


class Inject(BaseModel):
    fault: str
    station: str | None = None
    seconds: float = Field(default=30, ge=1, le=600)
    factor: float = Field(default=2.5, ge=1, le=10)


class Photo(BaseModel):
    station: str
    unit: str = Field(min_length=1, max_length=31)
    image_b64: str = Field(min_length=100, max_length=8_000_000)
    truth: dict | None = None      # gabarito opcional: {"defect": bool, "kind": "ponte"}


class WhatIf(BaseModel):
    scenarios: list[str] = Field(min_length=1, max_length=6)
    hours: float = Field(default=2, gt=0, le=12)
    seed: int | None = None


def create_app() -> FastAPI:
    cfg = load()
    db = open_db(os.environ.get("SFAL_DB", DATA_DIR / "sfal.db"))
    state: dict = {"client": None, "snapshot": None}

    def publish(topic: str, payload: str, qos: int, retain: bool) -> bool:
        return bus.publish(state["client"], topic, payload, qos, retain) if state["client"] else False

    engine = Engine(cfg, db, publish)
    assistant = Assistant(cfg.assistant["url"], cfg.assistant["model"])
    vision = VisionService(cfg.vision, cfg.assistant["url"])
    photos = Path(os.environ.get("SFAL_DATA_DIR", DATA_DIR)) / "inspections"
    photos.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    sockets: set[WebSocket] = set()

    def on_connect(client):
        client.subscribe("sfal/v1/#", qos=1)
        state["client"] = client
        engine.start(time.time())

    def ticker():
        while not stop.wait(1.0):
            try:
                engine.tick(time.time())
            except Exception:
                log.exception("erro no tick do motor")

    async def broadcaster():
        while True:
            snap = await asyncio.to_thread(engine.snapshot, time.time())
            snap["broker"] = bool(state["client"] and state["client"].is_connected())
            snap["assistant"] = {"available": await assistant.available(), "model": assistant.model}
            snap["vision"] = {**vision.info(), **snap["vision"]}
            snap["scenarios"] = {k: v.get("label", k) for k, v in cfg.scenarios.items()}
            state["snapshot"] = snap
            text = json.dumps(snap, ensure_ascii=False)
            for ws in list(sockets):
                try:
                    await ws.send_text(text)
                except (WebSocketDisconnect, RuntimeError):
                    sockets.discard(ws)
            await asyncio.sleep(1.0)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        client = bus.make_client("sfal-server", on_connect, lambda t, p: engine.handle(t, p, time.time()))
        state["client"] = client
        threading.Thread(target=ticker, daemon=True, name="tick").start()
        task = asyncio.create_task(broadcaster())
        warm = asyncio.create_task(assistant.warmup())
        yield
        task.cancel()
        warm.cancel()
        stop.set()
        client.loop_stop()
        client.disconnect()

    app = FastAPI(title="Smart Factory Assembly Line", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=20_000)

    def snapshot() -> dict:
        return state["snapshot"] or engine.snapshot(time.time())

    @app.get("/api/health")
    def health():
        ok = bool(state["client"] and state["client"].is_connected())
        if not ok:
            raise HTTPException(503, "sem conexão com o broker MQTT")
        return {"ok": True}

    @app.get("/api/snapshot")
    def get_snapshot():
        return snapshot()

    @app.get("/api/units")
    def units(limit: int = 30, status: str | None = None):
        return engine.units(min(max(limit, 1), 500), status)

    @app.get("/api/units/{uid}")
    def unit(uid: str):
        u = engine.unit(uid.strip())
        if not u:
            raise HTTPException(404, "unidade não encontrada")
        return u

    # ---- M1 (diagnóstico), M2 (simulação) e síntese
    @app.get("/api/m1")
    def get_m1():
        return sintese.load_m1()

    @app.get("/api/m2/scenarios")
    def m2_scenarios():
        return m2.scenarios()

    @app.get("/api/m2/run")
    async def m2_run(scenario: str = "atual", hours: float = 8.0, seed: int = 7):
        if scenario not in {s["id"] for s in m2.scenarios()}:
            raise HTTPException(400, f"cenário desconhecido: {scenario}")
        if not 0 < hours <= 12:
            raise HTTPException(400, "turno deve ter entre 0 e 12 horas")
        return await asyncio.to_thread(m2.run, scenario, float(hours), int(seed))

    @app.get("/api/sintese")
    async def get_sintese():
        return await asyncio.to_thread(sintese.build, engine, time.time())

    @app.post("/api/shift")
    def new_shift():
        engine.new_shift(time.time())
        return {"ok": True}

    @app.post("/api/assistant")
    async def ask(q: Question):
        return StreamingResponse(assistant.ask(q.question, snapshot()), media_type="text/plain; charset=utf-8")

    @app.post("/api/assistant/report")
    async def report():
        return StreamingResponse(assistant.ask(REPORT, snapshot()), media_type="text/plain; charset=utf-8")

    # ---- inspeção óptica: a câmera (ou o simulador) envia a foto; o servidor classifica e avisa a estação
    @app.post("/api/vision/inspect")
    async def vision_inspect(photo: Photo):
        if not vision.enabled or photo.station != vision.station:
            raise HTTPException(409, vision.error or f"a estação {photo.station} não tem inspeção automática configurada")
        try:
            jpeg = base64.b64decode(photo.image_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "image_b64 inválido") from None
        verdict = await vision.inspect(jpeg)
        name = f"{int(time.time() * 1000)}-{''.join(c for c in photo.unit if c.isalnum() or c == '-')}.jpg"
        await asyncio.to_thread((photos / name).write_bytes, jpeg)
        old = sorted(photos.glob("*.jpg"))[:-400]          # guarda as 400 fotos mais recentes
        for f in old:
            f.unlink(missing_ok=True)
        v = verdict.as_dict()
        if v["ok"] is False and not v["where"]:
            v["where"] = DEFECT_LABEL.get(v["defect"], v["defect"])
        v["id"] = engine.record_inspection(photo.station, photo.unit, v, photo.truth, name, time.time())
        return v

    @app.get("/api/vision/photo/{name}")
    def vision_photo(name: str):
        path = photos / Path(name).name
        if not path.is_file():
            raise HTTPException(404, "foto não encontrada (as mais antigas são apagadas)")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/sim/inject")
    def inject(cmd: Inject):
        if not engine.sim_status:
            raise HTTPException(409, "o simulador não está no ar")
        if not publish("sfal/v1/sim/cmd", cmd.model_dump_json(), 1, False):
            raise HTTPException(503, "sem conexão com o broker MQTT")
        return {"ok": True}

    @app.post("/api/whatif")
    async def run_whatif(req: WhatIf):
        unknown = [s for s in req.scenarios if s not in cfg.scenarios]
        if unknown:
            raise HTTPException(400, f"cenário desconhecido: {', '.join(unknown)}")
        return await asyncio.to_thread(whatif.compare, cfg, req.scenarios, req.hours, req.seed)

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        sockets.add(sock)
        try:
            if state["snapshot"]:
                await sock.send_text(json.dumps(state["snapshot"], ensure_ascii=False))
            while True:
                await sock.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            sockets.discard(sock)

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app
