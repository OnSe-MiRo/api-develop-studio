# API 개발 기능 진행 기록

## FastAPI·PostgreSQL·Redis·Java WAS 개발 순서 계획 (2026-09-12)

- 상태: 완료 — 구현이 아닌 로드맵 문서 정리.
- 결정: FastAPI와 Uvicorn 전환으로 내부 업무 API 계약을 먼저 안정화하고, PostgreSQL 이관과 Redis cache-aside를 완료한 뒤 workspace 격리와 Java WAS 인증 BFF를 진행한다.
- 저장소 경계: PostgreSQL은 영구 데이터의 단일 기준이고 Redis는 재생성 가능한 일반 캐시다. secret과 원문 request/response를 Redis에 저장하지 않으며 일반 캐시 장애는 PostgreSQL fallback으로 처리한다.
- 사용자 저장 경계: provider subject는 내부 `user_id`에 연결하고 모든 협업 데이터는 `workspace_id`와 서버가 결정한 작성자 정보를 저장한다. 사용자·workspace·actor 값은 request body에서 받지 않는다.
- 인증 경계: Java WAS는 로그인·Redis session·CSRF·외부 RBAC를 담당하고 FastAPI는 업무 권한과 workspace query를 담당한다. FastAPI 직접 외부 접근과 두 계층의 중복 인증 구현은 허용하지 않는다.
- 순서: FND-2 migration·테스트 기반 → FND-3 FastAPI 전환 → FND-4 PostgreSQL·Redis → COL-2 workspace 격리 → COL-1 Java WAS·OIDC → 내부 서비스 인증 → 외부 포트 차단 → 종단 검증.
- 제한: PostgreSQL·Redis 이관과 Java WAS·인증 provider의 실제 도입은 시작하지 않았으며 사내 SSO·Spring Security 표준 확정 전까지 Java 기술 선택 상태는 대기다.

## 예제 정책 테스트 추가 (2026-09-11)

- 상태: 완료 — health Setup, API Key 누락 401, 유효한 예제 API Key 200 케이스와 `example-ownership-local.json` 추가.
- 기존 example 케이스와 프로젝트 설정은 보존. 소유권 생략과 API 요청 인증이 독립적인지 실제 예제 handler를 사용하는 전송 mock 테스트로 확인.
- 검증: 전체 Python 138개 및 git diff --check 통과. 새 예제의 200→401→200 통과와 생략 비활성화 시 첫 요청 전 차단 확인.
- 실제 HTTP: 기존 Docker와 분리한 `127.0.0.1:8877` 임시 서버에서 `example-ownership-local.json` 실행, 3단계 모두 PASS 및 exit code 0 확인.

## 소유권 검증 및 외부 Setup (2026-09-11)

- 상태: 완료 — `feature/ownership-verification` (로컬 구현, 커밋/병합/푸시 없음)
- 범위: 일회용 HTTPS 챌린지, 로컬 모드 생략, 30일 미사용/90일 절대 만료, 승인된 외부 Setup 1회 호출.
- 실행 경로: 웹/CLI 공통 정책 검사, 응답 값 전달 재사용, redirect 차단과 외부 재시도 금지.
- 변경: `api_test/ownership.py`의 SQLite 검증/승인 상태, CLI/웹 실행 검사, 프로젝트 설정 패널, 빠른 호출 프로젝트 선택, 파이프라인 외부 Setup UI, 운영 가이드 추가.
- 검증: 전체 Python 135개 통과(신규 정책 22개), Vite build, py_compile, git diff --check 통과.
- 브라우저: 임시 데이터로 설정 패널, 토큰 발급/응답 표시, 새로고침 후 pending 유지와 원문 미노출, console error 없음 확인.
- 환경 차단: 최초 임시 HTTP 서버 bind가 sandbox PermissionError로 실패했으며 승인된 재실행 후 UI 검증 완료.
- 제한: 실제 외부 서버에 challenge를 배포하는 종단 검증은 수행하지 않음. HTTPS 전송/인증 판정은 mock 기반 테스트. 부하 생성기는 기존 저장소에 없으며 신규 생성기는 이번 범위에 포함하지 않음.
- 다음: 실제 관리 대상 공개 HTTPS API에 안내 응답 배포 후 운영 검증. 향후 VU 실행기는 Setup을 반복 루프 밖에서 한 번 실행하도록 연결.

이 문서는 [`API 개발 기능 로드맵`](api-development-plan.md)의 구현 상태를 기록하는 단일 기준 문서다. 코드 변경과 진행 기록 갱신은 같은 작업 범위에서 수행한다.

## 현재 요약

- 최종 갱신일: 2026-09-12
- 현재 단계: FND-2 완료
- 전체 상태: 진행
- 반영 브랜치: `feature/fnd-2-testing-migrations` (커밋 `ce5e614`, 원격 푸시 완료; 병합 없음)
- 다음 작업: FND-3 기존 HTTP 계약 matrix 작성 및 FastAPI `TestClient` 전환 착수

상태는 `대기`, `진행`, `완료`, `차단` 중 하나만 사용한다. 완료 기준과 검증을 충족하기 전에는 `완료`로 변경하지 않는다.

## 단계별 현황

| ID | 작업 | 우선순위 | 상태 | 다음 확인 사항 |
| --- | --- | --- | --- | --- |
| FND-1 | 빠른 호출·실행 대시보드 branch 안전 통합 | P0 | 완료 | 빠른 호출과 실행 대시보드 최신 `develop` 통합 |
| FND-2 | frontend test·DB migration·모듈 분리 기반 | P0 | 완료 | Python 150개·frontend 8개·실제 HTTP 검증 통과 |
| FND-3 | FastAPI 백엔드 전환 | P0 | 대기 | 기존 HTTP 계약 matrix와 `TestClient` 전환 범위 확정 |
| FND-4 | PostgreSQL 영구 저장소·Redis 캐시 | P0 | 대기 | SQLite 이관, 사용자·workspace 저장 계약, cache 대상과 장애 fallback 확정 |
| API-1 | 빠른 API 호출 | P0 | 대기 | 공통 request model |
| API-2 | 환경 프로필 | P0 | 대기 | 기존 `base_url` 호환 방식 |
| API-3 | 공통 인증 모델 | P0 | 대기 | 1차 지원 방식 확정 |
| RUN-1 | 구조화된 실행 결과와 CI report | P0 | 대기 | 결과 JSON schema |
| RUN-2 | 비동기 job과 실행 제한 | P0 | 대기 | worker lifecycle |
| OAS-1 | OpenAPI operation·schema·security 편집 | P0 | 대기 | 편집 데이터 모델 |
| OAS-2 | lint·응답 schema·breaking change 검증 | P0 | 대기 | lint 정책과 차단 수준 |
| TST-1 | 명세–케이스 커버리지 | P1 | 대기 | operation 안정 ID |
| TST-2 | 명세 변경과 케이스 동기화 | P1 | 대기 | 사용자 assertion 보존 규칙 |
| TST-3 | 테스트 데이터 setup·teardown | P1 | 대기 | 허용 generator 목록 |
| MOCK-1 | OpenAPI 기반 Mock Server | P1 | 대기 | state와 외부 공개 정책 |
| OBS-1 | 기능 테스트 실행 이력 | P1 | 대기 | RUN-1 공통 metadata |
| OBS-2 | 부하테스트 결과 대시보드 | P1 | 대기 | 별도 진행 기록 참조 |
| IOP-1 | cURL·Postman·HAR 연동 | P1 | 대기 | 지원 형식과 round trip 기준 |
| COL-1 | Java WAS 로그인 BFF와 RBAC | P2 | 대기 | 사내 SSO·Spring Security 표준과 OIDC provider 확정 |
| COL-2 | Workspace 데이터 격리 | P2 | 대기 | COL-1 전에 migration과 권한 query 경계 구현 |
| GOV-1 | API lifecycle과 변경 로그 | P2 | 대기 | release·revision 연결 |
| DOC-1 | 개발자 문서 portal | P2 | 대기 | 공개 범위와 인증 |
| EXT-1 | 비REST 프로토콜 확장 | P2 | 대기 | 사용자 수요 확인 |

OBS-2의 상세 상태는 [`API 부하테스트 및 대시보드 개발 진행 기록`](api-load-test-progress.md)에서도 관리한다. 두 문서의 상태가 다르면 실제 검증 기록이 최신인 문서를 확인하고 같은 작업 안에서 동기화한다.

## 현재 작업

- 작업 ID: FND-2
- 목표: 기존 HTTP·URL 계약을 유지하며 route와 React shell을 분리하고 versioned SQLite migration 및 frontend 회귀 테스트 기반을 추가
- 변경 파일: DB migration runner와 관련 저장소, `react_server.py` route 모듈, React shell·상태 컴포넌트, frontend/Python 테스트, 이 진행 기록
- 시작 시각: 2026-09-12 KST
- 상태: 완료 — `feature/fnd-2-testing-migrations`에서 구현·검증·커밋·원격 푸시 완료, 병합 없음
- 확인이 필요한 사항: FND-3에서 현재 method·path·status·body·cookie·attachment·SPA fallback 계약을 `TestClient` matrix로 고정

## 검증 기록

| 일시 | 작업 ID | 명령 또는 확인 방법 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| 2026-09-12 | FND-2 | `python3 -m unittest discover -s tests -v` | 통과, 150개 | 신규 migration 4개와 기존 route 회귀 포함 |
| 2026-09-12 | FND-2 | `cd web && npm test`, `npm run build` | 통과, 8개·build 성공 | router 3개, form 변환 3개, dashboard loading·empty·error 2개 |
| 2026-09-12 | FND-2 | `python3 -m py_compile ...`, `docker compose config --quiet`, `git diff --check` | 통과 | route 모듈과 전체 Python source compile 포함 |
| 2026-09-12 | FND-2 | `127.0.0.1:8879` 실제 `GET /api/projects`, `GET /api/dashboard`, `GET /dashboard` | 통과, 모두 200 | `python3 react_server.py` 실행 경로와 SPA fallback 확인 |
| 2026-09-12 | FND-2 | 첫 frontend test 실행 | 실패 후 해소 | 테스트 간 DOM cleanup 누락으로 중복 element 발견, 공통 setup에 cleanup 추가 후 8개 통과 |
| 2026-09-12 | FND-2 | 최초 로컬 HTTP 서버 bind | 실패 후 해소 | sandbox `PermissionError`, 승인된 재실행으로 실제 HTTP 검증 완료 |
| 2026-09-12 | FND-1 | `python3 -m unittest discover -s tests -v` | 통과, 146개 | 실행 이력 신규 8개 포함 전체 회귀 |
| 2026-09-12 | FND-1 | `cd web && npm run build`, `python3 -m py_compile ...`, `docker compose config --quiet`, `git diff --check` | 통과 | frontend test 명령은 FND-2 도입 전이라 없음 |
| 2026-09-12 | FND-1 | 저장소 root에서 `npm run build` 재검증 시도 | 실패 후 해소 | root에 `package.json`이 없어 실패, `web/`에서 재실행해 통과 |
| 2026-09-12 | FND-1 | `127.0.0.1:8878` 실제 `POST /api/run`, `GET /api/dashboard`, `/dashboard?project=example-api` | 통과 | 정책 차단은 error, 로컬 승인 실행은 passed로 각각 저장 확인 |
| 2026-09-12 | FND-1 | 브라우저 프로젝트 필터·Run ID·뒤로 가기·319px 폭·console 확인 | 통과 | document/body 폭 304px, viewport 319px, 표만 내부 스크롤, console error 없음 |
| 2026-09-12 | PLAN | roadmap ID, 사용자·workspace 저장 계약, 의존 관계와 완료 기준 확인 | 완료 | 애플리케이션 구현은 시작하지 않음 |
| 2026-09-09 | FND-1 | `python3 -m unittest discover -s tests -v` | 통과, 109개 | 응답시간 측정 중복 통합 결함 수정 후 전체 재실행 |
| 2026-09-09 | FND-1 | `cd web && npm run build` | 통과 | Vite 8.2.1 production build |
| 2026-09-09 | FND-1 | `python3 -m py_compile ...`, `docker compose config --quiet` | 통과 | 인증·runner·서버 컴파일과 Compose 구성 확인 |
| 2026-09-09 | FND-1 | 실제 `/quick` 브라우저 직접 접근, 인증 목록, 319px 폭과 console 확인 | 통과 | 13개 인증 타입 노출, `scrollWidth=319`, 오류 없음 |
| 2026-09-09 | FND-1 | 첫 전체 Python 테스트 | 실패, 5개 | 공통 HTTP 함수와 Runner의 응답시간 타이머 중복 발견 후 수정 |
| 2026-09-07 | PLAN | 문서 링크, 작업 ID, trailing whitespace와 `git diff --check` 확인 | 통과 | 애플리케이션 코드는 변경하지 않음 |
| 2026-09-07 | PLAN | 현재 기능, 원격 기능 branch, 문서와 코드 구조 비교 | 완료 | 구현은 시작하지 않음 |

## 결정 기록

| 일자 | 결정 | 이유 | 영향 |
| --- | --- | --- | --- |
| 2026-09-12 | Studio DB와 ownership DB에 독립적인 순차 migration 목록과 `schema_migrations` 사용 | 기존 무버전 DB를 보존하면서 향후 schema 변경 순서와 적용 여부를 명확히 관리 | 한 migration 실행 중 실패하면 schema와 version 기록 전체 rollback |
| 2026-09-12 | legacy HTTP handler는 유지하고 document·execution·OpenAPI·dashboard route만 모듈로 분리 | FND-3 전환 전 기존 HTTP 계약과 테스트 patch 지점을 바꾸지 않기 위해 단계적으로 책임 분리 | `StudioHandler`는 공통 origin·body·응답·예외 mapping과 dispatch 담당 |
| 2026-09-12 | 실행 metadata를 별도 DB가 아니라 `STUDIO_DB_PATH`의 Studio DB에 UUID Run ID로 저장 | RUN-1과 OBS-1이 재사용할 공통 실행 식별자와 저장 경계를 먼저 맞춤 | 웹 실행 응답·대시보드 이력이 같은 Run ID를 사용하고 Docker data volume에 보존 |
| 2026-09-12 | 이력에는 대상·프로젝트·시각·상태·소요 시간·종료 코드만 저장 | 요청·응답 본문, header, 인증정보와 runner 출력의 2차 노출 방지 | 상세 원문은 기존 실행 화면·로그에만 존재하며 대시보드는 metadata만 조회 |
| 2026-09-12 | 로그인 전부터 모든 협업 데이터에 내부 user ID와 workspace 경계 적용 | email·요청 header 변경이나 reference 조작이 데이터 소유권을 바꾸지 않도록 보장 | 저장소 메서드에 검증된 `RequestContext` 필수 |
| 2026-09-12 | 기존 SQLite 데이터는 local workspace·시스템 사용자로 이관 | 기존 데이터 손실 없이 다중 사용자 schema로 전환 | 이관 후 명시적인 소유권 양도 절차 필요 |
| 2026-09-12 | PostgreSQL을 영구 데이터 기준, Redis를 재생성 가능한 캐시로 사용 | 캐시 장애와 영구 데이터 정합성을 분리하고 다중 사용자 확장 기반 확보 | FND-4에서 SQLite 이관과 cache-aside 구현 |
| 2026-09-12 | 일반 캐시와 Java WAS session의 Redis namespace·TTL·장애 정책 분리 | 일반 조회 cache miss와 인증 session 손실은 허용 가능한 영향이 다름 | 일반 캐시는 DB fallback, session 장애는 인증 실패 처리 |
| 2026-09-12 | FastAPI 내부 API와 PostgreSQL 전환 후 필요 시 Java WAS 인증 BFF 도입 | Java가 FastAPI를 실행하지 않으며 인증과 업무 API 책임 중복 방지 | FND-2 → FND-3 → FND-4 → COL-2 → COL-1 순서 적용 |
| 2026-09-12 | Java WAS 도입 전 workspace 권한 query와 migration 구현 | 로그인만 추가해도 reference 조작과 데이터 혼선은 차단되지 않음 | 모든 문서·실행·secret에 workspace 경계 필요 |
| 2026-09-07 | REST와 OpenAPI 핵심 흐름을 먼저 완성 | 현재 제품 구조와 보유 기능을 활용하고 범위 확산 방지 | GraphQL·gRPC·AsyncAPI는 P2 이후 검토 |
| 2026-09-07 | 기능 테스트와 부하테스트가 공통 run metadata 사용 | 실행 이력 저장과 화면의 중복 방지 | RUN-1이 두 대시보드보다 선행 |
| 2026-09-07 | quick-call과 execution-dashboard branch를 최신 기준에 재구성 | 두 branch가 후속 기능과 테스트보다 이전 기준에서 분기 | 원본 branch 직접 병합 금지 |
| 2026-09-07 | 임의 스크립트보다 declarative test data 기능 우선 | 로컬·다중 사용자 환경의 명령 실행 위험 축소 | generator와 setup·teardown 기능 범위 제한 |

## 변경 이력

최신 항목을 위에 추가하고 작업 ID, 변경 파일, 검증 결과, 알려진 제한과 다음 작업을 기록한다.

### 2026-09-12 — FND-2 — 테스트·migration·route 모듈 기반

- 변경: Studio/ownership SQLite에 순차 version migration과 전체 실행 rollback 추가, 기존 무버전 DB 데이터 보존 승격 지원
- 구조: `react_server.py`에서 document·execution·OpenAPI·dashboard route를 `api_test/routes/`로 분리하고 React 공통 topbar·오류 shell을 `StudioShell`로 분리
- frontend test: Vitest·React Testing Library 명령과 공통 jsdom setup을 추가하고 router, form 변환, dashboard loading·empty·error·retry를 검증
- 변경 파일: `api_test/migrations.py`, 저장소 3개, `api_test/routes/`, `react_server.py`, migration 테스트, `web/package*.json`, Vite 설정, `StudioShell`, frontend 테스트, `README.md`, 이 진행 기록
- 검증: Python 150개, frontend 8개, Vite build, py_compile, Compose config, diff check와 실제 HTTP 3개 route 모두 통과
- 제한: 서버 framework는 FND-3 전까지 `ThreadingHTTPServer` 유지. route 모듈은 현재 handler의 공통 request/response helper를 주입받아 기존 계약을 보존
- 반영: `feature/fnd-2-testing-migrations`의 `ce5e614`로 커밋하고 `origin/feature/fnd-2-testing-migrations`에 푸시. 병합은 수행하지 않음
- 다음: FND-3 HTTP 계약 matrix 작성 후 FastAPI route로 단계 전환

### 2026-09-12 — FND-1 — 실행 대시보드 최신 `develop` 기준 재구성

- 변경: 웹 기능 테스트 실행에 UUID Run ID를 부여하고 성공·실패·오류·시간 초과 metadata를 Studio DB에 저장, 기간·프로젝트·결과 필터와 일별 추이·페이지 조회 API 및 `/dashboard` 화면 추가
- 보안: 요청·응답 본문, header, 인증정보와 runner 출력은 이력에 저장하지 않으며 저장 실패는 실행 결과를 보존하고 경고만 반환
- 변경 파일: `api_test/execution_history.py`, `react_server.py`, `tests/test_execution_history.py`, `tests/test_react_server.py`, `web/src/pages/dashboard/`, `web/src/App.jsx`, `web/src/router.js`, 공통 컴포넌트, `README.md`, 이 진행 기록
- 검증: Python 146개, Vite build, py_compile, Compose config, git diff check 통과. 실제 HTTP error·passed 기록과 조회, 브라우저 직접 경로·필터·뒤로 가기·319px·console 확인 통과
- 제한: CLI 직접 실행 이력, 개별 case/step 상세 결과, JSON·JUnit 출력은 RUN-1 범위. frontend test는 FND-2에서 도입 예정
- 반영: `feature/execution-dashboard-integration`에서 검증 후 `develop`에 fast-forward 병합. 원격 반영과 기능 브랜치 삭제는 수행하지 않음
- 다음: FND-2의 frontend test·DB migration·route 모듈 분리 착수

### 2026-09-12 — PLAN — FastAPI·PostgreSQL·Redis·Java WAS 권장 순서 문서화

- 변경: FND-3 FastAPI 전환, FND-4 PostgreSQL 이관·로그인 고려 저장 계약·Redis cache-aside, Java WAS 인증 BFF와 workspace 격리의 12단계 구현 순서 및 완료 기준 추가
- 변경 파일: `docs/api-development-plan.md`, `docs/api-development-progress.md`
- 검증: roadmap ID와 의존 관계, 문서 링크, Markdown 형식 및 `git diff --check` 확인
- 제한: FastAPI, Uvicorn, PostgreSQL, Redis, Java WAS, OIDC와 DB migration 구현은 시작하지 않음
- 다음: FND-2 기반 작업 후 FND-3의 기존 HTTP 계약 matrix를 작성하고 FND-4 SQLite 이관·사용자 데이터 schema 계약 설계

### 2026-09-09 — FND-1 — 빠른 호출 최신 `dev` 통합 완료

- 변경: `/quick` 빠른 호출 화면, 13개 인증 타입, 공통 HTTP 실행 함수와 요청별 proxy 설정을 최신 `dev` 기준으로 이식하고 기존 응답시간 검증을 보존
- 변경 파일: `api_test/authorization.py`, `api_test/runner.py`, `react_server.py`, `requirements.txt`, 관련 테스트, `web/src/App.jsx`, `web/src/router.js`, `web/src/styles.css`, `README.md`
- 검증: Python 109개 테스트, Vite build, py_compile, Compose config, 브라우저 `/quick` 직접 접근·인증 목록·319px overflow·console 확인 통과
- 제한: Digest·NTLM은 실제 외부 서버 handshake를 이번 작업에서 검증하지 않았고, 실행 대시보드는 이번 범위에서 제외
- 다음: 실행 대시보드를 RUN-1 공통 실행 결과 모델과 정렬해 최신 `dev`에 통합

### 2026-09-07 — PLAN — API 개발 기능 로드맵 작성

- 변경: 현재 기능 격차, P0~P2 우선순위, 단계별 완료 기준과 의존 관계 정의
- 변경 파일: `docs/api-development-plan.md`, `docs/api-development-progress.md`, `docs/README.md`, `AGENTS.md`
- 검증: 저장소 문서, 현재 코드와 원격 기능 branch 비교, 문서 링크·형식 확인
- 제한: 구현 작업과 기능 테스트는 시작하지 않음
- 다음: 통합 브랜치 이름 확정 후 FND-1 착수

## 차단 사항

현재 차단 사항 없음. 사용자가 이번 통합 대상을 최신 `dev`로 지정했으며, 장기 브랜치 명명 정리는 별도 결정으로 남긴다.

차단이 발생하면 작업 ID, 발생 시각, 재현 방법, 영향, 시도한 해결책과 필요한 결정을 기록한다. 해소 후에도 항목을 삭제하지 않고 해결 시각과 방법을 추가한다.

## 갱신 체크리스트

- 작업 시작 전 `현재 요약`, `단계별 현황`, `현재 작업` 갱신
- 설계나 범위가 바뀌면 `결정 기록` 갱신
- 의미 있는 구현 단위마다 `변경 이력` 추가
- 실행한 검증의 성공과 실패를 `검증 기록`에 모두 추가
- 차단 시 관련 단계 상태와 `차단 사항` 갱신
- 완료 기준을 충족한 경우에만 단계 상태를 `완료`로 변경
- 사용자 완료 보고 전에 요약, 검증, 변경 이력과 다음 작업 갱신
