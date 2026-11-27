"""Gera o modelo AAS e a configuração do FA³ST Service a partir de config/line.yaml.

Um shell por estação (o provedor de uma capacidade) e um para a linha. O FA³ST assina os tópicos do gêmeo no
broker MQTT e atualiza as propriedades; clientes OPC UA (e HTTP) leem e assinam a partir dele.

    sfal aas-config --out <pasta>     grava model.json e config.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..config import Config
from . import ids, twin

P = "de.fraunhofer.iosb.ilt.faaast.service."


def _submodel(sm_id: str, name: str, elements: list[dict]) -> dict[str, Any]:
    return {"modelType": "Submodel", "id": sm_id, "idShort": name, "kind": "Instance", "submodelElements": elements}


def _shell(aas_id: str, short: str, asset_id: str, kind: str, submodel_ids: list[str], description: str) -> dict[str, Any]:
    return {
        "modelType": "AssetAdministrationShell", "id": aas_id, "idShort": short,
        "description": [{"language": "pt", "text": description}],
        "assetInformation": {"assetKind": kind, "globalAssetId": asset_id},
        "submodels": [ids.ref(s) for s in submodel_ids],
    }


def model(cfg: Config) -> dict[str, Any]:
    shells, submodels = [], []
    for st in cfg.stations:
        sms = []
        for name in ("Estado", "Indicadores"):
            sm_id = ids.station_sm(st.id, name.lower())
            submodels.append(_submodel(sm_id, f"{name}_{ids.id_short(st.id)}", [
                ids.prop(short, None, vtype, desc) for sub, short, _, vtype, desc in twin.STATION_FIELDS if sub == name]))
            sms.append(sm_id)
        cap_id = ids.station_sm(st.id, "capacidade")
        submodels.append(_submodel(cap_id, f"Capacidade_{ids.id_short(st.id)}", [ids.prop(n, v, t) for n, v, t in twin.capabilities(st, cfg)]))
        shells.append(_shell(ids.station_aas(st.id), ids.id_short("Estacao_" + st.id), ids.station_asset(st.id), "Instance",
                             [*sms, cap_id], f"{st.name}: provedor da capacidade “{st.skill}”"))
    line_id = ids.line_sm("indicadores")
    submodels.append(_submodel(line_id, "Indicadores_linha", [ids.prop(short, None, vtype, desc) for _, short, _, vtype, desc in twin.LINE_FIELDS]))
    shells.append(_shell(ids.LINE_AAS, "Linha", ids.LINE_ASSET, "Instance", [line_id], cfg.name))
    return {"assetAdministrationShells": shells, "submodels": submodels, "conceptDescriptions": []}


def config(cfg: Config, mqtt_uri: str, opcua_port: int = 4840, http_port: int = 8443, model_file: str = "model.json") -> dict[str, Any]:
    subs: dict[str, dict[str, str]] = {}
    for st in cfg.stations:
        for sub, short, key, _, _ in twin.STATION_FIELDS:
            subs[f"(Submodel){ids.station_sm(st.id, sub.lower())}, (Property){short}"] = {
                "format": "JSON", "topic": twin.TOPIC_STATION.format(id=st.id, group=twin.group_of(sub, key)), "query": f"$.{key}"}
    for _, short, key, _, _ in twin.LINE_FIELDS:
        subs[f"(Submodel){ids.line_sm('indicadores')}, (Property){short}"] = {"format": "JSON", "topic": twin.TOPIC_LINE.format(group="indicadores"), "query": f"$.{key}"}
    conn: dict[str, Any] = {"@class": P + "assetconnection.mqtt.MqttAssetConnection", "serverUri": mqtt_uri,
                            # sem clientId: o FA³ST gera um por conexão. Com um fixo, as conexões que ele abre na partida
                            # derrubavam umas às outras no broker e as assinaturas não eram refeitas.
                            "subscriptionProviders": subs}
    if os.environ.get("SFAL_MQTT_USER"):
        conn["username"], conn["password"] = os.environ["SFAL_MQTT_USER"], os.environ.get("SFAL_MQTT_PASS", "")
    return {
        "core": {"requestHandlerThreadPoolSize": 2},
        "endpoints": [
            # OPC UA sem segurança e com acesso anônimo: só para rede isolada (docs/AAS.md)
            {"@class": P + "endpoint.opcua.OpcUaEndpoint", "tcpPort": opcua_port,
             "supportedSecurityPolicies": ["NONE"], "supportedAuthentications": ["Anonymous"]},
            {"@class": P + "endpoint.http.HttpEndpoint", "port": http_port, "sslEnabled": False, "corsEnabled": True,
             "profiles": ["AAS_REPOSITORY_READ", "AAS_READ", "SUBMODEL_REPOSITORY_READ", "SUBMODEL_READ", "SUBMODEL_VALUE"]},
        ],
        "persistence": {"@class": P + "persistence.memory.PersistenceInMemory", "initialModelFile": model_file},
        "messageBus": {"@class": P + "messagebus.internal.MessageBusInternal"},
        "assetConnections": [conn],
    }


def write(cfg: Config, out: Path, mqtt_uri: str, model_dir: str | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(model(cfg), ensure_ascii=False, indent=1), encoding="utf-8")
    model_file = f"{model_dir.rstrip('/')}/model.json" if model_dir else str(out / "model.json")
    (out / "config.json").write_text(json.dumps(config(cfg, mqtt_uri, model_file=model_file), ensure_ascii=False, indent=1), encoding="utf-8")
