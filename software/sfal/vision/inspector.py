"""Inspetor óptico: manda a foto da placa a um modelo de visão (Ollama) e devolve aprovada/reprovada.

O modelo recebe a foto e uma descrição do que é uma junta boa e de quais defeitos procurar; responde em JSON.
Qualquer falha (Ollama fora do ar, resposta inválida, tempo esgotado) vira `Verdict(ok=None)`: quem chama decide
o que fazer sem veredito. O inspetor nunca "aprova por omissão".
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import asdict, dataclass

import httpx

PROMPT = """You are an automated optical inspection (AOI) system for a phone PCB after reflow soldering.
The photo shows one board: a black IC in the middle with a row of solder joints above it and a row below it,
and several small two-terminal components (R1, R2, ...) each with one solder joint on its left and one on its right.

A GOOD solder joint is a small, separate, shiny silver-white rectangle. All good joints look alike.

Look for exactly these solder defects:
- "ponte": a solder BRIDGE - silver solder joining two neighbouring IC joints into one wide blob (they must be separate).
- "ausente": MISSING solder - one pad is dull brown/orange copper instead of shiny silver-white.
- "excesso": EXCESS solder - one large round silver ball, much bigger than the other joints.

Inspect every joint. If every joint is a separate, shiny, normal-sized rectangle, the board is OK.
Answer with JSON only: {"veredito": "OK" or "NOK", "defeito": "nenhum" | "ponte" | "ausente" | "excesso", "local": "<short description in Portuguese of where, or empty>"}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "veredito": {"type": "string", "enum": ["OK", "NOK"]},
        "defeito": {"type": "string", "enum": ["nenhum", "ponte", "ausente", "excesso"]},
        "local": {"type": "string"},
    },
    "required": ["veredito", "defeito", "local"],
}


@dataclass
class Verdict:
    ok: bool | None           # True aprovada, False reprovada, None sem veredito
    defect: str = ""
    where: str = ""
    model: str = ""
    latency_ms: int = 0
    error: str = ""
    score: float | None = None      # nota do defeito mais provável (só no classificador)
    x: float | None = None          # posição do defeito na foto, de 0 a 1 (só no classificador)
    y: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _body(model: str, jpeg: bytes) -> dict:
    return {
        "model": model,
        "stream": False,
        "keep_alive": "30m",
        "format": SCHEMA,
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(jpeg).decode()]}],
    }


def _parse(model: str, data: dict, t0: float) -> Verdict:
    ms = int((time.monotonic() - t0) * 1000)
    try:
        out = json.loads(data["message"]["content"])
        ok = out["veredito"] == "OK"
        defect = "" if ok else str(out.get("defeito", ""))
        return Verdict(ok, defect, "" if ok else str(out.get("local", ""))[:120], model, ms)
    except (KeyError, TypeError, ValueError) as e:
        return Verdict(None, model=model, latency_ms=ms, error=f"resposta inválida do modelo: {e}")


def inspect(url: str, model: str, jpeg: bytes, timeout: float = 30.0) -> Verdict:
    t0 = time.monotonic()
    try:
        r = httpx.post(f"{url.rstrip('/')}/api/chat", json=_body(model, jpeg), timeout=httpx.Timeout(timeout, connect=3))
        r.raise_for_status()
        return _parse(model, r.json(), t0)
    except httpx.HTTPError as e:
        return Verdict(None, model=model, latency_ms=int((time.monotonic() - t0) * 1000), error=f"{type(e).__name__}: {e}")


async def inspect_async(url: str, model: str, jpeg: bytes, timeout: float = 30.0) -> Verdict:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=3)) as c:
            r = await c.post(f"{url.rstrip('/')}/api/chat", json=_body(model, jpeg))
            r.raise_for_status()
            return _parse(model, r.json(), t0)
    except httpx.HTTPError as e:
        return Verdict(None, model=model, latency_ms=int((time.monotonic() - t0) * 1000), error=f"{type(e).__name__}: {e}")
