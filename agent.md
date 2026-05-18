# Paris AI Agent 동작 설명

이 문서는 현재 `feature/agent-demo` 코드 기준으로 Paris AI Agent가 어떻게 동작하는지 정리한 문서이다. 핵심 정의는 다음과 같다.

> 우리 Agent는 자연어 요청을 Planning Brief로 구조화하고, 사용자 조건과 시간 의미를 기준으로 day blueprint를 선택한 뒤, 장소 검색, 동선 최적화, 조건 검증, 재계획을 거쳐 MongoDB에 저장하는 Travel Planning Agent이다.

즉, 이 Agent는 단순히 LLM에게 "여행 일정 만들어줘"라고 묻고 결과를 그대로 저장하는 구조가 아니다. 자연어 요청을 여행 계획 제약 조건으로 바꾸고, 그 제약 조건을 만족하는 일정인지 검증하며, 실패하면 다시 계획하는 구조를 가진다.

## 전체 구조

현재 시스템은 크게 네 계층으로 나뉜다.

1. `frontend`
   - 사용자가 자연어 여행 요청을 입력하는 UI.
   - 주요 요청은 `/api/trips/generate`, `/api/trips/{trip_id}/agent-modify`, `/api/flights/search`, `/api/hotels/search` 등으로 전달된다.

2. `backend`
   - FastAPI 서버.
   - 인증, MongoDB 저장, Google Places, 항공/호텔 API, route optimizer, agent 결과 정규화와 저장을 담당한다.

3. `parser_api`
   - Agent의 의도 분류, parser, orchestrator, executor가 있는 로컬 agent 계층.
   - 자연어를 구조화된 intent payload로 바꾼다.

4. 외부 API
   - OpenAI: 자연어 구조화, 항공/호텔 추천 랭킹 등에 사용.
   - Google Places: 장소 검색, 사진, 음식점 후보 보강.
   - RapidAPI Kiwi: 항공권 검색.
   - RapidAPI Booking: 호텔 검색.
   - MongoDB: 최종 여행 계획과 일정 데이터 저장.

## 주요 진입점

새 여행 일정 생성의 프론트 요청은 다음 흐름으로 들어온다.

```text
Frontend
  -> POST /api/trips/generate/jobs
  -> backend/app/api/routes/trips.py
  -> start_generate_trip_job()
  -> background task: _run_generation_job()
  -> backend/app/services/agent_service.py
  -> generate_trip_payload()
  -> MongoDB 저장 후 GET /api/trips/generate/jobs/{job_id}로 polling
```

동기식 `POST /api/trips/generate`도 남아 있지만, 현재 프론트는 긴 일정 생성 중 nginx timeout이나 HTML error page가 화면에 그대로 노출되지 않도록 job 생성과 polling 흐름을 사용한다.

기존 여행 일정 수정은 다음 흐름으로 들어온다.

```text
Frontend
  -> POST /api/trips/{trip_id}/agent-modify
  -> backend/app/api/routes/trips.py
  -> agent_modify_trip_route()
  -> backend/app/services/agent_service.py
  -> modify_trip_with_agent()
```

## Agent 선택 방식

`backend/app/services/agent_service.py`의 `generate_trip_payload()`가 agent 실행 방식을 결정한다.

1. `EXTERNAL_AGENT_API_URL`이 설정되어 있으면 외부 agent API를 호출한다.
2. 외부 agent가 없으면 로컬 agent인 `parser_api.services.agent_service.run_agent()`를 호출한다.
3. 로컬 agent 실행이 불가능하면 `_mock_trip_payload()` 기반 fallback planner가 최소한의 일정을 만든다.

현재 Docker 배포에서는 로컬 agent가 기본 흐름이다.

## 로컬 Agent Orchestrator

로컬 agent의 중심은 `parser_api/services/orchestration_service.py`의 `AgentOrchestrator`이다.

동작 순서는 다음과 같다.

1. `extract_intent(message, context)`로 사용자의 의도를 분류한다.
2. intent에 맞는 parser를 `ParserRegistry`에서 찾는다.
3. parser가 자연어를 Pydantic payload로 구조화한다.
4. 필요한 정보가 부족하면 `status="ASK"`를 반환한다.
5. 실제 예약/취소처럼 확인이 필요한 작업은 confirmation을 요구한다.
6. 실행 가능한 intent는 executor로 넘긴다.
7. 결과에 Planning Brief를 붙이고 `AgentRunResponse`로 반환한다.

응답 상태는 주로 다음 세 가지다.

- `DONE`: 요청을 처리했고 구조화된 결과가 있다.
- `ASK`: 추가 정보가 필요하거나 사용자 확인이 필요하다.
- `ERROR`: parser 또는 executor가 처리하지 못했다.

## Intent 분류

의도 분류는 `parser_api/parsers/classifier.py`에서 시작해 `parser_api/parsers/workflow/request_bundle/detection.py`의 규칙 기반 detector로 이어진다.

지원 intent는 `parser_api/intents.py`에 정의되어 있다.

대표 intent는 다음과 같다.

- `CREATE_PLAN`: 새 여행 일정 생성.
- `MODIFY_PLAN`: 기존 일정 수정.
- `FLIGHT_SEARCH`: 항공권 검색.
- `FLIGHT_BOOK`: 항공권 예약 단계.
- `HOTEL_SEARCH`: 호텔 검색.
- `HOTEL_BOOK`: 호텔 예약 단계.
- `ESTIMATE_BUDGET`: 예산 계산.
- `MANAGE_BOOKING`: 예약 변경/취소/조회.
- `OPTIMIZE_ROUTE`: 동선 최적화.
- `RECOMMEND_VENUE`: 장소 추천.
- `MANAGE_TRIP`: 여행 관리.
- `TRIP_DIARY`: 여행 다이어리.
- `REQUEST_BUNDLE`: 여러 요청이 한 문장에 섞인 복합 요청.

예를 들어 사용자가 "파리 4일 일정 만들고 호텔도 찾아줘"처럼 여러 작업을 한 번에 요청하면 `REQUEST_BUNDLE`로 묶고, 내부 action을 순서와 의존성에 따라 실행한다.

## CREATE_PLAN Parser

새 일정 생성은 `parser_api/parsers/create_plan/parser.py`의 `CreatePlanParser`가 처리한다.

흐름은 다음과 같다.

1. OpenAI를 호출해 자연어를 JSON으로 구조화한다.
2. `_normalize_llm_payload()`로 LLM 응답 모양을 정규화한다.
3. `CreatePlanPayload` Pydantic 모델로 검증한다.
4. `_apply_rule_overrides()`로 규칙 기반 보정을 적용한다.
5. LLM 파싱이 실패하면 기본 `CreatePlanPayload()`를 만들고 규칙 기반 보정만 적용한다.

OpenAI 호출은 `parser_api/parsers/llm.py`의 `_call_llm_structured()`에서 수행된다. 기본 모델은 `OPENAI_RESPONSE_MODEL`이 없으면 `gpt-4o-mini`이다.

## Planning Brief

Planning Brief는 agent가 따라야 하는 여행 계획 명세서이다. 자연어로 들어온 취향과 조건을 구조화한 객체이며, 일정 생성, blueprint 선택, 검증, 재계획의 기준이 된다.

생성 위치는 다음과 같다.

```text
backend/app/services/planning_brief_service.py
  -> build_planning_brief()
```

Planning Brief에는 보통 다음 정보가 들어간다.

- `intent`: create_trip, modify_trip 등 현재 작업 목적.
- `trip_days`: 여행 일수.
- `destination`: 목적지.
- `must_include`: 꼭 포함해야 하는 장소.
- `must_avoid`: 피해야 하는 장소.
- `preferred_time_slots`: 선호 시간대.
- `meal_preference`: 카페, 디저트, 프렌치 식사 등 식사 선호.
- `night_view_required`: 야경 필수 여부.
- `pace`: slow, normal, fast.
- `travel_style`: museum, cafe, foodie, night_view 등 여행 스타일.
- `budget_range`: 예산 정보.
- `hotel_area_preference`: 숙소 권역 선호.
- `transport_preference`: walking, transit, both 등 이동 선호.
- `hard_constraints`: 반드시 지켜야 하는 제약.
- `soft_constraints`: 가능하면 반영해야 하는 선호.
- `locked_stops`: 특정 장소를 특정 시간대에 고정하는 정보.
- `preferred_blueprints`: 우선 사용할 day blueprint 후보.

예를 들어 사용자의 자연어는 다음처럼 구조화된다.

```text
"3박 4일"
  -> trip_days: 4

"루브르랑 오르세"
  -> must_include: ["Louvre", "Orsay"]

"여유롭게"
  -> pace: "slow"

"마지막 밤", "야경"
  -> night_view_required: true
  -> preferred_time_slots: ["evening", "night"]

"카페", "디저트", "미식"
  -> meal_preference
  -> travel_style

"에펠탑 야경"
  -> locked_stops에 Eiffel Tower evening/night 고정 후보 추가
```

## Day Blueprint 선택

Day blueprint는 하루 일정을 어떤 리듬으로 구성할지 정하는 틀이다. 장소 목록을 무작정 나열하는 대신, 사용자의 조건에 맞는 하루의 구조를 먼저 고른다.

주요 구현 위치는 다음과 같다.

```text
parser_api/services/place_catalog.py
  -> build_itinerary()
  -> _select_blueprint_archetype()
  -> _day_blueprint()
```

대표 blueprint archetype은 다음과 같다.

- `slow_cafe_evening_day`
  - 느린 템포, 카페/디저트, 저녁 야경 조건이 강할 때 사용.

- `night_view_focused_day`
  - 에펠탑, 센강, 개선문 등 야경 조건이 핵심일 때 사용.

- `romantic_evening_day`
  - 저녁 식사, 산책, 분위기 중심의 하루에 사용.

- `museum_focused_day`
  - 루브르, 오르세 등 미술관 중심 일정에 사용.

- `slow_cafe_day`
  - 카페, 골목 산책, 여유로운 로컬 감성 일정에 사용.

- `general_landmark_day`
  - 특정 조건이 강하지 않은 일반 랜드마크 일정에 사용.

blueprint는 보통 다음과 같은 slot 구조를 가진다.

```text
morning
  -> 하루의 첫 핵심 장소

lunch
  -> 동선 중간 식사 또는 카페

afternoon
  -> 같은 권역의 주요 장소

evening/night
  -> 야경, 저녁 식사, 산책, 하루의 마무리
```

Planning Brief의 `preferred_blueprints`, `locked_stops`, `pace`, `travel_style`, `meal_preference`, `night_view_required`가 blueprint 선택에 영향을 준다.

## 장소 후보 구성

blueprint가 정해지면 각 slot에 들어갈 장소를 고른다.

주요 데이터는 다음에서 온다.

- `parser_api/services/place_catalog.py`
  - 기본 장소 카탈로그와 blueprint 기반 장소 선택.

- `backend/app/services/google_places_service.py`
  - Google Places 기반 장소 검색, 음식점 후보, 사진, 평점, Google Maps URI 등 보강.

- `backend/app/services/place_repository_service.py`
  - 좌표, 거리 계산, 장소 repository 관련 보조 기능.

장소 객체에는 보통 다음 정보가 붙는다.

- 장소명.
- 카테고리.
- 좌표.
- 설명.
- 예상 체류 시간.
- 이미지 또는 Google photo.
- Google place id.
- Google Maps URI.
- 평점과 리뷰 수.
- 음식점/카페 후보 정보.

## 동선 최적화

장소 후보가 정해진 뒤에는 route optimizer가 날짜별 동선을 정리한다.

주요 구현 위치는 다음과 같다.

```text
backend/app/services/route_optimizer_service.py
  -> optimize_trip_payload()
  -> attach_route_legs_to_days()
  -> _optimize_day()
  -> _attach_route_legs()
```

route optimizer는 다음 일을 한다.

- 하루 안의 장소 순서를 거리 기준으로 재정렬한다.
- 같은 권역의 장소를 최대한 묶는다.
- 걷기/대중교통 선호를 반영한다.
- 장소 사이 `route_to_next` 정보를 붙인다.
- 이동 시간과 거리, effort level을 계산한다.
- 점심/카페/휴식 slot이 동선 중간에 자연스럽게 들어가도록 보정한다.
- 이동 부담이 큰 구간에는 buffer나 rest reason을 붙인다.

`route_to_next`에는 다음과 같은 정보가 포함될 수 있다.

- 이동 모드.
- 이동 거리.
- 예상 이동 시간.
- scheduled duration.
- effort level.
- rest buffer reason.
- 표시용 route summary.

## 조건 검증

일정이 생성된 뒤에는 Planning Brief를 기준으로 조건을 만족하는지 검사한다.

주요 구현 위치는 다음과 같다.

```text
backend/app/services/planning_brief_service.py
  -> validate_planning_brief_compliance()
```

검증 항목은 다음과 같다.

- `must_include` 장소가 실제 일정에 들어갔는가.
- `must_avoid` 장소가 들어가지 않았는가.
- 야경 필수 조건이 evening/night slot에 반영되었는가.
- 선호 시간대가 일정에 반영되었는가.
- 카페/디저트/프렌치 식사 선호가 충분히 반영되었는가.
- `pace=slow`인데 하루에 장소가 너무 많지 않은가.
- 이동 부담이 높은 구간이 과도하지 않은가.
- helper block, free time, placeholder가 너무 많지 않은가.
- 하루의 story flow가 자연스러운가.
- night climax가 필요한 경우 마지막 장면에 야경 포인트가 있는가.

검증 결과는 `constraint_validation`으로 저장된다.

대표 필드는 다음과 같다.

- `is_valid`
- `score`
- `constraint_score`
- `preference_match_score`
- `route_score`
- `pacing_score`
- `story_flow_score`
- `final_quality_score`
- `satisfied_constraints`
- `violated_constraints`
- `missing_must_include`
- `included_must_avoid`
- `time_slot_violations`
- `meal_preference_violations`
- `pace_violations`
- `quality_violations`
- `warnings`
- `needs_replan`

## 재계획

조건 검증에서 문제가 발견되면 agent는 재계획을 시도한다.

주요 구현 위치는 다음과 같다.

```text
backend/app/services/agent_service.py
  -> _optimize_payload_if_possible()
  -> _should_replan_validation()
  -> _replan_action()
```

현재 새 일정 생성에서는 최대 2번까지 재계획한다.

재계획이 필요한 대표 상황은 다음과 같다.

- 필수 포함 장소가 빠짐.
- 피해야 할 장소가 포함됨.
- 야경 필수 조건을 만족하지 못함.
- 선호 시간대가 맞지 않음.
- story flow 품질이 낮음.
- helper block이 너무 많음.
- `final_quality_score`가 기준보다 낮음.

재계획 action은 검증 결과에 따라 달라진다.

예시:

- `lock_eiffel_tower_to_night_slot`
  - 에펠탑 야경 조건이 있는데 낮 시간대에 배치되었거나 누락된 경우.

- `reduce_helper_blocks_and_rebuild`
  - helper block이 많거나 story flow 품질이 낮은 경우.

- `switch_to_evening_first_blueprint`
  - 야경이나 evening/night 조건이 강한데 현재 blueprint가 맞지 않는 경우.

- `strengthen_planning_brief_and_rebuild`
  - 기타 제약 위반이 있는 경우.

재계획 시 Planning Brief에는 `replan_history`가 쌓이고, `strict_constraints`가 켜지며, preferred blueprint가 조정될 수 있다.

## MongoDB 저장

최종 일정은 `backend/app/services/trip_service.py`의 `create_generated_trip()`에서 MongoDB에 저장된다.

저장되는 주요 collection은 다음과 같다.

- `trip_plans`
  - 여행 제목, 사용자 id, 날짜, 총 일수, 스타일 태그, 상태, route summary, Planning Brief, constraint validation, agent explanation, agent trace 등을 저장한다.

- `itinerary_day`
  - 날짜별 일정, day number, title, route summary, items, blueprint archetype 등을 저장한다.

- `budget_summary`
  - 관광지 비용, 호텔 비용, custom expenses, currency 등을 저장한다.

저장 후 프론트는 generation job 응답의 `trip` 또는 `trip_id`를 사용해 여행 계획 화면으로 이동한다.

## 기존 일정 수정 흐름

기존 일정 수정은 `MODIFY_PLAN` intent를 사용한다.

예시 요청:

```text
"2일차에 카페를 하나 더 넣어줘"
"에펠탑을 밤 일정으로 옮겨줘"
"루브르는 빼고 오르세를 더 오래 보게 해줘"
```

흐름은 다음과 같다.

1. `/api/trips/{trip_id}/agent-modify`로 요청이 들어온다.
2. 백엔드가 기존 `trip`과 `itinerary_day`를 MongoDB에서 읽는다.
3. `MODIFY_PLAN` parser가 수정 의도를 구조화한다.
4. 수정 payload에 `trip_id`, `target_day`, operation 정보를 채운다.
5. `_apply_modify_payload()`가 기존 itinerary에 patch를 적용한다.
6. 필요한 경우 Google Places로 음식점/카페 후보를 보강한다.
7. route leg를 다시 붙인다.
8. Planning Brief 기준으로 다시 검증한다.
9. MongoDB의 기존 itinerary를 업데이트한다.

수정 흐름도 새 일정 생성과 마찬가지로 "수정 후 검증"을 수행한다.

## Request Bundle 흐름

사용자가 한 문장에 여러 작업을 섞으면 `REQUEST_BUNDLE`이 사용된다.

예시:

```text
"파리 4일 일정 만들고, 항공권이랑 호텔도 같이 찾아줘"
```

이 경우 agent는 내부 action 목록을 만들고, 각 action을 순서대로 실행한다.

각 action은 다음 정보를 가진다.

- `intent`
- `order`
- `depends_on`
- `action_ref`

앞 action이 실패하거나 `ASK` 상태면 뒤 action은 `SKIPPED`될 수 있다. 일부만 성공하면 bundle 전체 상태는 `PARTIAL`이 된다.

## 항공권/호텔 기능

항공권과 호텔 검색은 여행 계획 agent와 별도 API로도 동작한다.

항공권:

```text
frontend
  -> /api/flights/search
  -> backend/app/api/routes/flights.py
  -> backend/app/services/kiwi_service.py
  -> RapidAPI Kiwi
```

호텔:

```text
frontend
  -> /api/hotels/search
  -> backend/app/api/routes/hotels.py
  -> backend/app/services/booking_service.py
  -> RapidAPI Booking
```

항공권/호텔 추천형 요청은 OpenAI를 사용해 자연어 검색 조건을 파싱하고, 검색 결과를 랭킹할 수 있다.

관련 파일:

- `backend/app/services/llm_service.py`
- `backend/app/services/flight_recommend_service.py`
- `backend/app/services/hotel_recommend_service.py`

## Agent 응답 데이터 모양

로컬 agent의 기본 응답은 `AgentRunResponse` 형태이다.

주요 필드는 다음과 같다.

```text
status
intent
trip_id
data
clarify
```

새 일정 생성에서는 최종적으로 백엔드가 agent 응답을 다음 payload로 변환한다.

```text
{
  "trip": {
    "trip_title": "...",
    "prompt": "...",
    "start_date": "...",
    "end_date": "...",
    "total_days": 4,
    "style_tags": [...],
    "status": "generated",
    "route_summary": "...",
    "planning_brief": {...},
    "constraint_validation": {...}
  },
  "itinerary_days": [...],
  "budget": {...},
  "planning_brief": {...},
  "selected_blueprints": [...],
  "_plan_source": {...}
}
```

## 중요한 특징

현재 agent의 중요한 특징은 다음과 같다.

1. LLM 단발 생성이 아니다.
   - LLM은 자연어를 구조화하는 데 쓰이고, 이후 규칙, blueprint, route optimizer, validator가 개입한다.

2. Planning Brief가 중심이다.
   - 사용자 말의 의미를 Planning Brief로 구조화하고, 이후 모든 단계가 이 명세를 기준으로 움직인다.

3. Day blueprint로 하루의 리듬을 먼저 잡는다.
   - 미술관 중심, 야경 중심, 카페 중심, 느린 여행 등 서로 다른 하루 구조를 선택한다.

4. 장소 데이터와 동선을 실제로 보강한다.
   - 장소 카탈로그, Google Places, route optimizer를 통해 실제 표시 가능한 itinerary item을 만든다.

5. 조건 검증과 재계획이 있다.
   - 생성된 일정이 사용자 조건을 만족하지 않으면 재계획한다.

6. 결과와 검증 정보가 함께 저장된다.
   - MongoDB에는 일정뿐 아니라 Planning Brief, constraint validation, agent explanation, agent trace도 저장된다.

## 현재 운영상 참고점

- 일정 생성은 route optimization과 validation/replan 때문에 오래 걸릴 수 있다.
- 프론트는 `/api/trips/generate/jobs`로 생성 job을 시작하고 `/api/trips/generate/jobs/{job_id}`를 polling해 진행 상태를 보여준다.
- Docker 프론트의 nginx `/api` proxy timeout은 긴 일정 생성을 고려해 `300s`로 설정되어 있다.
- 프론트 API 클라이언트는 HTML/비JSON 응답이 와도 JSON parse error 대신 읽을 수 있는 에러를 표시하도록 보강되어 있다.
- 항공권 검색은 `destination=paris` 같은 도시명과 `destination=CDG` 같은 IATA 코드 직접 입력을 모두 처리한다.

## 핵심 파일 지도

```text
backend/app/api/routes/trips.py
  - 여행 생성/수정 API 진입점.

backend/app/services/agent_service.py
  - 백엔드 agent 흐름의 중심.
  - 외부 agent, 로컬 agent, fallback planner 선택.
  - Planning Brief 기반 최적화, 검증, 재계획 연결.

backend/app/services/planning_brief_service.py
  - Planning Brief 생성, 추출, 검증, 재계획 history 관리.

backend/app/services/route_optimizer_service.py
  - 날짜별 동선 최적화, route leg 부착, 이동 부담 계산.

backend/app/services/trip_service.py
  - MongoDB 저장/조회/수정/삭제.

parser_api/services/agent_service.py
  - 로컬 agent FastAPI/MCP 스타일 진입점.

parser_api/services/orchestration_service.py
  - intent 분류 후 parser/executor 실행.
  - ASK, DONE, ERROR, REQUEST_BUNDLE 처리.

parser_api/parsers/create_plan/parser.py
  - 새 일정 생성 자연어 parser.

parser_api/parsers/llm.py
  - OpenAI structured JSON 호출.

parser_api/services/place_catalog.py
  - day blueprint 선택, 장소 카탈로그 기반 itinerary 생성.

parser_api/intents.py
  - agent가 이해하는 intent 목록.

parser_api/executors/registry.py
  - intent별 executor 연결.
```
