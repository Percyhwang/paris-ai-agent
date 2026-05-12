from typing import Any, Dict


def _normalize_llm_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(raw)

    for key in [
        "dates",
        "party",
        "lodging",
        "mobility",
        "pace",
        "budget",
        "preferences",
        "constraints",
        "output",
        "clarify",
        "destination",
    ]:
        if key not in data or not isinstance(data.get(key), dict):
            data[key] = {}

    prefs = data.get("preferences", {})
    if not isinstance(prefs.get("weights"), dict):
        prefs["weights"] = {}
    for arr_key in ("themes", "must_include", "must_avoid"):
        value = prefs.get(arr_key)
        if value is None:
            prefs[arr_key] = []
        elif isinstance(value, str):
            prefs[arr_key] = [value]
        elif not isinstance(value, list):
            prefs[arr_key] = []
    data["preferences"] = prefs

    clarify = data.get("clarify", {})
    if not isinstance(clarify.get("missing_fields"), list):
        clarify["missing_fields"] = []
    data["clarify"] = clarify

    return data
