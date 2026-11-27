"""Assistente da linha com IA local (Ollama).

O modelo só recebe um retrato compacto dos dados da linha e a pergunta; não executa ações.
Sem Ollama, a resposta vem do diagnóstico por regras (kpi.insights), e isso é dito ao usuário.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

SYSTEM = """Você é o assistente de uma linha de montagem de celulares, falando com o líder de produção.
Responda em português do Brasil, de forma direta e curta (no máximo 8 linhas, salvo se pedirem relatório).
Use SOMENTE os dados do bloco DADOS DA LINHA. Cite números com unidade. Se o dado não estiver lá, diga que não tem.
Não invente causas: quando sugerir uma causa, diga que é hipótese e qual dado a sustenta.
Quando fizer sentido, termine com uma ação concreta para o chão de fábrica.
Em "ocorrencias_no_turno" estão as contagens do turno por tipo; use-as em vez de contar linhas de "ultimos_eventos".
Glossário: FPY = aprovadas na primeira tentativa; RTY = produto dos FPY das estações; OEE = disponibilidade ×
desempenho × qualidade; takt = ritmo exigido pelo cliente; jidoka/retenção = estação segurada por alarme de processo;
ciclo degradado = feito sem liberação do servidor. Frações entre 0 e 1 devem ser ditas em porcentagem."""

REPORT = (
    "Escreva o relatório do turno em até 12 linhas: (1) resultado contra as metas de FPY, RTY e OEE; "
    "(2) gargalo e maiores perdas, com números; (3) ocorrências (alertas, chamados, bloqueios); "
    "(4) três ações recomendadas, em ordem de prioridade."
)


FRACTIONS = {"fpy", "rty", "oee", "availability", "performance", "quality", "utilization"}


def _fmt(key: str, v: Any) -> Any:
    """Frações viram texto em porcentagem: o modelo erra menos lendo "94.1%" do que 0.941."""
    if isinstance(v, float):
        return f"{v:.1%}" if key in FRACTIONS else round(v, 1)
    return v


def context(snap: dict[str, Any]) -> str:
    """Retrato compacto do estado da linha para o modelo."""
    line = snap["line"]
    data = {
        "linha": line["name"],
        "takt_s": line["takt_s"],
        "intertravamento": line["interlock"],
        "metas": {
            k: {"referencia": f"{t['baseline']:.0%}", "meta": f"{t['goal']:.0%}", "situacao": line["levels"][k]}
            for k, t in line["targets"].items()
        },
        "ocorrencias_no_turno": snap.get("counts", {}),
        "indicadores_da_linha": {k: _fmt(k, v) for k, v in line["kpi"].items() if k != "window_start"},
        "estacoes": [
            {
                "id": s["id"],
                "nome": s["name"],
                "estado": s["state"],
                "hardware": s["hw"] or None,
                "chamado_aberto": s["call"],
                "retida": s["hold"],
                "temperatura": s["temp"],
                "ciclo_ideal_s": s["ideal_cycle_s"],
                "unidades_esperando": s["kpi"]["waiting"],
                **{k: _fmt(k, v) for k, v in s["kpi"].items() if k != "waiting"},
            }
            for s in snap["stations"]
        ],
        "alertas_abertos": [a["message"] for a in snap["alerts"]],
        "diagnostico_por_regras": [i["text"] for i in snap["insights"]],
        "ultimos_eventos": [
            time.strftime("%H:%M:%S", time.localtime(e["ts"])) + " " + e["message"] for e in snap["log"][:20]
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def fallback(snap: dict[str, Any]) -> str:
    k = snap["line"]["kpi"]

    def pct(v):
        return "sem dado" if v is None else f"{v:.1%}"

    lines = [
        "(IA local indisponível: resposta do diagnóstico por regras.)",
        (f"FPY {pct(k['fpy'])} · RTY {pct(k['rty'])} · OEE {pct(k['oee'])} · "
        f"{k['done']} prontas, {k['scrap']} refugo, {k['wip']} em processo."),
    ]
    lines += ["• " + i["text"] for i in snap["insights"]]
    return "\n".join(lines)


class Assistant:
    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        self._checked, self._ok = 0.0, False

    async def available(self) -> bool:
        if time.monotonic() - self._checked > 15:
            self._checked = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=2) as c:
                    r = await c.get(f"{self.url}/api/tags")
                    names = [m.get("name", "") for m in r.json().get("models", [])]
                    self._ok = any(n == self.model or n.split(":")[0] == self.model for n in names)
            except (httpx.HTTPError, ValueError):
                self._ok = False
        return self._ok

    async def warmup(self) -> None:
        """Carrega o modelo na memória (a primeira carga leva de segundos a minutos)."""
        if await self.available():
            try:
                async with httpx.AsyncClient(timeout=300) as c:
                    await c.post(f"{self.url}/api/generate", json={"model": self.model, "keep_alive": "30m"})
            except httpx.HTTPError:
                self._ok, self._checked = False, time.monotonic()

    async def ask(self, question: str, snap: dict[str, Any]) -> AsyncIterator[str]:
        """Devolve a resposta em pedaços (para o painel mostrar enquanto o modelo escreve)."""
        if not await self.available():
            yield fallback(snap)
            return
        body = {
            "model": self.model,
            "stream": True,
            "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_ctx": 8192},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"DADOS DA LINHA:\n{context(snap)}\n\nPERGUNTA: {question}"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3)) as c:
                async with c.stream("POST", f"{self.url}/api/chat", json=body) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line:
                            continue
                        piece = json.loads(line).get("message", {}).get("content", "")
                        if piece:
                            yield piece
        except (httpx.HTTPError, ValueError) as e:
            self._ok, self._checked = False, time.monotonic()
            yield f"\n(Falha ao consultar a IA local: {e}.)\n" + fallback(snap)
