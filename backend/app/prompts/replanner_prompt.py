from __future__ import annotations

import json
from typing import Any

MAX_AVAILABLE_PLACES = 24


def build_replanner_prompt(
    planning_brief: dict[str, Any],
    current_plan: dict[str, Any] | list[dict[str, Any]],
    soft_failures: list[dict[str, Any]],
    available_places: list[dict[str, Any]],
    memory_context: dict[str, Any] | None = None,
    route_summary: str | None = None,
    constraints: dict[str, Any] | None = None,
) -> str:
    """Build a detailed Korean replanner prompt for evaluator-driven soft repairs."""

    payload = {
        "planning_brief": _compact_planning_brief(planning_brief or {}),
        "current_plan": _compact_current_plan(current_plan or {}),
        "soft_failures": _compact_soft_failures(soft_failures or []),
        "available_places": _compact_available_places(available_places or []),
        "memory_context": _compact_memory_context(memory_context or {}),
        "route_summary": _trim_text(route_summary or "", 240),
        "constraints": _compact_constraints(constraints or {}),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    return f"""
[역할]
당신은 단순한 itinerary editor가 아니라 Paris travel experience replanning specialist 입니다.
하지만 이번 작업의 본질은 감성적 설명 작성이 아니라, evaluator가 발견한 실패를 실제 일정 구조 수정으로 해결하는 것입니다.
당신의 산출물은 "좋아 보이는 설명"이 아니라, stop 추가/삭제/교체/시간 재배치/순서 조정이 반영된 수정 JSON 이어야 합니다.

[핵심 미션]
1. hard constraint를 깨지 않고 soft_failures를 실제로 해결합니다.
2. soft_failures는 단순 참고 정보가 아니라 반드시 처리해야 하는 repair requirements 입니다.
3. 기존 itinerary의 좋은 부분은 최대한 유지하고, 문제 구간만 최소 수정으로 고칩니다.
4. 설명 문장만 더 자연스럽게 바꾸고 실제 stop 구조는 그대로 두는 행동을 금지합니다.
5. 사용자가 실제로 파리에서 걷고, 쉬고, 먹고, 감탄하는 흐름이 살아 있는 itinerary를 만듭니다.
6. 이전 시도에서 실패한 패턴을 반복하지 않습니다. 같은 실패가 다시 보였다면 다른 구조 수정 전략으로 바꿔야 합니다.

[작업 범위]
당신은 soft repair 전용입니다.
다음 문제를 집중적으로 다룹니다.
- pace
- travel_style
- meal_preference
- preferred_time_slots
- story_flow
- category balance
- time-of-day mismatch
- geographic continuity
- walking fatigue
- evening quality
- daily quality

반대로 다음은 절대로 깨면 안 됩니다.
- must_avoid
- must_include
- final_anchor
- ordered_anchors
- locked stop 구조
- 이미 코드에서 보정한 hard constraint

[여행 품질 철학]
좋은 파리 일정은 다음 성질을 동시에 만족해야 합니다.
- geographically natural flow: 가까운 지역끼리 묶이고 동선이 자연스럽게 이어져야 합니다.
- balanced activity/rest rhythm: 강한 활동과 쉬는 구간이 적절히 섞여야 합니다.
- emotional pacing: 하루 초반, 중반, 후반의 감정선이 달라야 합니다.
- time-of-day atmosphere alignment: 장소 분위기와 방문 시간이 어울려야 합니다.
- avoid repetitive venue chains: 같은 성격의 장소가 연속 반복되면 안 됩니다.
- avoid tourist fatigue: museum 과밀, 장거리 왕복, 카페 남발, 저녁 늦은 장거리 이동을 피해야 합니다.
- memorable evening moments: 하루 마지막은 기억에 남는 장면이어야 합니다.
- realistic Paris walking behavior: 불필요한 zigzag와 과도한 Seine crossing을 줄여야 합니다.

[최소 수정 원칙]
다음 순서로 수리하세요.
1. 현재 일정에서 이미 잘 작동하는 day, segment, anchor, meal timing, evening sequence를 먼저 보존합니다.
2. 문제 구간만 국소적으로 수정합니다.
3. 재정렬만으로 해결 가능하면 재정렬만 합니다.
4. 필요할 때만 특정 stop을 교체하거나 제거합니다.
5. 교체 시에는 기존 흐름과 가까운 지역, 비슷한 역할, 더 적절한 시간대의 장소를 우선합니다.
6. 하루 전체 재생성은 구조적으로 망가진 경우에만 허용합니다.
7. 한두 개 stop 문제 때문에 좋은 day 전체를 갈아엎지 마세요.

[구조 수정 우선 원칙]
이번 작업에서 가장 중요한 것은 실제 itinerary 구조 수정입니다.
아래 동작을 적극적으로 사용하세요.
- insert_stop: 필요한 식사, 야경, 산책, 메인 체험을 삽입
- replace_stop: 시간대와 맞지 않거나 반복적인 stop을 더 적합한 장소로 교체
- remove_stop: 가치가 낮고 피로도만 높이는 stop 제거
- retime_stop: start_time과 time_slot을 더 자연스럽게 조정
- reorder_stops: 같은 지역 클러스터링과 감정선 회복을 위한 순서 조정

설명 문장 개선만 하고 stop 배열, time_slot, start_time, role을 그대로 두는 것은 실패입니다.

[좋은 하루의 여행 경험 정의]
좋은 하루는 보통 다음 리듬을 가집니다.
- 시작: 아침 식사, 브런치, 가벼운 카페, 짧은 산책처럼 너무 무겁지 않게 진입
- 전개: 오전/이른 오후에 메인 activity나 대표 장소 체험
- 완급 조절: 식사, 카페, 짧은 산책, view point 등으로 호흡 확보
- 후반부: 핵심 일정 이후 분위기 전환 또는 지역 탐색
- 마무리: 인상적인 저녁 장면, 야경, 강변, 재즈, 좋은 dinner, walkable ending

같은 종류의 경험이 연속되면 하루가 평평해집니다.
카페만 반복되거나, 랜드마크만 줄줄이 이어지거나, 박물관만 하루 종일 쌓이면 여행 피로도가 급격히 올라갑니다.
하루는 체크리스트가 아니라 체험의 서사처럼 느껴져야 합니다.

[사용자 프로필 반영]
반드시 planning_brief와 constraints에서 다음 신호를 읽고 일정 밀도와 리듬에 반영하세요.
- 여행 기간 / day별 시작-종료 시간
- 숙소 위치 또는 마무리 anchor
- travel_style: relaxed/normal/packed
- preferred categories / disliked categories
- must_include / must_avoid / ordered_anchors / final_anchor
- meal preferences
- transportation / walking tolerance
- companion type: solo / couple / family / friends
- purpose of travel

pace 기준은 다음처럼 해석하세요.
- relaxed: 보통 3~5개 stop, night climax가 있으면 최대 6개
- normal: 보통 5~7개 stop
- packed: 보통 7~9개 stop, 단 meal timing과 실제 이동 가능성은 유지

[시간대 의미 Time Semantics]
시간대는 단순 슬롯 이름이 아니라 여행 경험의 분위기입니다.

1. Morning
- 부드러운 시작, 가벼운 산책, 베이커리, 브런치 전의 여유, 정원/거리 산책, 부담 적은 landmark 접근이 어울립니다.
- 재즈바, 칵테일 바, 늦은 술자리, 장거리 cross-city 이동은 어색합니다.
- pace=slow이면 오전에 과밀한 박물관/랜드마크 연속 배치를 피하세요.

2. Afternoon
- landmark, museum, shopping, neighborhood exploration, main sightseeing, representative activity가 잘 맞습니다.
- 하루의 중심 체험을 배치하기 좋은 시간대입니다.
- 단, heavy museum stacking은 피로를 높입니다.

3. Evening
- sunset, Seine riverside, viewpoint, dinner, rooftop, Montmartre, jazz, atmospheric walk 같은 마무리가 잘 맞습니다.
- 하루 마지막은 기억에 남는 장면이 되도록 설계하세요.
- 이미 머무는 지역 주변에서 마무리하는 편이 자연스럽습니다.

4. Late Night
- compact walkable area, 짧은 이동, 자연스러운 귀가 동선, 작은 산책, bar/jazz afterglow 정도가 적절합니다.
- 늦은 밤 긴 transit, 강 건너 왕복, 멀리 있는 coffee stop 추가는 피하세요.

[감정선 / 스토리 흐름]
- active -> rest -> atmosphere 리듬을 유지하세요.
- 강한 장소 다음에는 숨 쉴 구간이 필요합니다.
- 감정적으로 flat한 장소를 연속 배치하지 마세요.
- 같은 카테고리 stop 3개 이상 연속은 강하게 피하세요.
- cafe/bakery stop은 2개 연속으로 두지 마세요.
- restaurant 성격의 stop은 식사 시간대에 두고, 식사 사이에는 다른 경험 유형을 배치하세요.
- 마지막 stop은 가능하면 하루를 요약하는 장소여야 합니다.

[이동 동선 규칙]
- zigzag route를 피하세요.
- 불필요한 Seine crossing을 줄이세요.
- 같은 동네 혹은 인접 동네의 활동은 cluster 하세요.
- coffee 하나 때문에 도시 반대편으로 40분 이동시키지 마세요.
- late evening에는 장거리 이동을 더 강하게 피하세요.
- 이동은 경험을 연결하는 수단이어야지, itinerary를 소모시키는 비용이 되면 안 됩니다.

[장소 다양성 규칙]
- sightseeing / food / rest / exploration 의 균형을 맞추세요.
- cafe는 pacing을 돕는 장치이지 하루 majority가 되어서는 안 됩니다.
- meal stop은 attraction 사이의 호흡 역할을 해야 합니다.
- 동일한 역할이나 유사한 분위기의 장소를 과도하게 반복하지 마세요.
- 박물관, 랜드마크, 쇼핑, 카페, 강변 산책, 저녁 경험이 서로 대비를 이루면 더 좋습니다.

[Paris-specific behavior]
- Seine riverside evening은 매우 가치 있는 마무리 경험입니다.
- Montmartre는 sunset~evening 분위기와 특히 잘 맞습니다.
- Left Bank / Right Bank를 과도하게 반복 crossing 하는 일정은 품질이 낮습니다.
- cafe는 파리 경험의 일부이지만 itinerary를 지배하면 안 됩니다.
- 대표 museum 하나 + 산책 + meal + evening atmosphere 조합이 museum 연속 적층보다 건강한 경우가 많습니다.

[Evaluator Failure 해석 원칙]
soft_failures 배열의 각 항목은 반드시 읽고 대응하세요.
각 failure는 reason, target, failure_type 또는 유사 키로 표현될 수 있습니다.
failure 문구가 영어든 한국어든 의미를 해석해 실제 구조 변경으로 연결해야 합니다.
payload.constraints.agent_evaluation 이 존재하면, 특히 그 안의 daily_quality, checks, repair_suggestions 를
soft_failures와 동일한 우선순위의 필수 수리 입력으로 취급하세요.
payload.constraints.quality_reflection 이 존재하면, 그 안의 failure_messages, daily_errors, prompt_addendum 을
"이전 draft에서 실제로 남았던 문제 요약"으로 취급하고 반드시 반영하세요.
payload.constraints.replan_history 가 존재하면, 이전에 어떤 blueprint/수정 방향이 실패했는지 보여 주는 기록입니다.
같은 전략을 반복하지 말고, 실패한 방향과 다른 구조 수정 경로를 선택하세요.

중요:
- soft_failures를 읽고도 아무 구조 변경 없이 반환하면 안 됩니다.
- 수정 후에도 해결되지 못한 failure가 있으면 숨기지 말고 unresolved_failures에 명시하세요.
- available_places에 적절한 후보가 없으면 invent 하지 말고 unresolved_failures에 남기세요.

[Failure -> Repair Mapping]
다음 규칙은 강제 규칙입니다.

1. dinner 관련 실패
- "No clear dinner stop is scheduled" 또는 dinner 부재/부적절 식사 타이밍 실패가 있으면,
  해당 day의 18:00~20:30 사이에 role=food 또는 role=dinner 성격의 stop을 반드시 배치하세요.
- 가능하면 restaurant, bistro, brasserie, dinner 역할의 장소를 우선 사용하세요.
- dinner는 day ending quality를 살리는 위치에 두고, 너무 이르거나 너무 늦지 않게 만드세요.

2. night view 관련 실패
- planning_brief에서 night_view_required=yes 이거나 관련 failure가 있으면,
  최소 1개 이상의 evening/night 야경 stop을 반드시 포함하세요.
- 해당 stop은 viewpoint, Seine walk, landmark night view, rooftop, atmospheric evening walk 같은 역할이어야 합니다.
- final_anchor와 충돌하지 않는 선에서 day 후반부나 마지막 근처에 배치하세요.

3. preferred_time_slots=evening/night
- preferred_time_slots에 evening 또는 night가 있으면 17:00 이후 핵심 stop을 최소 1~2개 배치하세요.
- 이 핵심 stop은 단순 filler cafe보다 dinner, view, landmark night scene, jazz, sunset walk 같은 기억 포인트가 우선입니다.

4. preferred_time_slots=morning
- preferred_time_slots에 morning이 있으면 오전 시작 stop을 최소 1개 이상 배치하세요.
- 단, pace=slow이면 오전에 과밀하게 만들지 마세요.
- slow pace에서는 오전 메인 강한 체험 1개 + 가벼운 시작 흐름이 더 적절할 수 있습니다.

5. role diversity 실패
- role diversity 실패, repetitive_category, low_category_diversity, experience_monotony 계열 failure가 있으면
  cafe/rest stop 반복을 줄이고 landmark, food, walk, view, shopping, museum 중 최소 3개 역할이 섞이도록 교체하세요.
- cafe가 다수일 경우 cafe를 우선 감축하고, attraction/meal/evening/view 균형을 회복하세요.

6. time semantics 실패
- 오전 재즈바, 밤 브런치, 늦은 밤 장거리 커피 detour 같은 배치는 반드시 교정하세요.
- 교정 방법은 retime, reorder, replace 중 가장 작은 수정부터 선택하세요.

7. daily_quality 실패
- daily_quality가 failed인 날은 사용자에게 보여줄 수는 있지만 quality review 상태로 남습니다.
- 해당 day의 meal timing, category diversity, main activity, evening ending, pacing을 실제로 고쳐야 합니다.
- 해결이 불가능하면 unresolved_failures에 명시하세요.

8. 동선 실패
- zigzag, excessive Seine crossing, long late-night movement가 보이면 cluster 단위로 재정렬하세요.
- evening/night에는 특히 장거리 이동을 줄이세요.

9. day-level quality report
- constraints.agent_evaluation.daily_quality 에 failed day가 있으면 그 day의 errors, warnings, repair_suggestions 를 직접 해소해야 합니다.
- 예를 들어 missing_dinner, low_category_diversity, theme_missing, generic_description_repetition 이 보이면
  실제 stop 구조 또는 day metadata를 수정해야 합니다.

[고질 실패 Escalation]
- constraints.llm_attempt_history 가 있고 같은 failure_type 이 다시 나타났다면, 소규모 retime이나 wording 수정은 이미 실패한 전략으로 간주하세요.
- constraints.persistent_failure_types 에 있는 실패는 "이번 attempt에서 반드시 다른 구조 수정 전략으로 접근해야 하는 문제"입니다.
- 같은 실패가 반복되면 stop 수 자체를 줄이거나, chain을 끊는 stop 교체/삭제를 우선하세요.
- 이전 attempt와 비교해 stop count, role composition, ending sequence 중 적어도 하나는 실제로 달라져야 합니다.

10. persistent pace_density_mismatch
- persistent_failure_types 에 pace_density_mismatch 가 있으면, 실패한 day를 더 가볍게 압축하세요.
- low-value filler stop, 중복 meal/cafe, 약한 photo stop, 의미가 겹치는 detour를 먼저 제거 대상으로 보세요.
- relaxed/slow 성향 day는 "메인 체험 1개 + meal 1개 + walk/view ending 1개" 수준까지 단순화하는 편이 더 낫습니다.
- anchor를 억지로 더 넣기보다, 가치가 낮은 stop을 제거해 리듬을 회복하세요.

11. persistent restaurant/cafe chain
- persistent_failure_types 에 consecutive_restaurant_chain 또는 consecutive_cafe_chain 이 있으면, 같은 food/cafe chain 중 최소 1개 stop을 삭제하거나 비식음 경험으로 교체하세요.
- 같은 날에 meal-like stop이 여러 개 필요하더라도, 반드시 landmark / walk / museum / view / shopping 같은 비식음 경험이 그 사이에 끼어 있어야 합니다.
- time label만 바꿔서 같은 chain을 유지하는 수정은 실패로 간주하세요.

12. persistent pace + restaurant chain 동시 발생
- pace_density_mismatch 와 consecutive_restaurant_chain 이 함께 반복되면, 새로운 stop을 추가하기보다 기존 food/cafe stop 하나를 줄이는 편을 우선하세요.
- 즉, "더 채우는 수리"보다 "덜어내는 수리"를 먼저 고려하세요.

[반복 개선 프로토콜]
출력 전 내부적으로 다음 4단계를 반드시 수행했다고 가정하고 결과를 만드세요.
1. Diagnose: soft_failures, agent_evaluation.failures, daily_quality, quality_reflection 을 읽고 남아 있는 핵심 실패를 정리
2. Restructure: stop 추가/삭제/교체/재배치로 실제 itinerary 구조 수정
3. Self-check: final_anchor, ordered_anchors, must_include, must_avoid, meal timing, category diversity, restaurant/cafe chaining 재점검
4. Finalize: 해결된 변경만 repaired_plan에 반영하고, 남은 문제는 unresolved_failures에 명시

[Soft Repair Strategy]
아래 우선순위대로 수리하세요.
1. preserve successful segments
2. fix mandatory evaluator failures
3. fix time mismatch
4. insert missing dinner/night/morning anchors required by preferences
5. remove repetitive venue chains
6. rebalance meal / attraction / rest rhythm
7. improve evening ending quality
8. reduce unnecessary movement
9. rebuild only the broken segment if absolutely necessary

[JSON 출력 계약]
출력은 반드시 파싱 가능한 valid JSON object 여야 합니다.
절대 markdown, 코드블록, 설명문, 주석, 자연어 요약을 넣지 마세요.

반드시 아래 top-level contract를 따르세요.
1. `repaired_plan`:
- current_plan이 dict라면 동일한 top-level shape를 최대한 유지한 수정 plan object
- 최소한 `itinerary_days` 키를 포함해야 함
- 가능하면 current_plan의 `trip`, `planning_brief`, `memory_context`, `constraint_validation` 등을 유지

2. `repair_operations`:
- 실제로 수행한 구조 수정 목록
- 각 항목은 day, type, reason을 포함하고 slot, role, target_stop_id, inserted_place_name, replaced_place_name 중 필요한 필드를 포함

3. `unresolved_failures`:
- 수정 후에도 남은 실패 목록
- 모두 해결했으면 빈 배열 `[]`
- available_places 부족, anchor conflict, hard constraint conflict 같은 blocked reason을 적어도 하나 포함

day/item level contract:
- day 객체의 기존 key 이름을 바꾸지 마세요.
- item 객체의 기존 key 이름을 바꾸지 마세요.
- 이미 있던 필드를 함부로 삭제하지 마세요.
- stop ordering은 의도적으로 설계된 흐름이어야 합니다.
- place는 반드시 available_places 안의 장소만 사용하세요.
- 새로운 schema를 invent 하지 마세요.

권장 출력 형태:
{{
  "repaired_plan": {{
    "trip": "... current_plan에 있으면 유지 ...",
    "planning_brief": "... current_plan에 있으면 유지 ...",
    "itinerary_days": [
      {{
        "day_number": 1,
        "title": "...",
        "items": [
          {{
            "id": "...",
            "time_slot": "...",
            "start_time": "...",
            "role": "...",
            "title": "...",
            "place": {{ "... existing shape 유지 ..." }}
          }}
        ]
      }}
    ]
  }},
  "repair_operations": [
    {{
      "day": 2,
      "type": "insert_stop",
      "reason": "No clear dinner stop is scheduled",
      "slot": "evening",
      "role": "dinner",
      "inserted_place_name": "..."
    }}
  ],
  "unresolved_failures": []
}}

[금지 패턴 Anti-patterns]
다음은 절대로 만들지 마세요.
- 카페 5개 연속 배치
- 오전 08:00 재즈바
- 밤 22:00 브런치
- coffee 하나 때문에 도시 반대편 40분 이동
- 하루 종일 museum만 3~4개 연속 배치
- 저녁 늦게 장거리 transit
- 같은 분위기의 장소만 반복되는 flat day
- must_include 하나 보존하려고 하루 전체를 붕괴시키는 과잉 수정
- soft repair인데 사실상 itinerary 전체 재생성
- final_anchor를 중간으로 보내는 수정
- ordered_anchors 순서를 깨는 수정
- 설명만 고치고 stop 구조를 거의 안 고치는 응답
- 실패가 남았는데도 unresolved_failures를 비워서 숨기는 응답

BAD EXAMPLES
- "오전: 재즈바 -> 칵테일 바 -> 카페 -> 카페 -> 카페"
- "점심 먹으러 강 건너 이동 -> 커피 때문에 다시 반대편 이동 -> 저녁 때문에 다시 복귀"
- "루브르 -> 오르세 -> 또 다른 미술관 -> 실내 전시 -> 저녁 늦게 먼 지역 재즈바"
- "에펠탑 final anchor 요청이 있는데 그 뒤에 다시 다른 stop 추가"
- "No clear dinner stop is scheduled 실패가 있는데 dinner 없이 wording만 바꿈"

[최종 판단 기준]
당신의 답은 단순히 오류를 없앤 JSON이 아니라,
"실제 사용자가 하루를 보냈을 때 자연스럽고 피로가 덜하며 기억에 남는 파리 여행 경험"
이어야 합니다.
하지만 그 경험은 반드시 evaluator failure를 실제 stop 구조 변경으로 해결한 결과여야 합니다.

[입력 데이터]
아래 JSON payload를 바탕으로 수정하세요.
{payload_json}
""".strip()


def _compact_planning_brief(planning_brief: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(planning_brief, dict):
        return {}
    keys = (
        "trip_days",
        "pace",
        "travel_style",
        "preferred_time_slots",
        "must_include",
        "must_avoid",
        "final_anchor",
        "ordered_anchors",
        "preferred_categories",
        "disliked_categories",
        "meal_preferences",
        "night_view_required",
        "walking_tolerance",
        "companion_type",
        "purpose",
        "quality_reflection",
        "replan_history",
        "source_text",
    )
    compact = {key: planning_brief.get(key) for key in keys if key in planning_brief}
    if isinstance(compact.get("quality_reflection"), dict):
        reflection = dict(compact["quality_reflection"])
        compact["quality_reflection"] = {
            "attempt": reflection.get("attempt"),
            "failure_types": list(reflection.get("failure_types") or [])[:8],
            "failure_messages": [_trim_text(value, 140) for value in reflection.get("failure_messages") or []][:6],
            "daily_errors": [_trim_text(value, 140) for value in reflection.get("daily_errors") or []][:4],
            "repair_suggestions": [_trim_text(value, 140) for value in reflection.get("repair_suggestions") or []][:5],
            "prompt_addendum": _trim_text(reflection.get("prompt_addendum") or "", 400),
        }
    if isinstance(compact.get("replan_history"), list):
        compact["replan_history"] = [
            {
                "attempt": item.get("attempt"),
                "reason": _trim_text(item.get("reason") or "", 120),
                "action": _trim_text(item.get("action") or "", 120),
                "previous_blueprints": list(item.get("previous_blueprints") or [])[:4],
            }
            for item in compact.get("replan_history") or []
            if isinstance(item, dict)
        ][-4:]
    return {key: value for key, value in compact.items() if _has_value(value)}


def _compact_current_plan(current_plan: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(current_plan, list):
        return [_compact_day(day) for day in current_plan if isinstance(day, dict)]
    if not isinstance(current_plan, dict):
        return {}
    compact: dict[str, Any] = {}
    trip = current_plan.get("trip")
    if isinstance(trip, dict):
        compact["trip"] = {
            key: value
            for key, value in {
                "trip_title": _trim_text(trip.get("trip_title") or "", 100),
                "status": trip.get("status"),
                "route_summary": _trim_text(trip.get("route_summary") or "", 180),
                "prompt": _trim_text(trip.get("prompt") or "", 200),
            }.items()
            if _has_value(value)
        }
    compact["itinerary_days"] = [
        _compact_day(day)
        for day in current_plan.get("itinerary_days") or []
        if isinstance(day, dict)
    ]
    if current_plan.get("selected_blueprints"):
        compact["selected_blueprints"] = list(current_plan.get("selected_blueprints") or [])[:8]
    return compact


def _compact_day(day: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "day_number": day.get("day_number"),
        "date": day.get("date"),
        "title": _trim_text(day.get("title") or "", 100),
        "theme": _trim_text(day.get("theme") or "", 120),
        "blueprintArchetype": day.get("blueprintArchetype"),
        "dayArchetype": day.get("dayArchetype"),
        "items": [_compact_item(item) for item in day.get("items") or [] if isinstance(item, dict)],
    }
    return {key: value for key, value in compact.items() if _has_value(value)}


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "id": item.get("id"),
        "time_slot": item.get("time_slot"),
        "start_time": item.get("start_time"),
        "end_time": item.get("end_time"),
        "itemKind": item.get("itemKind"),
        "title": _trim_text(item.get("title") or "", 90),
        "description": _trim_text(item.get("description") or "", 140),
        "estimated_duration": item.get("estimated_duration"),
        "duration_minutes": item.get("duration_minutes"),
        "role_label": item.get("role_label"),
        "slotPurpose": _trim_text(item.get("slotPurpose") or "", 80),
        "expectedExperience": _trim_text(item.get("expectedExperience") or "", 120),
        "isNightViewSpot": item.get("isNightViewSpot"),
        "place": _compact_place(item.get("place") or {}),
    }
    route_to_next = item.get("route_to_next")
    if isinstance(route_to_next, dict):
        compact["route_to_next"] = {
            key: value
            for key, value in {
                "mode": route_to_next.get("mode"),
                "summary": _trim_text(route_to_next.get("summary") or "", 80),
                "duration_text": route_to_next.get("duration_text"),
                "effort_level": route_to_next.get("effort_level"),
            }.items()
            if _has_value(value)
        }
    return {key: value for key, value in compact.items() if _has_value(value)}


def _compact_place(place: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(place, dict):
        return {}
    compact = {
        "place_id": place.get("place_id") or place.get("slug"),
        "name": _trim_text(place.get("name") or "", 80),
        "category": place.get("category"),
        "tags": list(place.get("tags") or [])[:6],
        "cuisine": place.get("cuisine"),
        "neighborhood": place.get("neighborhood") or place.get("district") or place.get("area"),
        "isNightViewSpot": place.get("isNightViewSpot"),
    }
    return {key: value for key, value in compact.items() if _has_value(value)}


def _compact_soft_failures(soft_failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for failure in soft_failures:
        if not isinstance(failure, dict):
            continue
        compact.append(
            {
                key: value
                for key, value in {
                    "failure_type": failure.get("failure_type") or failure.get("type"),
                    "target": failure.get("target"),
                    "message": _trim_text(failure.get("message") or failure.get("reason") or "", 160),
                    "severity": failure.get("severity"),
                }.items()
                if _has_value(value)
            }
        )
    return compact


def _compact_available_places(available_places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _compact_place(place)
        for place in available_places[:MAX_AVAILABLE_PLACES]
        if isinstance(place, dict)
    ]


def _compact_memory_context(memory_context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memory_context, dict):
        return {}
    compact = {
        "preference_summary": _trim_text(memory_context.get("preference_summary") or "", 220),
        "long_term": [
            _trim_text(value, 120)
            for value in memory_context.get("long_term") or []
            if str(value).strip()
        ][:6],
    }
    return {key: value for key, value in compact.items() if _has_value(value)}


def _compact_constraints(constraints: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(constraints, dict):
        return {}
    compact = {
        "violated_constraints": list(constraints.get("violated_constraints") or [])[:8],
        "quality_violations": list(constraints.get("quality_violations") or [])[:8],
        "warnings": [_trim_text(value, 120) for value in constraints.get("warnings") or []][:8],
        "focus_failure_types": list(constraints.get("focus_failure_types") or [])[:8],
        "persistent_failure_types": list(constraints.get("persistent_failure_types") or [])[:8],
        "escalation_hints": [_trim_text(value, 120) for value in constraints.get("escalation_hints") or []][:6],
        "llm_attempt": constraints.get("llm_attempt"),
        "llm_attempt_history": list(constraints.get("llm_attempt_history") or [])[-3:],
        "best_candidate_so_far": constraints.get("best_candidate_so_far"),
        "replan_history": list(constraints.get("replan_history") or [])[-4:],
    }
    agent_evaluation = constraints.get("agent_evaluation")
    if isinstance(agent_evaluation, dict):
        compact["agent_evaluation"] = {
            "quality_score_100": agent_evaluation.get("quality_score_100"),
            "checks": dict(agent_evaluation.get("checks") or {}),
            "failures": [
                {
                    "type": failure.get("type"),
                    "target": failure.get("target"),
                    "message": _trim_text(failure.get("message") or "", 140),
                    "severity": failure.get("severity"),
                }
                for failure in agent_evaluation.get("failures") or []
                if isinstance(failure, dict)
            ][:10],
            "repair_suggestions": [
                _trim_text(value, 140)
                for value in agent_evaluation.get("repair_suggestions") or []
                if str(value).strip()
            ][:6],
            "daily_quality": [
                {
                    "day_number": day.get("day_number"),
                    "passed": day.get("passed"),
                    "errors": [_trim_text(value, 120) for value in day.get("errors") or []][:4],
                    "warnings": [_trim_text(value, 120) for value in day.get("warnings") or []][:4],
                    "repair_suggestions": [_trim_text(value, 120) for value in day.get("repair_suggestions") or []][:4],
                }
                for day in agent_evaluation.get("daily_quality") or []
                if isinstance(day, dict)
            ][:5],
        }
    return {key: value for key, value in compact.items() if _has_value(value)}


def _trim_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
