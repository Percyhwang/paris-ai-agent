from typing import Any, Dict


def _normalize_modify_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(raw)
    if not isinstance(data.get("operations"), list):
        if isinstance(data.get("operations"), dict):
            data["operations"] = [data["operations"]]
        else:
            data["operations"] = []
    if not isinstance(data.get("clarify"), dict):
        data["clarify"] = {}
    clarify = data["clarify"]
    if not isinstance(clarify.get("missing_fields"), list):
        clarify["missing_fields"] = []
    data["clarify"] = clarify
    return data
