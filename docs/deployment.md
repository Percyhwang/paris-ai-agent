# CI/CD 배포 설정

이 저장소는 GitHub Actions로 테스트, Docker 이미지 발행, Docker 서버 배포를 수행하도록 구성되어 있습니다.

## 동작 방식

- `main` 브랜치에 push되거나 Actions에서 수동 실행하면 `CI/CD` 워크플로가 실행됩니다.
- 프론트엔드는 `npm ci`와 `npm run build`로 검증합니다.
- 백엔드와 `parser_api`는 `unittest` discovery로 검증합니다.
- 검증이 끝나면 backend/frontend Docker 이미지를 GHCR에 발행합니다.
- SSH 배포용 GitHub Secrets가 있으면 원격 서버에서 `docker-compose.prod.yml`을 pull/up 합니다.
- SSH 배포용 Secrets가 없으면 이미지 발행까지만 수행하고 배포 단계는 건너뜁니다.

## 필수 GitHub Secrets

서버 배포까지 자동화하려면 repository Settings > Secrets and variables > Actions에 아래 값을 추가합니다.

- `DEPLOY_HOST`: Docker가 설치된 서버 주소
- `DEPLOY_USER`: SSH 접속 사용자
- `DEPLOY_SSH_KEY`: 위 사용자의 private key

서버 사용자는 `docker compose`를 실행할 수 있어야 합니다.

## 권장 Secrets

- `DEPLOY_PATH`: 서버 배포 경로. 기본값은 `/opt/paris-ai-agent`
- `FRONTEND_PORT`: 외부 공개 포트. 기본값은 `80`
- `BACKEND_PORT`: backend 직접 접근 포트. 기본값은 `127.0.0.1:8010`
- `FRONTEND_ORIGIN`: 실제 프론트엔드 origin. 비워두면 `http://DEPLOY_HOST`
- `GHCR_USERNAME`: private GHCR package를 pull할 사용자
- `GHCR_TOKEN`: `read:packages` 권한이 있는 token

## 앱 환경 변수 Secrets

필요한 API만 채우면 됩니다. 비워둔 값은 코드의 fallback 또는 비활성 상태로 동작합니다.

- `VITE_GOOGLE_CLIENT_ID`
- `VITE_GOOGLE_ALLOWED_ORIGINS`
- `VITE_GOOGLE_MAPS_API_KEY`
- `VITE_HOME_BACKGROUND_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_PLACES_API_KEY`
- `ENABLE_GOOGLE_FOOD_SEARCH`
- `GOOGLE_ROUTES_API_KEY`
- `JWT_PRIVATE_KEY`
- `JWT_PUBLIC_KEY`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `WEATHER_API_URL`
- `WEATHER_CACHE_TTL_MINUTES`
- `EXTERNAL_AGENT_API_URL`
- `LLM_DIARY_API_URL`
- `OPENAI_API_KEY`
- `RAPIDAPI_KEY`
- `KIWI_RAPIDAPI_HOST`
- `BOOKING_RAPIDAPI_HOST`

`JWT_PRIVATE_KEY`와 `JWT_PUBLIC_KEY`는 줄바꿈을 `\n`으로 치환한 한 줄 문자열로 저장할 수 있습니다.
