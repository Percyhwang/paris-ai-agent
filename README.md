# Paris AI Agent Web Platform

React + FastAPI + MongoDB 기반의 파리 여행 전용 AI Agent 웹 서비스입니다. 현재 구현은 AI agent 자체보다 웹 서비스, 서버, 데이터 저장 흐름, 외부 agent/LLM/API 교체가 쉬운 service layer에 초점을 둡니다.

## Structure

```text
frontend/  React, routing, service API layer, Paris travel UI
backend/   FastAPI, MongoDB, Google OAuth verification, RSA JWT auth
```

## Quick Start

1. 환경 파일을 준비합니다.

```bash
cp .env.example .env
```

2. MongoDB를 실행합니다.

```bash
docker compose -p paris-ai-agent up -d mongo
```

3. 백엔드를 실행합니다.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

4. 프론트엔드를 실행합니다.

```bash
cd frontend
npm install
npm run dev
```

## Authentication Notes

- 실제 Google 로그인을 사용하려면 `GOOGLE_CLIENT_ID`와 `VITE_GOOGLE_CLIENT_ID`를 설정하세요.
- 로컬 개발 편의를 위해 `ALLOW_INSECURE_DEV_AUTH=true`일 때 프론트엔드의 데모 로그인 버튼이 동작합니다.
- JWT는 RS256으로 서명/검증합니다. 운영 환경에서는 `.env`에 고정 RSA private/public key를 반드시 넣어야 합니다.

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
- `GET/PUT /api/trips/{trip_id}/itinerary`
- `GET/PUT /api/trips/{trip_id}/budget`
- `POST /api/trips/{trip_id}/budget/items`
- `DELETE /api/trips/{trip_id}/budget/items/{item_id}`
- `GET/POST /api/trips/{trip_id}/reservations`
- `GET/POST /api/trips/{trip_id}/diary`
- `POST /api/trips/{trip_id}/diary/generate`
- `GET /api/places`
- `GET /api/places/{place_id}`
- `GET /api/weather/paris`
- `GET /api/weather/paris/forecast`

MongoDB collection details are documented in `docs/mongodb-schema.md`.
