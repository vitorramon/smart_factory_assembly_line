"""Sincronizador do BaSyx: publica o produto e mantém o shell de cada unidade igual ao que o motor sabe.

Roda numa thread do servidor. O motor só anota quais unidades mudaram (`dirty_units`); aqui cada uma é lida,
convertida em AAS e gravada por HTTP. BaSyx fora do ar: as unidades continuam na fila e a linha segue.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from . import ids, product

log = logging.getLogger("sfal.aas")
BATCH = 40


class BasyxSync:
    def __init__(self, engine, url: str, photo_base: str):
        self.engine, self.url, self.photo_base = engine, url.rstrip("/"), photo_base.rstrip("/")
        self.known: set[str] = set()         # shells de unidade já criados nesta execução
        self.synced = 0
        self.error = ""
        self.ready = False
        self._stop = threading.Event()
        self._http = httpx.Client(timeout=10)

    # ---- HTTP
    def _upsert(self, kind: str, body: dict[str, Any]) -> None:
        """Cria ou substitui um shell ('shells') ou submodelo ('submodels')."""
        r = self._http.put(f"{self.url}/{kind}/{ids.b64(body['id'])}", json=body)
        if r.status_code == 404:
            r = self._http.post(f"{self.url}/{kind}", json=body)
        if r.status_code >= 300 and r.status_code != 409:
            raise httpx.HTTPError(f"{kind} {body['id']}: HTTP {r.status_code} {r.text[:200]}")

    def _bootstrap(self) -> None:
        shell, submodels = product.product_type(self.engine.cfg)
        for sm in submodels:
            self._upsert("submodels", sm)
        self._upsert("shells", shell)
        with self.engine.lock:      # depois de um reinício (BaSyx em memória), reenvia o que importa
            rows = self.engine.db.execute(
                "SELECT id FROM units WHERE status IN ('planned','wip','rework') "
                "UNION SELECT id FROM (SELECT id FROM units WHERE finished_ts IS NOT NULL ORDER BY finished_ts DESC LIMIT 150)")
            self.engine.dirty_units.update(r["id"] for r in rows)
        self.ready = True
        log.info("BaSyx: produto %s publicado em %s", self.engine.cfg.product["id"], self.url)

    def _push(self, uid: str) -> None:
        data = self.engine.unit(uid)
        if data is None:
            return
        shell, sm = product.unit(self.engine.cfg, data, self.photo_base)
        self._upsert("submodels", sm)
        if uid not in self.known:
            self._upsert("shells", shell)
            self.known.add(uid)
        self.synced += 1

    # ---- laço
    def step(self) -> int:
        """Uma rodada. Devolve quantas unidades foram enviadas."""
        if not self.ready:
            self._bootstrap()
        with self.engine.lock:
            batch = [self.engine.dirty_units.pop() for _ in range(min(BATCH, len(self.engine.dirty_units)))]
        for n, uid in enumerate(batch):
            try:
                self._push(uid)
            except httpx.HTTPError:
                with self.engine.lock:
                    self.engine.dirty_units.update(batch[n:])     # devolve o que faltou
                raise
        return len(batch)

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                sent = self.step()
                self.error = ""
                self._stop.wait(0.2 if sent == BATCH else 1.0)
            except httpx.HTTPError as e:
                if not self.error:
                    log.warning("BaSyx indisponível (%s); tentando de novo", e)
                self.error, self.ready = str(e)[:160], False
                self.known.clear()
                self._stop.wait(5.0)

    def start(self) -> None:
        threading.Thread(target=self.run, daemon=True, name="aas-sync").start()

    def stop(self) -> None:
        self._stop.set()

    def info(self) -> dict[str, Any]:
        return {"enabled": True, "ok": self.ready and not self.error, "synced": self.synced,
                "pending": len(self.engine.dirty_units), "error": self.error}
