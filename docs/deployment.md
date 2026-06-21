# CI/CD 배포 설정

이 저장소는 GitHub Actions로 테스트, Docker 이미지 빌드, GHCR 푸시, GitHub Pages 배포를 수행합니다.

## 현재 배포 방식

- `main` 브랜치에 push하거나 Actions에서 수동 실행하면 `CI/CD` workflow가 실행됩니다.
- frontend는 `npm ci`와 `npm run build`로 검증합니다.
- backend와 parser API는 `unittest`로 검증합니다.
- 검증이 끝나면 backend/frontend Docker 이미지를 GitHub Container Registry(GHCR)에 push합니다.
- 마지막 단계에서 frontend 정적 빌드 결과물을 GitHub Pages에 배포합니다.

## 배포 URL

GitHub Pages 배포가 성공하면 아래 URL로 접속할 수 있습니다.

```text
https://percyhwang.github.io/paris-ai-agent/
```

## 주의 사항

GitHub Pages는 정적 파일 호스팅만 지원합니다. 따라서 frontend 화면은 배포할 수 있지만, FastAPI backend와 MongoDB를 계속 실행해주는 서버는 아닙니다.

backend와 DB까지 완전히 외부에서 동작하게 하려면 Render, Railway, Fly.io 같은 별도 호스팅 서비스와 MongoDB Atlas 같은 외부 DB가 필요합니다.

## GitHub Actions 구성

현재 workflow는 다음 job으로 구성됩니다.

- `Test and build`: frontend/backend/parser 테스트와 빌드 검증
- `Build and publish images`: backend/frontend Docker 이미지를 GHCR에 push
- `Deploy frontend to GitHub Pages`: frontend를 GitHub Pages에 배포

## 선택 Secrets

frontend 빌드에 필요한 값이 있으면 Repository Settings > Secrets and variables > Actions에 추가합니다.

- `VITE_API_BASE_URL`
- `VITE_GOOGLE_CLIENT_ID`
- `VITE_GOOGLE_ALLOWED_ORIGINS`
- `VITE_GOOGLE_MAPS_API_KEY`
- `VITE_HOME_BACKGROUND_URL`

backend Docker 이미지 실행에 필요한 값은 실제 backend 호스팅 서비스를 붙일 때 설정합니다.
