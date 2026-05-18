import re

from parser_api.parsers.common.constants import KNOWN_PLACE_TOKENS
from parser_api.parsers.create_plan.constants import THEME_TOKEN_MAP

PLACE_ALIASES: dict[str, tuple[str, ...]] = {
    "에펠탑": ("에펠탑", "에펠"),
    "루브르": ("루브르", "루브르박물관"),
    "오르세": ("오르세", "오르세미술관"),
    "개선문": ("개선문",),
    "샹젤리제": ("샹젤리제",),
    "몽마르트르": ("몽마르트르", "몽마르트", "사크레쾨르", "사크레쾨르성당"),
    "마레": ("마레", "마레지구"),
    "센강": ("센강", "세느강"),
    "노트르담": ("노트르담",),
    "생트샤펠": ("생트샤펠", "생트샤펠성당"),
    "튈르리": ("튈르리", "튈르리정원"),
    "뤽상부르": ("뤽상부르", "뤽상부르공원", "룩셈부르크", "룩셈부르크공원"),
    "오페라 가르니에": ("오페라가르니에", "오페라", "가르니에", "팔레가르니에", "palaisgarnier", "operagarnier", "opera"),
    "팔레 루아얄": ("팔레루아얄", "팔레 루아얄", "palaisroyal", "palais-royal"),
    "재즈바": ("재즈바", "재즈", "위셰트"),
    "베르사유": ("베르사유",),
}

INCLUDE_CUES = ("꼭", "반드시", "무조건", "넣고싶", "넣어줘", "넣고", "넣", "포함", "가고싶", "보고싶", "핵심", "보고", "방문", "산책", "마무리", "시작")
AVOID_CUES = ("빼줘", "빼고", "제외", "싫어", "피하고싶", "안가고싶", "가지않", "말고", "없는", "없이", "넣지", "빼고싶")


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _extract_place_preferences(message: str) -> tuple[list[str], list[str]]:
    text = _compact(message)
    must_include: list[str] = []
    must_avoid: list[str] = []

    for canonical, aliases in PLACE_ALIASES.items():
        aliases = tuple(dict.fromkeys([*aliases, *[place for place in KNOWN_PLACE_TOKENS if place == canonical]]))
        if not any(alias in text for alias in aliases):
            continue

        if any(_avoid_cue_after_alias(text, alias, window=8) and not _photo_marker_near_alias(text, alias) for alias in aliases):
            must_avoid.append(canonical)
            continue

        if any(_photo_marker_near_alias(text, alias) for alias in aliases):
            must_include.append(canonical)
            continue

        if any(_only_marker_after_alias(text, alias) for alias in aliases):
            must_include.append(canonical)
            continue

        if any(_cue_after_alias(text, alias, INCLUDE_CUES, window=28) for alias in aliases):
            must_include.append(canonical)
            continue

        for segment in re.split(r"[.!?\n。！？]+", message):
            segment_text = _compact(segment)
            if not any(alias in segment_text for alias in aliases):
                continue
            alias_index = min((segment_text.find(alias) for alias in aliases if alias in segment_text), default=-1)
            include_index = _first_index_after(segment_text, INCLUDE_CUES, alias_index)
            avoid_index = _first_index_after(segment_text, AVOID_CUES, alias_index)
            if (
                alias_index >= 0
                and avoid_index >= 0
                and avoid_index - alias_index <= 18
                and not (include_index >= 0 and include_index < avoid_index)
            ):
                must_avoid.append(canonical)
                break
            if include_index < 0:
                continue
            if alias_index >= 0 and (avoid_index < 0 or include_index < avoid_index):
                must_include.append(canonical)
                break

    avoid_aliases = {
        alias
        for avoided in must_avoid
        for alias in PLACE_ALIASES.get(avoided, (avoided,))
    }
    filtered_include = [place for place in must_include if place not in must_avoid and place not in avoid_aliases]
    return list(dict.fromkeys(filtered_include)), list(dict.fromkeys(must_avoid))


def _cue_after_alias(text: str, alias: str, cues: tuple[str, ...], *, window: int) -> bool:
    index = text.find(alias)
    if index < 0:
        return False
    after = text[index + len(alias) : index + len(alias) + window]
    next_alias_positions = [
        after.find(other_alias)
        for aliases in PLACE_ALIASES.values()
        for other_alias in aliases
        if other_alias and other_alias in after
    ]
    if next_alias_positions:
        after = after[: min(next_alias_positions)]
    return any(cue in after for cue in cues)


def _avoid_cue_after_alias(text: str, alias: str, *, window: int) -> bool:
    index = text.find(alias)
    if index < 0:
        return False
    after = text[index + len(alias) : index + len(alias) + window]
    next_alias_positions = [
        after.find(other_alias)
        for aliases in PLACE_ALIASES.values()
        for other_alias in aliases
        if other_alias and other_alias in after
    ]
    if next_alias_positions:
        after = after[: min(next_alias_positions)]
    avoid_positions = [after.find(cue) for cue in AVOID_CUES if cue in after]
    if not avoid_positions:
        return False
    avoid_index = min(avoid_positions)
    include_positions = [after.find(cue) for cue in INCLUDE_CUES if cue in after]
    return not include_positions or min(include_positions) > avoid_index


def _only_marker_after_alias(text: str, alias: str) -> bool:
    index = text.find(alias)
    if index < 0:
        return False
    return text[index + len(alias) : index + len(alias) + 2].startswith("만")


def _photo_marker_near_alias(text: str, alias: str) -> bool:
    index = text.find(alias)
    if index < 0:
        return False
    window = text[max(0, index - 4) : index + len(alias) + 14]
    return any(token in window for token in ("사진만", "사진찍", "사진", "포토", "photo", "외관만"))


def _first_index(text: str, cues: tuple[str, ...]) -> int:
    indices = [text.find(cue) for cue in cues if cue in text]
    return min(indices) if indices else -1


def _first_index_after(text: str, cues: tuple[str, ...], alias_index: int) -> int:
    if alias_index < 0:
        return -1
    indices = [index for cue in cues if (index := text.find(cue, alias_index)) >= 0]
    return min(indices) if indices else -1


def _extract_themes(message: str) -> list[str]:
    compact = message.replace(" ", "")
    themes: list[str] = []

    for theme, tokens in THEME_TOKEN_MAP.items():
        if any(token in compact for token in tokens):
            themes.append(theme)

    return list(dict.fromkeys(themes))

