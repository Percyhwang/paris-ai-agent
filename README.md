# Paris AI Agent Web Platform

React + FastAPI + MongoDB 기반의 파리 여행 전용 AI Agent 웹 서비스입니다. 여행 계획 생성, Agent 기반 일정 수정, 동선 최적화, 예산 계산, 장소 검색, 날씨, 여행 기록 UI를 한 흐름으로 연결하는 데 초점을 둡니다.

## Structure

```text
frontend/   React, routing, Paris travel UI, trip plan map/list views
backend/    FastAPI, MongoDB, auth, trip generation, route/budget services
parser_api/ Local intent parser, itinerary catalog, MCP tool registry
docs/       MongoDB schema and project notes
```

## Recent Updates

- 여행 플랜에서 저장된 여행을 선택, Agent로 수정, 삭제할 수 있습니다.
- `POST /api/trips/{trip_id}/agent-modify`로 자연어 일정 수정 요청을 처리합니다.
- "1일차 점심을 파스타 맛집으로 바꿔줘" 같은 요청은 동선 주변 음식점 후보를 찾고, Google Places rating/review count가 있으면 우선순위에 반영합니다.
- 일정 생성은 하루 4개 고정이 아니라 여행 템포에 따라 조절됩니다.
  - `slow`/힐링: 여유 있는 3개 내외
  - `normal`: 5개 내외
  - `fast`/알차게: 7개 내외
- 같은 장소가 같은 날 또는 여러 날 반복되지 않도록 이름, place id, 좌표 기준 중복 방지를 강화했습니다.
- 관광지 입장료를 일정 기반으로 자동 합산해 예산에 반영합니다.
- 여행 플랜의 Google 지도 영역에 일차별 동선 오버레이와 번호 마커를 표시합니다.
- `Google Maps로 보기` 링크는 실제 Google Maps 길찾기 화면으로 연결합니다.
- 일정 장소 이름을 누르면 Google 검색으로 장소 정보를 확인할 수 있습니다.
- 예약 체크 페이지는 프론트 내비게이션에서 제거했습니다.
- 숙소 검색(`/accommodations`)과 항공권 검색(`/flights`) 페이지를 추가했습니다. 현재는 API 연결 전 조건 정리 UI입니다.
- `parser_api`에 `google_maps_route` MCP 서버를 추가했습니다.

## Quick Start

1. 환경 파일을 준비합니다.

```bash
cp .env.example .env
```

2. MongoDB를 실행합니다.

```bash
docker compose -p paris-ai-agent up -d mongo
```

도커로 전체 스택을 실행하려면:

```bash
docker compose up --build -d
```

기본 주소:

- Frontend: `http://localhost:4173`
- Backend health: `http://localhost:8010/health`

3. 백엔드를 실행합니다.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Windows PowerShell 예시:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

4. 프론트엔드를 실행합니다.

```bash
cd frontend
npm install
npm run dev
```

기본 주소:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000/api`

## CI/CD

이 저장소는 GitHub Actions 기반 `CI/CD` 파이프라인을 포함합니다.

- CI
  - `pull_request`와 모든 `push`에서 자동 실행
  - Python deterministic test 실행
  - Frontend build 검증
  - Backend/Frontend Docker image build 검증
  - MongoDB까지 포함한 full stack smoke test 실행
- CD
  - `main` 브랜치 push 시 자동 실행
  - Backend/Frontend 이미지를 `GHCR`에 publish
  - 배포 서버 SSH secret이 설정되어 있으면 Frontend + Backend + MongoDB 스택을 원격 서버에서 `docker compose pull && up -d`로 자동 갱신

워크플로 파일:

- `.github/workflows/ci-cd.yml`

배포용 파일:

- `infra/docker-compose.prod.yml`
- `scripts/deploy_remote.sh`
- `env.production.example`

기본 배포 구성은 `infra/docker-compose.prod.yml` 안에 `mongo` 서비스를 포함합니다. Atlas 같은 외부 MongoDB를 쓰고 싶다면 서버의 `.env`에서 `MONGODB_URI`만 바꿔주면 됩니다.

### GitHub Secrets

이미지 publish와 서버 배포를 위해 아래 secret 구성을 권장합니다.

- `VITE_GOOGLE_CLIENT_ID`
- `VITE_GOOGLE_ALLOWED_ORIGINS`
- `VITE_GOOGLE_MAPS_API_KEY`
- `VITE_HOME_BACKGROUND_URL`
- `DEPLOY_HOST`
- `DEPLOY_PORT`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PATH`
- `GHCR_READ_TOKEN`

`GHCR_READ_TOKEN`은 원격 서버가 `ghcr.io` 이미지를 pull 할 수 있도록 `read:packages` 권한이 있는 GitHub Personal Access Token을 사용하면 됩니다.

### Remote Server Setup

원격 서버에는 Docker와 Docker Compose plugin이 설치되어 있어야 하며, 배포 전에 아래 준비가 필요합니다.

1. 배포 경로 예시: `/opt/paris-ai-agent`
2. `env.production.example`을 참고해 서버에 `/opt/paris-ai-agent/.env` 생성
3. `main` 브랜치 push 후 GitHub Actions의 `Deploy to Remote Server` job 확인

제출 시에는 아래 항목을 함께 적으면 됩니다.

- GitHub repo URL
- GitHub Actions 실행 화면
- 배포 URL
- `GHCR + Docker Compose + SSH` 기반 자동 배포 구조 설명

## Required And Optional APIs

### Required For Local Core Flow

- MongoDB
  - `MONGODB_URI`
  - `MONGODB_DB`
  - 여행, 일정, 예산, 일기, 장소 seed 데이터를 저장합니다.

### Google Login

- Google OAuth Client ID
  - Backend: `GOOGLE_CLIENT_ID`
  - Frontend: `VITE_GOOGLE_CLIENT_ID`
  - Frontend allowed origins: `VITE_GOOGLE_ALLOWED_ORIGINS`
- 로컬 개발에서는 `ALLOW_INSECURE_DEV_AUTH=true`이면 dev login을 사용할 수 있습니다.

### Google Places API

- 환경 변수: `GOOGLE_PLACES_API_KEY`
- Google Cloud에서 사용할 API: `Places API (New)`
- 사용 위치:
  - 파리 장소 검색 및 상세 정보
  - 장소 사진 proxy
  - 음식점/카페 교체 추천
  - rating, user rating count 기반 맛집 우선순위
- 음식점 Agent 수정 기능 스위치:
  - `ENABLE_GOOGLE_FOOD_SEARCH=true`
- 권장 제한:
  - 백엔드 서버용 API key는 HTTP referrer 제한보다 IP 제한을 권장합니다.
  - Google Cloud Console에서 quota, budget alert, API restriction을 설정하세요.

### Google Routes API

- 환경 변수: `GOOGLE_ROUTES_API_KEY`
- Google Cloud에서 사용할 API: `Routes API`
- 사용 위치:
  - 일정 장소 사이 이동 시간
  - 도보/대중교통 구간 요약
  - `route_to_next` 이동 정보
- 키가 없거나 요청이 실패하면 앱은 직선거리 기반 fallback 이동 정보를 사용합니다.

### Google Maps Display

- 현재 여행 플랜 지도는 iframe 지도 + 앱 자체 SVG 동선 오버레이를 사용합니다.
- `Google Maps로 보기`는 Google Maps directions 링크를 사용합니다.
- 현재 코드 기준으로 여행 플랜 지도 표시에는 `VITE_GOOGLE_MAPS_API_KEY`가 필수는 아닙니다.
- 향후 Google Maps JavaScript API 또는 Static Maps API로 바꾸면 `VITE_GOOGLE_MAPS_API_KEY`가 필요합니다.

### Weather

- 기본값은 Open-Meteo forecast API이며 별도 API key가 필요 없습니다.
- 다른 날씨 API를 쓰려면 `WEATHER_API_URL`로 교체할 수 있습니다.

### Booking.com API

- 아직 연결 전입니다.
- 숙소 검색 페이지(`/accommodations`)는 Booking.com API 연결을 위한 준비 UI입니다.
- 추후 필요한 값:
  - Booking.com 또는 제휴 provider API key
  - 숙소 검색 endpoint
  - 요금/가용성/지역/체크인/체크아웃 schema

### Kayak API

- 아직 연결 전입니다.
- 항공권 검색 페이지(`/flights`)는 Kayak API 연결을 위한 준비 UI입니다.
- 추후 필요한 값:
  - Kayak 또는 제휴 flight search provider API key
  - 항공권 검색 endpoint
  - 출발지/도착지/날짜/인원/좌석등급 schema

### Optional Agent And LLM APIs

- `EXTERNAL_AGENT_API_URL`
  - 비워두면 로컬 parser/orchestrator를 사용합니다.
  - 외부 Agent 서버를 붙일 때 사용합니다.
- `OPENAI_API_KEY`
  - `parser_api`의 LLM 기반 structured parser를 사용할 때 필요합니다.
  - 없으면 rule-based parser/fallback 흐름을 사용합니다.
- `LLM_DIARY_API_URL`
  - 여행 일기 생성 외부 LLM API를 붙일 때 사용합니다.

## Cost Notes

Google Places API와 Google Routes API는 호출량에 따라 과금될 수 있습니다.

권장 설정:

- Google Cloud Billing budget과 alert 설정
- API별 quota 제한
- Places API, Routes API만 허용하는 API restriction
- 백엔드 서버 IP 기반 key restriction
- 개발/운영 key 분리

## Authentication Notes

- 실제 Google 로그인을 사용하려면 `GOOGLE_CLIENT_ID`와 `VITE_GOOGLE_CLIENT_ID`를 설정하세요.
- 로컬 개발에서는 `ALLOW_INSECURE_DEV_AUTH=true`로 dev login을 사용할 수 있습니다.
- JWT는 RS256으로 서명/검증합니다.
- 운영 환경에서는 `.env`에 고정 RSA private/public key를 설정해야 합니다.

## API Envelope

모든 API 응답은 아래 형태를 따릅니다.

```json
{
  "success": true,
  "data": {},
  "message": "OK",
  "error": null
}
```

## Main Endpoints

- `POST /api/auth/google/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
- `GET/PATCH /api/users/me`
- `POST /api/trips/generate`
- `POST/GET /api/trips`
- `GET/PATCH/DELETE /api/trips/{trip_id}`
- `POST /api/trips/{trip_id}/agent-modify`
- `GET/PUT /api/trips/{trip_id}/itinerary`
- `GET/PUT /api/trips/{trip_id}/budget`
- `POST /api/trips/{trip_id}/budget/items`
- `DELETE /api/trips/{trip_id}/budget/items/{item_id}`
- `GET/POST /api/trips/{trip_id}/diary`
- `POST /api/trips/{trip_id}/diary/generate`
- `GET /api/places`
- `GET /api/places/{place_id}`
- `GET /api/weather/paris`
- `GET /api/weather/paris/forecast`

예약 체크 페이지는 프론트에서 제거되었지만, 기존 backend reservations route는 legacy 호환용으로 남아 있을 수 있습니다.

## MCP Servers

`parser_api/mcp_servers`에는 로컬 orchestration에서 사용할 MCP 서버들이 있습니다.

- `google_maps_route`
  - tool: `build_day_route_map`
  - 일차별 itinerary items를 받아 Google Maps directions URL과 route points를 반환합니다.

MongoDB collection details are documented in `docs/mongodb-schema.md`.
