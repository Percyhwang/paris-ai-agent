## Parser API

`parser_api`는 자연어 여행 요청을 `CREATE_PLAN` 또는 `MODIFY_PLAN` 스키마로 변환하는 FastAPI 기반 파서 서비스입니다.

### 현재 구조

- `main.py`: FastAPI 앱 엔트리포인트
- `router.py`: HTTP 레이어
- `services/agent_service.py`: intent 분기, parser 호출, 응답 조립
- `services/trip_store.py`: MVP in-memory 저장소와 MCP stub
- `parsers/`: intent classifier, LLM 호출, intent별 parser 규칙
- `tests/`: 회귀 테스트와 서비스 테스트

### 설치

루트에서:

```bash
parser_api/.venv/bin/pip install -r parser_api/requirements.txt
```

또는 `parser_api` 디렉터리에서:

```bash
pip install -r requirements.txt
```

### 실행

루트에서:

```bash
parser_api/.venv/bin/uvicorn parser_api.main:app --reload
```

기본 주소는 `http://127.0.0.1:8000`입니다.

### 테스트

루트에서:

```bash
parser_api/.venv/bin/python -m unittest parser_api.tests.test_parser_regressions parser_api.tests.test_agent_service
```

### 엔드포인트

`POST /agent/run`

예시 요청:

```json
{
  "message": "파리 3박 4일 일정 만들어줘. 카페 많이, 걷기는 적게.",
  "context": {}
}
```

예시 응답:

```json
{
  "status": "ASK | DONE | ERROR",
  "intent": "CREATE_PLAN",
  "trip_id": "",
  "data": {},
  "clarify": {
    "needed": false,
    "missing_fields": []
  }
}
```

### LLM 처리 방식

- 현재 구현은 OpenAI Chat Completions API의 `json_object` 응답 형식을 사용합니다.
- 응답은 `normalize` 단계에서 보정한 뒤 Pydantic으로 검증합니다.
- 검증 또는 호출 실패 시 최대 1회 재시도합니다.
- 2회 모두 실패하면 규칙 기반 fallback으로 기본 payload를 만든 뒤 후처리합니다.

### 규칙 처리 방식

- `create_plan`과 `modify_plan`은 각각 `normalize`, `parser`, `rules`를 기준으로 동작합니다.
- 큰 규칙 파일은 날짜, 인원, 선호도, operation 추론 모듈로 분리되어 있습니다.
- 공통 토큰과 정규식은 `parsers/common/` 아래에서 공유합니다.
