from typing import Any


def api_ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "data": data, "message": message, "error": None}


def api_error(
    message: str,
    code: str = "ERROR",
    details: Any = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "message": message,
        "error": {"code": code, "details": details},
    }
