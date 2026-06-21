# CI/CD 배포 설정

이 저장소는 GitHub Actions로 테스트, Docker 이미지 빌드, GHCR 푸시, Docker 호스트 배포를 수행합니다.

## 동작 방식

- `main` 브랜치에 push하거나 Actions에서 수동 실행하면 `CI/CD` workflow가 실행됩니다.
- frontend는 `npm ci`와 `npm run build`로 검증합니다.
- backend와 parser API는 `unittest`로 검증합니다.
- 검증이 끝나면 backend/frontend Docker 이미지를 GitHub Container Registry(GHCR)에 push합니다.
- 배포 단계는 `DEPLOY_HOST`로 SSH 접속해 `docker-compose.prod.yml`을 pull/up 합니다.
- `WG_CONFIG` Secret이 있으면 먼저 WireGuard VPN을 올린 뒤 SSH 접속을 시도합니다.

## 필수 GitHub Secrets

Repository Settings > Secrets and variables > Actions에 아래 값을 등록해야 합니다.

- `DEPLOY_HOST`: Docker 배포 서버 주소입니다. 예: `10.0.0.1` 또는 `ssh.example.com`
- `DEPLOY_USER`: SSH 접속 사용자입니다.
- `DEPLOY_SSH_KEY`: 해당 사용자로 접속 가능한 private key입니다.

## 선택 GitHub Secrets

- `DEPLOY_PORT`: SSH 포트입니다. 비워두면 `22`를 사용합니다.
- `DEPLOY_PATH`: 서버의 배포 경로입니다. 비워두면 `/opt/paris-ai-agent`를 사용합니다.
- `WG_CONFIG`: WireGuard를 통해 서버에 접속해야 할 때 사용하는 클라이언트 설정입니다.
- `FRONTEND_PORT`: 외부에 공개할 frontend 포트입니다. 비워두면 `80`을 사용합니다.
- `BACKEND_PORT`: backend 포트 바인딩입니다. 비워두면 `127.0.0.1:8010`을 사용합니다.
- `FRONTEND_ORIGIN`: 실제 frontend origin입니다. 예: `http://10.0.0.1:4173`
- `GHCR_USERNAME`: private GHCR 이미지를 pull할 사용자명입니다.
- `GHCR_TOKEN`: `read:packages` 권한이 있는 토큰입니다.

## 애플리케이션 환경 Secrets

필요한 API만 채우면 됩니다. 비어 있는 값은 코드의 fallback 또는 비활성 상태로 동작합니다.

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

`JWT_PRIVATE_KEY`와 `JWT_PUBLIC_KEY`는 줄바꿈을 `\n`으로 치환한 문자열로 저장해도 됩니다.

## 현재 배포 실패를 확인하는 방법

배포 job에서 WireGuard가 올라간 뒤 `transfer: 0 B received`가 보이거나 `SSH was not reachable`가 나오면 GitHub Actions 문제가 아니라 배포 서버 네트워크 문제입니다.

이 경우 서버에서 아래를 확인해야 합니다.

- WireGuard 서버가 실행 중이고 UDP `51820`이 열려 있는지
- 서버 WireGuard 설정에 GitHub Actions용 peer가 등록되어 있는지
- 서버에서 `10.0.0.1` 같은 내부 VPN 주소가 실제로 붙어 있는지
- `sshd`가 실행 중이고 `DEPLOY_PORT`로 접속 가능한지
- 방화벽이 VPN 클라이언트에서 SSH 포트로 들어오는 연결을 허용하는지
