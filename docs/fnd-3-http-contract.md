# FND-3 HTTP 계약과 운영 기준

기준은 FND-2 통합 커밋 `df3ca9a`의 React/CLI 사용 계약이다. `react_server.py`는 업무 함수와 요청별 정책을 유지하고 `api_test/asgi.py`가 FastAPI route, 오류 응답과 thread pool 경계를 구성한다. `StudioHandler`와 API 서버의 `ThreadingHTTPServer`는 제거했다. 별도 암호화 서비스의 HTTP 서버는 이 전환 범위에 포함하지 않는다.

## 계약 matrix

| Method | Path | 정상 응답 | 오류·특수 계약 | 검증 |
| --- | --- | --- | --- | --- |
| GET | `/api/projects`, `/api/cases`, `/api/pipelines` | 200, `items` 및 기존 `details` | project 필터·Example 노출 설정, collection trailing slash 유지 | TestClient |
| GET | `/api/{kind}/{reference}` | 200, 문서와 `_storage` | 없는 문서 400 `error`; 일반 secret masking, Example 공개 fixture 예외 유지 | TestClient |
| GET | `/api/{kind}/{reference}/revisions` | 200, `items` | greedy document route보다 먼저 등록 | TestClient·실제 HTTP |
| PUT | `/api/{kind}/{reference}` | 200, `path`, `_storage` | stale/missing revision 409 및 `currentRevision`; Example 변경 400 | TestClient |
| DELETE | `/api/{kind}/{reference}` | 200, `deleted`, `deleted_pipelines` | case가 남은 project 삭제 400; Example 변경 400 | TestClient |
| GET | `/api/dashboard` | 200, 기존 metadata 집계 | 잘못된 days/status/page 400, body·header·credential·실행 출력 저장 금지 유지 | TestClient·React |
| POST | `/api/docs` | 200, `operations` | URL/document/bundle 중 하나, 잘못된 JSON·타입 400 | 이전 테스트의 TestClient 전환·실제 HTTP |
| POST | `/api/projects/{reference}/openapi/operations` | 200, `operation`, `_storage` | revision 충돌 409, Example 변경 400 | TestClient |
| POST | `/api/generate` | 200, ZIP bytes | `application/zip`, attachment filename, Content-Length, 생성 timeout 504 | TestClient·Docker 실제 Generator |
| POST | `/api/request` | 200, 대상 status/headers/body/rawBody/elapsedMs | 대상 4xx/5xx도 wrapper 200, network 502/504, 정책 거부 403 | TestClient·React |
| POST | `/api/run` | 200, runId/exitCode/output | 미저장 preview, 잘못된 배열 400, timeout 504와 runId; metadata 저장 유지 | TestClient·실제 subprocess·React |
| POST | `/api/uploads/{reference}` | 200, `path` | raw bytes, 1 byte–25 MB, `case/{tag}/{api}/files` 경계; 크기 초과/빈 body 400 | TestClient·실제 HTTP |
| GET | `/api/ownership` | 200, 기존 status | 새 세션 cookie: Path=/, HttpOnly, SameSite=Strict; 기존 cookie 재사용 | TestClient |
| POST | `/api/ownership/{action}` | 기존 issue/verify/grant/remove-grant 응답 | 동일 출처·세션·운영자 승인 키, 거부 403 `OWNERSHIP_POLICY_DENIED` | TestClient 및 기존 ownership 서비스 테스트 |
| GET/POST | `/example-api/...` | health/user 200, 사용자 생성 201 | API key 누락·불일치 401, 비활성화·없는 endpoint 404 | TestClient·실제 HTTP·React |
| GET | SPA 및 정적 자산 | 기존 dist 파일, 없는 경로는 index.html | 빌드 없음 404 JSON, dist 밖 경로는 SPA fallback | TestClient·실제 HTTP·React |
| POST/PUT/DELETE | 알 수 없는 endpoint | — | 기존 `Unknown run/save/delete endpoint` 400 | TestClient·실제 HTTP |

JSON 응답은 `application/json; charset=utf-8`, `Cache-Control: no-store`, UTF-8 byte 길이의 Content-Length를 유지한다. 오류는 `detail` 대신 기존 `error`를 사용한다. FastAPI `RequestValidationError`도 명시적으로 400에 매핑한다. 잘못된 UTF-8 body는 기존 서버 연결 오류 대신 400 `Invalid request JSON`으로 처리한다.

reference는 `{reference:path}`로 등록한다. React가 보내던 `%2F` 인코딩 경로를 유지하며, 인코딩하지 않은 중첩 경로도 지원한다. revision/OpenAPI suffix route가 일반 document route보다 먼저 매칭된다. 경로 응답은 운영체제에 관계없이 `/` 구분자를 사용한다.

전환 대상 업무 메서드는 GET/POST/PUT/DELETE이다. 기존 `SimpleHTTPRequestHandler`의 부수적인 HEAD 정적 파일 동작은 업무 API 계약으로 채택하지 않는다. 별도 등록하지 않은 HEAD/PATCH/OPTIONS는 FastAPI 기본 405 응답을 사용한다. 브라우저의 같은 출처 호출에는 CORS preflight가 필요하지 않으며 외부 CORS 허용은 추가하지 않았다.

## 실행과 동시성

- `python3 react_server.py` 또는 `python3 -m react_server`: `API_TEST_HOST`(기본 127.0.0.1), `API_TEST_PORT`(기본 8765)를 사용하는 Uvicorn **1 worker**.
- Docker도 같은 entry point를 사용한다. `LOCAL_SERVER=true`이면 loopback 외 bind를 거부한다. proxy header 신뢰는 끈다.
- SQLite·파일·SDK/테스트 subprocess 작업은 thread pool에서 실행해 ASGI event loop를 막지 않는다. 다중 worker/replica, queue, PostgreSQL, Redis, 로그인/RBAC 도입은 포함하지 않는다.
- `/api/schema.json`은 내부 route schema를 제공한다. 자동 Swagger/Redoc 화면은 비활성화하여 기존 SPA 경로를 보존한다. 상세 문서 모델 검증은 기존 업무 검증 함수를 사용한다.
- raw upload는 chunked 전송도 수신 중 크기를 제한하고, 유효성 확인 후 파일을 기록한다.

## 검증 증거 (2026-09-14)

- macOS Python 3.13 및 Docker Python 3.12에서 각각 전체 Python 166개 통과: 기존 152개 회귀와 신규 HTTP 계약 14개. 모든 API handler 직접 호출 테스트를 TestClient 요청으로 전환했다. 외부 네트워크·SDK 비용 작업은 필요한 테스트에서만 mock하고, 실제 전송·생성은 아래 별도 검증했다.
- frontend 8개와 Vite production build 통과. React 소스 변경 없음.
- `df3ca9a` 기존 서버와 신규 서버를 별도 임시 데이터·loopback 포트에서 실행해 실제 HTTP 13개 비교: status 및 JSON/본문 일치. revision 목록은 매 실행 달라지는 UUID/시각을 제외한 응답 구조를 비교했다.
- 실제 `/api/run` → 예제 pipeline 200→401→200, 3개 PASS, exitCode 0, runId 기록.
- React 브라우저에서 빠른 호출 200, Example 목록/중첩 케이스 열기, 미저장 케이스 실행 PASS, dashboard 이력 2건·성공률 100% 표시 확인.
- Dockerfile.api 빌드 및 격리 Compose API 컨테이너에서 원래 Compose의 동일 healthcheck 사용, healthy 확인. Java/OpenAPI Generator로 Python SDK ZIP 32개 entry 생성 및 ZIP 무결성 검사 통과. 기존 운영 Compose 서비스는 교체하지 않았다.
- 테스트 과정의 임시 경로 실패는 macOS `/var`→`/private/var` fixture 정규화로 해결했고, 동일 내용 저장 시 revision이 증가하지 않는 기존 계약에 맞춰 갱신 테스트에 실제 변경값을 넣었다.
- sandbox의 Git metadata/Docker socket/loopback 제한은 허용된 재실행으로 해소했다. 이미지 metadata 조회 지연도 빌드 완료로 해소했다.

FastAPI의 [경로 변환과 등록 순서](https://fastapi.tiangolo.com/tutorial/path-params/) 및 [예외 handler 재정의](https://fastapi.tiangolo.com/tutorial/handling-errors/)를 적용했다.
