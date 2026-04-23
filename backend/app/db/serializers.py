from datetime import date, datetime
from typing import Any

from bson import ObjectId


def serialize_doc(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_doc(item) for item in value]
    if isinstance(value, dict):
        serialized = {key: serialize_doc(item) for key, item in value.items()}
        if "_id" in serialized:
            serialized["id"] = serialized.pop("_id")
        return serialized
    return value


def serialize_many(values: list[dict]) -> list[dict]:
    return [serialize_doc(value) for value in values]


def to_object_id(value: str, field_name: str = "id") -> ObjectId:
    if not ObjectId.is_valid(value):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return ObjectId(value)
