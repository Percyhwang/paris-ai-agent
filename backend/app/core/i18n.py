def normalize_language(value: str | None, default: str = "ko") -> str:
    if not value:
        return default

    lowered = value.strip().lower()
    if lowered.startswith("en"):
        return "en"
    if lowered.startswith("ko"):
        return "ko"
    return default
