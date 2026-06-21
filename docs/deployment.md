# CI/CD 배포 설정

이 저장소는 GitHub Actions로 테스트, Docker 이미지 빌드, GHCR 푸시, GitHub Pages 배포, 그리고 원격 서버 full-stack 배포를 수행합니다.

## 현재 배포 방식

- `main` 브랜치에 push하거나 Actions에서 수동 실행하면 `CI/CD` workflow가 실행됩니다.
- frontend는 `npm ci`와 `npm run build`로 검증합니다.
- backend와 parser API는 `unittest`로 검증합니다.
- 검증이 끝나면 backend/frontend Docker 이미지를 GitHub Container Registry(GHCR)에 push합니다.
- 마지막 단계에서 frontend 정적 빌드 결과물을 GitHub Pages에 배포합니다.
- `Server Deployment` workflow가 이어서 원격 서버에 frontend/backend/mongo 컨테이너를 배포합니다.

## 배포 URL

GitHub Pages 배포가 성공하면 아래 URL로 접속할 수 있습니다.

```text
https://percyhwang.github.io/paris-ai-agent/
```

## 주의 사항

GitHub Pages는 정적 파일 호스팅만 지원합니다. 따라서 full-stack 동작은 `Server Deployment` workflow가 SSH로 배포하는 원격 서버에서 담당합니다.

GitHub Pages가 live API를 바라보게 하려면 Repository Secrets에 `PUBLIC_API_BASE_URL`을 공개 HTTPS API 주소로 설정하는 것이 가장 안전합니다. 이 값이 없으면 workflow는 내부망 주소를 사용하지 않고 공개 주소만 선택하려고 시도합니다.

## GitHub Actions 구성

현재 workflow는 다음 job으로 구성됩니다.

- `Test and build`: frontend/backend/parser 테스트와 빌드 검증
- `Build and publish images`: backend/frontend Docker 이미지를 GHCR에 push
- `Deploy frontend to GitHub Pages`: frontend를 GitHub Pages에 배포
- `Server Deployment`: GHCR 이미지를 원격 서버로 내려받아 frontend/backend/mongo를 함께 기동

## 선택 Secrets

frontend 빌드에 필요한 값이 있으면 Repository Settings > Secrets and variables > Actions에 추가합니다.

- `VITE_API_BASE_URL`
- `VITE_GOOGLE_CLIENT_ID`
- `VITE_GOOGLE_ALLOWED_ORIGINS`
- `VITE_GOOGLE_MAPS_API_KEY`
- `VITE_HOME_BACKGROUND_URL`
- `PUBLIC_API_BASE_URL`

원격 서버 배포에 필요한 값은 아래와 같습니다.

- `DEPLOY_HOST`
- `DEPLOY_PORT`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PATH`
- `GHCR_READ_TOKEN` 또는 `GHCR_TOKEN`
