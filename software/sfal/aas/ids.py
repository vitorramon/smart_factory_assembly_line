"""Identificadores dos shells e submodelos (um lugar só, para servidor, gerador e testes concordarem)."""

import base64
import re

NS = "urn:sfal"


def id_short(text: str) -> str:
    """idShort do AAS: letras, dígitos e sublinhado, começando por letra."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", text)
    return s if s[:1].isalpha() else "x" + s


def b64(identifier: str) -> str:
    """Identificador codificado como a API do AAS pede nos caminhos (base64url sem preenchimento)."""
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


def ref(submodel_id: str) -> dict:
    return {"type": "ModelReference", "keys": [{"type": "Submodel", "value": submodel_id}]}


def prop(name: str, value, value_type: str = "xs:string", description: str = "") -> dict:
    p = {"modelType": "Property", "idShort": name, "valueType": value_type, "value": _text(value, value_type)}
    if description:
        p["description"] = [{"language": "pt", "text": description}]
    return p


def _text(value, value_type: str) -> str:
    if value is None:
        return {"xs:string": "", "xs:boolean": "false", "xs:dateTime": "1970-01-01T00:00:00Z"}.get(value_type, "0")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# estações e linha (FA³ST)
station_aas = lambda sid: f"{NS}:aas:station:{sid}"                 # noqa: E731
station_asset = lambda sid: f"{NS}:asset:station:{sid}"             # noqa: E731
station_sm = lambda sid, name: f"{NS}:sm:station:{sid}:{name}"      # noqa: E731
LINE_AAS, LINE_ASSET = f"{NS}:aas:line", f"{NS}:asset:line"
line_sm = lambda name: f"{NS}:sm:line:{name}"                        # noqa: E731

# produto e unidades (BaSyx)
product_aas = lambda pid: f"{NS}:aas:product:{pid}"                 # noqa: E731
product_asset = lambda pid: f"{NS}:asset:product:{pid}"             # noqa: E731
product_sm = lambda pid, name: f"{NS}:sm:product:{pid}:{name}"      # noqa: E731
unit_aas = lambda uid: f"{NS}:aas:unit:{uid}"                       # noqa: E731
unit_asset = lambda uid: f"{NS}:asset:unit:{uid}"                   # noqa: E731
unit_sm = lambda uid, name: f"{NS}:sm:unit:{uid}:{name}"            # noqa: E731
