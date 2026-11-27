"""AAS do produto e de cada unidade, no formato JSON do AAS v3 (publicados no BaSyx).

  produto (tipo)      Identificacao + ProcessoDeFabricacao: as etapas e a capacidade que cada uma pede.
                      É o "requisitante" da proposta do M1; os provedores são as estações (FA³ST).
  unidade (instância) Fabricacao: situação, pedido, passos por estação e inspeções. Existe desde que a unidade
                      é planejada, antes de ser fabricada.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import Config
from . import ids
from .ids import prop

STATUS = {"planned": "planejada", "wip": "em_producao", "rework": "retrabalho", "done": "pronta",
          "scrap": "refugada", "removed": "retirada"}


def iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collection(elements: list[dict]) -> dict:
    return {"modelType": "SubmodelElementCollection", "value": elements}


def _list(name: str, items: list[dict], description: str = "") -> dict:
    out = {"modelType": "SubmodelElementList", "idShort": name, "orderRelevant": True,
           "typeValueListElement": "SubmodelElementCollection", "value": items}
    if description:
        out["description"] = [{"language": "pt", "text": description}]
    return out


def _submodel(sm_id: str, name: str, elements: list[dict]) -> dict:
    return {"modelType": "Submodel", "id": sm_id, "idShort": name, "kind": "Instance", "submodelElements": elements}


def product_type(cfg: Config) -> tuple[dict, list[dict]]:
    """Shell do produto (tipo) e seus submodelos."""
    p = cfg.product
    pid = str(p["id"])
    ident = _submodel(ids.product_sm(pid, "identificacao"), "Identificacao", [
        prop("Codigo", pid), prop("Nome", p.get("name", pid)), prop("Descricao", p.get("description", "")),
        prop("Fabricante", p.get("manufacturer", "")), prop("TaktS", cfg.takt_s, "xs:double", "Ritmo do cliente, em segundos"),
    ])
    steps = [
        _collection([
            prop("Ordem", s.index + 1, "xs:int"),
            prop("Capacidade", s.skill, "xs:string", "Capacidade que a etapa pede"),
            prop("Estacao", s.id),
            prop("Provedor", ids.station_aas(s.id), "xs:string", "AAS da estação que oferece a capacidade (FA³ST)"),
            prop("CicloIdealS", s.ideal_cycle_s, "xs:double"),
            prop("AoReprovar", "retrabalho" if s.on_fail == "rework" else "refugo"),
        ])
        for s in cfg.stations
    ]
    process = _submodel(ids.product_sm(pid, "processo"), "ProcessoDeFabricacao", [
        _list("Etapas", steps, "Etapas na ordem da rota; cada uma pede uma capacidade a um provedor"),
        prop("MaximoDeTentativas", int(cfg.rules["max_attempts"]), "xs:int"),
    ])
    shell = {
        "modelType": "AssetAdministrationShell", "id": ids.product_aas(pid), "idShort": ids.id_short("Produto_" + pid),
        "description": [{"language": "pt", "text": p.get("name", pid)}],
        "assetInformation": {"assetKind": "Type", "globalAssetId": ids.product_asset(pid)},
        "submodels": [ids.ref(ident["id"]), ids.ref(process["id"])],
    }
    return shell, [ident, process]


def unit(cfg: Config, data: dict[str, Any], photo_base: str) -> tuple[dict, dict]:
    """Shell e submodelo Fabricacao de uma unidade. `data` é a saída de Engine.unit()."""
    u = data["unit"]
    uid, pid = u["id"], str(cfg.product["id"])
    names = {s.id: s for s in cfg.stations}
    planned = u["status"] == "planned"
    current = u["next_station"] if u["busy"] else ""
    elements = [
        prop("NumeroDeSerie", uid),
        prop("Produto", pid),
        prop("Status", STATUS.get(u["status"], u["status"]), "xs:string",
             "planejada, em_producao, retrabalho, pronta, refugada ou retirada"),
        prop("Pedido", u.get("order_id") or 0, "xs:int", "Pedido que planejou a unidade (0 = sem pedido)"),
        prop("EstacaoAtual", current, "xs:string", "Estação onde a unidade está em processo"),
        prop("ProximaEstacao", "" if u["busy"] else (u["next_station"] or ""), "xs:string", "Estação que a unidade aguarda"),
        prop("Reprovacoes", u["fails"], "xs:int"),
    ]
    for name, ts in (("PlanejadaEm", u.get("planned_ts")), ("IniciadaEm", None if planned else u["created_ts"]),
                     ("ConcluidaEm", u["finished_ts"])):
        if ts is not None:
            elements.append(prop(name, iso(ts), "xs:dateTime"))
    if u["status"] == "done" and u["finished_ts"]:
        elements.append(prop("LeadTimeS", round(u["finished_ts"] - u["created_ts"], 1), "xs:double"))

    steps = []
    for s in data["steps"]:
        st = names.get(s["station"])
        row = [prop("Estacao", s["station"]), prop("Capacidade", st.skill if st else ""), prop("Tentativa", s["attempt"], "xs:int"),
               prop("Inicio", iso(s["start_ts"]), "xs:dateTime"),
               prop("Resultado", "em_andamento" if s["end_ts"] is None else "aprovada" if s["ok"] else "reprovada")]
        if s["end_ts"] is not None:
            row += [prop("Fim", iso(s["end_ts"]), "xs:dateTime"), prop("DuracaoS", round(s["dur_ms"] / 1000, 2), "xs:double"),
                    prop("ModoDegradado", bool(s["degraded"]), "xs:boolean")]
        if s["temp"] is not None:
            row.append(prop("TemperaturaC", round(s["temp"], 1), "xs:double"))
        steps.append(_collection(row))
    elements.append(_list("Passos", steps, "Uma entrada por passagem em estação"))

    inspections = []
    for i in data.get("inspections", []):
        row = [prop("Quando", iso(i["ts"]), "xs:dateTime"), prop("Estacao", i["station"]),
               prop("Veredito", "sem_veredito" if i["ok"] is None else "aprovada" if i["ok"] else "reprovada"),
               prop("Defeito", i["defect"] or ""), prop("Modelo", i["model"] or ""),
               prop("Foto", f"{photo_base}/api/vision/photo/{i['image']}", "xs:anyURI")]
        if i["x"] is not None:
            row += [prop("PosicaoX", round(i["x"], 3), "xs:double"), prop("PosicaoY", round(i["y"], 3), "xs:double")]
        inspections.append(_collection(row))
    elements.append(_list("Inspecoes", inspections, "Inspeções ópticas por IA"))

    sm = _submodel(ids.unit_sm(uid, "fabricacao"), "Fabricacao", elements)
    shell = {
        "modelType": "AssetAdministrationShell", "id": ids.unit_aas(uid), "idShort": ids.id_short(uid),
        "derivedFrom": {"type": "ModelReference", "keys": [{"type": "AssetAdministrationShell", "value": ids.product_aas(pid)}]},
        "assetInformation": {"assetKind": "Instance", "globalAssetId": ids.unit_asset(uid), "assetType": ids.product_asset(pid)},
        "submodels": [ids.ref(sm["id"])],
    }
    return shell, sm
