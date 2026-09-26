# API 개발 기능 진행 기록

## OBS-2 / DB-1 결과 계약·importer 완료 (2026-09-26)

- 시작: MOCK-1이 `develop`에 통합된 상태에서 다음 명시 작업인 DB-1을 `feature/load-test-results`에서 시작.
- 범위: 부하테스트 결과 JSON schema, k6 summary·원본 JSON importer, 정상·오류 fixture, 집계·보안 경계 단위 테스트와 사용 문서.
- 비범위: 결과 저장소·조회 API(DB-2), React 대시보드(DB-3), 실제 장시간 부하 실행(LT-1~LT-5), 커밋·푸시·병합.
- 변경: `schemaVersion: 1` 계약, 줄 단위 k6 importer, `handleSummary` manifest helper, Smoke·Target·오류 fixture와 운영 문서를 추가. query/origin 제거, 동적 path 정규화, 원문 미노출 오류 경계를 적용.
- 최종 검증: DB-1 단위 테스트 10개, 권한 확장 전체 Python 310개(skip 0), Python compile, Node helper 실행, 생성 코드 검사와 `git diff --check` 통과. 제한된 sandbox의 최초 전체 실행은 loopback·PostgreSQL·process 접근 제한으로 실패했고 같은 코드의 승인된 재실행으로 환경 원인임을 확인. Node의 제거된 `--experimental-default-type=module` 옵션 사용도 1회 실패했고 `--input-type=module` 직접 로드로 helper 동작을 재검증.
- 완료 기준: Smoke·Target fixture가 schema를 통과하고 요청 수·RPS·오류율·percentile·시간 bucket이 수작업 기준과 일치하며 비밀값과 동적 URL 식별자가 결과에 남지 않는다.
- 완료: DB-1 계약·importer의 로컬 구현과 검증 완료. 실제 k6 부하 실행과 DB 저장·API·UI는 각각 LT 단계와 DB-2 이후 범위로 유지.

## MOCK-1 완료 보완 및 독립 검증 (2026-09-25)

- 시작: 사용자 요청으로 미완료 항목을 확인하고 `gpt-6-sol / xhigh` 서브에이전트에 개발 위임. 기존 archive 정리 변경을 보존해 `fix/mock-completion`에서 작업.
- 변경: 응답/항목 1MiB 제한, HEAD method/body 처리, config/reset/stop 경합 직렬화, status/media 변경 시 종속 example 초기화, 테스트 fixture 격리.
- 검증: 주 에이전트 전체 Python 300개 통과(skip 0), 생성 검사·diff 검사 통과. 서브에이전트 Mock 31개·frontend 28개·build 통과. 실제 브라우저 명세 소스 3종의 선택→시작→HTTP 응답, refresh/reset/error/stop, UI 결함 수정 재현 확인.
- 완료: MOCK-1 개발 및 로컬 검증 완료. [완료 보고서](archive/mock-1/completion-report.md). 기존 보류 기록은 과거 이력이며 최신 판정은 이 기록을 따른다.
- Git: 이번 보완은 미커밋·미푸시·미병합. 테스트 전용 DB는 유지하고 임시 브라우저 서버는 종료.

## 완료 문서 정리 (2026-09-22)

- MOCK-1 개발 인계·리뷰·검증 계획·검증 보고서를 `docs/archive/mock-1/`로 이동해 당시 증거를 보존했다.
- 현재 사용 기준은 [Mock Server](mock-server.md), 전체 문서 탐색 기준은 [문서 안내](README.md)로 분리했다.
- 상태 기준을 현재 `develop` 통합 상태로 갱신했다. 문서 정리만 수행했으며 제품 코드·테스트 결과·MOCK-1 잔여 검증 판정은 변경하지 않았다.

## 테스트 PostgreSQL·Redis 기본 설정 (2026-09-22)

- 시작: 사용자 요청으로 테스트 전용 접속 설정을 기본값으로 적용.
- 변경: `tests/test_postgres_storage.py`에서 환경변수 미설정 시 loopback PostgreSQL 15432/Redis 16379 사용. 명시한 override 우선, 빈 문자열은 의도적인 SQLite-only 실행을 위한 opt-out으로 유지.
- 환경: `docker-compose.test.yml`에 앱 저장소와 분리된 테스트 컨테이너 구성. PostgreSQL tmpfs, loopback 포트, Redis 비영속 저장. CI 서비스도 동일 기본값으로 구성. README 실행 안내 및 `.venv/` ignore 추가.
- 검증: 최초 시스템 Python 실행은 psycopg 누락으로 오류. 기존 Python 의존성을 재사용하는 프로젝트 `.venv`에 psycopg binary/pool 및 redis 설치 후 `.venv/bin/python -m unittest discover -s tests -v` 실행, **297개 전체 통과·skip 0**(15.845초). diff 검사 통과. 원격 CI 자체 실행은 미수행.
- 완료: 기본 설정과 로컬 검증 완료. 테스트 전용 PostgreSQL·Redis 컨테이너는 다음 실행을 위해 기동 상태 유지. 기존 앱/운영 데이터는 변경하지 않음. 커밋·푸시·병합 없음.

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

- 최종 갱신일: 2026-09-26
- 현재 단계: OBS-2의 DB-1 결과 계약·importer 완료
- 전체 상태: 진행
- 반영 브랜치: `feature/load-test-results` (기반 `develop` `d77e0d1`)
- 다음 작업: DB-2 전용 migration·repository와 atomic import·조회 API 설계 및 구현.

상태는 `대기`, `진행`, `완료`, `차단` 중 하나만 사용한다. 완료 기준과 검증을 충족하기 전에는 `완료`로 변경하지 않는다.

## 단계별 현황

| ID | 작업 | 우선순위 | 상태 | 다음 확인 사항 |
| --- | --- | --- | --- | --- |
| FND-1 | 빠른 호출·실행 대시보드 branch 안전 통합 | P0 | 완료 | 빠른 호출과 실행 대시보드 최신 `develop` 통합 |
| FND-2 | frontend test·DB migration·모듈 분리 기반 | P0 | 완료 | Python 150개·frontend 8개·실제 HTTP 검증 통과 |
| FND-3 | FastAPI 백엔드 전환 | P0 | 완료 | Python 166개·frontend 8개·build·실제 HTTP/React·Docker healthcheck·SDK ZIP 통과 |
| FND-4 | PostgreSQL 영구 저장소·Redis 캐시 | P0 | 완료 | 전체 Python 206개·frontend 8개·build·실제 Compose HTTP·장애 복구·백업 복원 통과 |
| API-1 | 빠른 API 호출 | P0 | 완료 | JSON·Text·Form Data, 케이스 저장 전환, 응답 대기 취소, cURL 마스킹 |
| API-2 | 환경 프로필 | P0 | 완료 | 기존 base_url 호환, 웹·CLI 선택, 암호화 override |
| API-3 | 공통 인증 모델 | P0 | 완료 | 1차 No Auth·API Key·Basic·Bearer 완료. OAuth 2.0 발급은 2차 |
| RUN-1 | 구조화된 실행 결과와 CI report | P0 | 완료 | JSON/JUnit·웹 판정 및 민감정보 제외 검증 통과 |
| RUN-2 | 비동기 job과 실행 제한 | P0 | 완료 | 기능 테스트 제출·조회·취소·제한 검증 완료. SDK 연동은 후속 |
| OAS-1 | OpenAPI operation·schema·security 편집 | P0 | 진행 | operation 메타데이터 수정·삭제부터 단계적으로 구현 |
| OAS-2 | lint·응답 schema·breaking change 검증 | P0 | 완료 | 구조 lint·revision diff·빠른 호출 응답·CLI gate 검증. 원격 CI 실행은 미수행 |
| TST-1 | 명세–케이스 커버리지 | P1 | 완료 | operation/status 연결 수·최근 성공, 미검증 응답 표시 |
| TST-2 | 명세 변경과 케이스 동기화 | P1 | 완료 | field preview·선택 갱신·revision 충돌·assertion/secret 보존 |
| TST-3 | 테스트 데이터 setup·teardown | P1 | 완료 | UUID/시각/정수·seed·run 변수 추출·정리 결과 분리 |
| MOCK-1 | OpenAPI 기반 Mock Server | P1 | 완료 | Python 300개 skip 없이 통과, frontend 28개·build·생성 검사 및 실제 브라우저 명세 3종 검증 완료 |
| OBS-1 | 기능 테스트 실행 이력 | P1 | 대기 | RUN-1 공통 metadata |
| OBS-2 | 부하테스트 결과 대시보드 | P1 | 진행 | DB-1 완료. 다음은 DB-2 저장소·조회 API |
| IOP-1 | cURL·Postman·HAR 연동 | P1 | 대기 | 지원 형식과 round trip 기준 |
| COL-1 | Java WAS 로그인 BFF와 RBAC | P2 | 대기 | 사내 SSO·Spring Security 표준과 OIDC provider 확정 |
| COL-2 | Workspace 데이터 격리 | P2 | 대기 | COL-1 전에 migration과 권한 query 경계 구현 |
| GOV-1 | API lifecycle과 변경 로그 | P2 | 대기 | release·revision 연결 |
| DOC-1 | 개발자 문서 portal | P2 | 대기 | 공개 범위와 인증 |
| EXT-1 | 비REST 프로토콜 확장 | P2 | 대기 | 사용자 수요 확인 |

OBS-2의 상세 상태는 [`API 부하테스트 및 대시보드 개발 진행 기록`](api-load-test-progress.md)에서도 관리한다. 두 문서의 상태가 다르면 실제 검증 기록이 최신인 문서를 확인하고 같은 작업 안에서 동기화한다.

## 직전 작업

### MOCK-1 독립 검증 결과 (2026-09-21)

- 작업 ID: MOCK-1 (독립 검증 결과)
- 일시: 2026-09-21 23:36 KST
- 검증 기준: `docs/archive/mock-1/verification-plan.md` (M01~M20 전수 및 최근 6개 수정 검증)
- 상세 보고서: `docs/archive/mock-1/verification-report.md`
- 최종 판정: **진행** (핵심 기능 M01~M15, M17~M20 통과, M16 경미 지연 및 생성기 개행 2건 보완 필요)
- 검증 내역:
  - 기능 매트릭스: M01~M15, M17~M20 (총 19개 항목) 통과.
  - 자동화 테스트:
    - `python3 -m unittest discover -s tests -v`: 293개 실행, 251개 통과, 42개 skip, 0 failure, 0 error (기존 전체 회귀 무결성 검증).
    - `python3 -m unittest tests/test_mock_server.py -v`: 11개 전체 통과.
    - `python3 -m unittest tests/test_mock_review_regressions.py -v`: 11개 전체 통과.
    - `cd web && npm test`: 10개 파일 27개 테스트 전체 통과 (MockServerPanel 3개 포함).
    - `cd web && npm run build`: Vite 번들 정상 빌드 완료.
    - `git diff --check && git diff --cached --check`: 공백 오류 0건 통과.
    - 라이브 HTTP 수명주기: GET -> start -> health -> config -> reset -> stop -> 포트 릴리즈 100% 통과.
  - 발견 결함:
    - **Finding 1 (P2 / M16)**: `test_mock_concurrent_smoke_harness` 단독 실행 시 `synthesize_schema`의 `contracts.validation` 동적 import로 인한 콜드스타트 GIL 병목으로 p95 238ms~256ms 초과 (`assertLess(p95, 200.0)` 실패).
    - **Finding 2 (P3 / 빌드 정합성)**: `python3 scripts/generate_server.py --check` 실행 시 `api_test/generated/apis/mock_api.py` 라우터 함수 간 개행 빈 줄 누락으로 exit code 1 차이 감지.
- 후속 조치: `schema_errors` 모듈 선행 import 및 `mock_api.py` 개행 정합성 조정 후 최종 재검증. 코드는 임의 수정하지 않고 작업 트리 보존.

### MOCK-1 독립 리뷰 결함(R1–R8) 및 경계 보완 (2026-09-21)

- 작업 ID: MOCK-1 (결함 보완 및 재검증 대기)
- 시작: 2026-09-21 KST
- 상태: 진행 (보완 완료, 독립 재검증 대기) — `feature/mock-server`, clean develop `f033c44` 기준 미커밋 작업 트리 유지.
- 결함 수정 내역:
  - **R1 (P1 · State 격리)**: 경로 템플릿과 상위 파라미터 값을 결합한 명시적 컬렉션 키 매핑 적용. `/api/users`와 `/api/orders` 간 state 격리 보장.
  - **R2 (P1 · ID 카운터 및 충돌 방지)**: 컬렉션별 단조 증가 `_next_ids` 카운터 도입, 삭제 후 새 항목 생성 시 기존 ID 보존, 명시적 중복 ID 생성 요청 시 409 Conflict 반환.
  - **R3 (P2 · 상태 변경 및 응답 순서)**: 오버라이드/에러 시뮬레이션에 의한 오류 상태(>= 400) 발생 시 state 변경 차단. POST 시 스키마 기본값(예: `status: "active"`)과 본문 병합 후 저장·반환.
  - **R4 (P2 · 스키마 제약 준수)**: `minItems`, `maxItems`, `minimum`, `maximum`, `exclusiveMinimum/Maximum`, `minLength`, `maxLength` 제약값 만족. 깊이 초과/순환 참조 시 non-null 스키마에 대해 타입 기본값(`{}`, `[]`, `""`, `0`) 반환. `jsonschema` 검증 통과.
  - **R5 (P2 · 관리 API 엄격 검증 및 포트 계약)**: seed, port(1..65535, port 0 거부), defaultLatencyMs(0..5000), overrides 구조 검증 실패 시 400 반환. 재시작 실패 시 기존 서버 중지 방지. IPv6 주소 URL 대괄호(`http://[::1]:port`) 표기.
  - **R6 (P2 · 파이프라인 본문 검증 계약)**: `expected.body` 및 `validation_modes.exact_body` 반영, `case/{tag}/{api_name}/{case_file}.json` 경로 준수, 의도된 본문 불일치 시 파이프라인 실패(음성 테스트) 입증.
  - **R7 (P2 · 웹 UI Operation별 오버라이드 지원)**: Operation 선택기, 상태 코드/미디어타입/Example/지연/오류 오버라이드 설정 및 삭제 UI 추가, `applyConfig`/`startServer`에 전달. 상태 조회 실패 시 중지 상태 복원. 단일 프로세스/인메모리 state 소멸/명세 스냅샷 안내 문구 추가.
  - **R8 (P2 · 비 JSON 미디어 타입 지원)**: `resolve_operation_response` 3-tuple(`status, media_type, payload`) 반환. `text/plain` 요청 시 `text/plain; charset=utf-8` 및 raw string body 전송.
  - **경계 조건 보완**: 요청 본문 1MB 상한(`MAX_BODY_BYTES`), 인메모리 state 10MB 상한(`MAX_STATE_BYTES`) 및 10,000개 상한. `stop()` 시 uvicorn 정상 소켓 close 대기 후 강제 취소. smoke 하네스 전체 실행 `deadline_seconds`(30s) 적용.
- 검증 결과:
  - 독립 회귀 테스트 `tests/test_mock_review_regressions.py` (6개 항목 전체 통과).
  - 전체 Python: 288개 실행, 246개 통과, 42개 skip (외부 PostgreSQL URL 설정 의존).
  - 프론트엔드: `npm test` 10개 파일 27개 테스트 전체 통과, `npm run build` Vite 번들 생성 성공.
  - 생성 코드: `python3 scripts/generate_server.py --check` 통과.
  - 실제 HTTP 파이프라인: POST(추출) -> GET(본문 검증) -> 의도된 404 -> 부정 검증(본문 불일치 차단) 전체 통과.
  - Smoke 테스트: 100건 요청, 동시성 10, 성공률 100%, 0 에러, RPS 349.6, p50 2.9ms.
- 커밋·병합·푸시: 수행하지 않음. MOCK-1 독립 재검증 전까지 `완료` 처리 보류.

- 작업 ID: OAS-2
- 시작: 2026-09-17 KST
- 상태: 완료 — `feature/openapi-contract-validation`, develop 기준에 OAS-1 미커밋 변경 보존.
- 범위: OpenAPI 3.0/3.1 lint, revision 비교, 빠른 호출의 실제 응답 검증, CLI/CI breaking change 차단과 해시에 연결된 승인 기록.
- 결정: OAS-1 잔여 편집 UI보다 OAS-2를 먼저 진행한다는 사용자 요청 적용. 검증 오류는 차단, 설명·operationId 누락 등 조직 lint는 경고. 알려진 breaking과 분석 불확실 변경은 CI 차단.
- 검증: Python 전체 259개(217 통과·42 환경 의존 skip), frontend 22개·production build, 생성 코드 --check·git diff --check. 실제 develop 명세 비교 compatible=true, CLI breaking exit 1·승인 exit 0·오래된 승인 exit 2 검증.
- 실제 브라우저: 임시 데이터와 HTTP 서버 8883에서 lint 통과, revision 1→2의 required query 추가 차단, 실제 HTTP 200의 유효 body 통과·타입 불일치 실패 확인.
- 지원 경계: 응답 검증은 빠른 호출에 연결. 케이스·파이프라인 자동 계약 검증은 후속. URL-only 과거 revision, 외부 참조·dynamic/anchor·구조적 ref sibling·사용자 schema dialect·복합 header serialization은 지원하지 않고 차단. 일반 JSON Schema 포함관계 대신 지원 규칙과 review 분류 사용.
- 승인 경계: 두 명세 hash·변경 ID·reason·approvedBy를 파일로 기록하고 CLI/CI에서 검증. 실제 승인 권한은 저장소 리뷰 정책이며 인증된 승인 UI는 미구현.
- 문서: [OpenAPI 계약 검증 사용법·정책](openapi-contract-validation.md).
- 반영: 커밋·병합·푸시·배포 없음. GitHub CI 원격 실행·브랜치 보호 설정·실제 PostgreSQL 회귀는 수행하지 않음.

### 이전 OAS-1 1차 작업

- 작업 ID: OAS-1 (1차 operation 메타데이터 수정·삭제)
- 시작: 2026-09-17 KST
- 상태: 1차 완료 / OAS-1 전체 진행 — `feature/openapi-operation-edit`, 깨끗한 develop의 cd32db2 기준.
- 범위: summary·description·operationId·tags·deprecated 수정, 삭제, 중복 ID 검증, 변경 preview, revision 충돌 및 Example 보호 유지.
- 후속: component schema·security·request/response 편집과 전체 문서 validation.
- 검증: Python 242개(200 통과·42 조건 의존 skip), frontend 19개·production build·생성 코드 --check·diff check. 실제 임시 서버 8882에서 브라우저 수정·미리보기·저장·새로고침 후 값 유지 확인.
- 제한: path/method 변경 미지원. 외부 URL 문서는 프로젝트 사본으로 전환. fragment·공유 path 참조 및 참조 operation은 손실 방지를 위해 편집 거부. 본 단계 검증은 metadata 타입·중복 operationId·기존 문서 검사이며 전체 OpenAPI 표준 validation은 후속.

### 이전 RUN-2 작업

- 작업 ID: RUN-2
- 시작: 2026-09-15 KST / 완료: 2026-09-16 KST
- 상태: 완료 — `feature/async-runs` 미커밋 작업 트리 (RUN-1 변경 보존)
- 결과: 비동기 제출·조회·취소 API, worker·사용자·프로젝트 한도, 종료 정리, 화면 상태·취소·재조회와 대시보드 취소 상태 연결.
- 검증: Python 236개 중 194개 통과·42개 조건 의존 skip. frontend 17개·production build, OpenAPI 재생성 --check, git diff --check 통과.
- 실제 동작: macOS 자식 프로세스와 임시 파일이 취소·timeout·shutdown 후 제거됨. 임시 서버 8879에서 로컬 예제 HTTP 200·실행 완료, 새로고침 후 동일 Run ID 결과 복원 확인.
- 제한: 단일 API 프로세스·메모리 job; 재시작 복구 없음. Windows taskkill 경로는 구현했지만 실제 Windows 검증은 미수행. SDK 생성은 기존 동기 API를 유지하며 공통 JobManager의 후속 adapter 대상.
- 사용법: [RUN-2 비동기 실행](async-runs.md).
- 커밋·병합·푸시·배포: 수행하지 않음.

### 이전 RUN-1 작업

- 작업 ID: RUN-1
- 시작·완료: 2026-09-15 KST
- 상태: 완료 — `feature/run-reports` 미커밋 작업 트리
- 결과: 공통 결과 모델·JSON schema, CLI JSON/JUnit 출력, 웹 실행 결과·Run ID 연결
- 검증: 전체 Python 229개 중 187개 통과·외부 서비스 등 조건 의존 42개 skip. 신규 보고서 테스트 5개, schema 상태 5종·설정 오류 검증, OpenAPI 재생성 --check, git diff --check 통과.
- 계약 및 제한: [RUN-1 실행 보고서](run-reports.md). 취소·비동기 job은 RUN-2 범위.
- 커밋·병합·푸시: 수행하지 않음.

### 이전 작업

- 작업 ID: OpenAPI Generator 서버 구조 전환
- 목표: Studio 명세에서 생성한 라우터·모델과 직접 작성하는 서비스 분리
- 시작: 2026-09-14 KST / 완료: 2026-09-15 KST
- 상태: 완료 — `feature/openapi-generated-server` 작업 트리
- 결과: 29 operations·41 schemas·9개 도메인 router, 앱 진입점·dependency·implementation·service 분리. Generator 7.24.0 고정 재생성 스크립트와 CI 추가.
- 검증: Python 222개 중 181개 통과·외부 서비스 설정 의존 41개 skip. frontend 14개·build·compile·diff check·실제 재생성 --check 통과. 임시 Uvicorn 실제 HTTP CRUD·revision suffix·빠른 호출 통과.
- 계약 및 사용법: [OpenAPI Generator 서버 구조](generated-server.md)
- 범위: 기존 업무 검증·원문 JSON·오류 계약을 유지. DTO 강제 HTTP 입력 검증과 공유 도우미의 전면 클래스/DI 재작성은 포함하지 않음.
- 커밋·병합·푸시·배포: 수행하지 않음.

## 검증 기록

| 일시 | 작업 ID | 명령 또는 확인 방법 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| 2026-09-17 | OAS-2 | Python 259개, frontend 22개, build, 생성 --check, diff check | 통과 (Python 42 skip) | 구조·중첩/재귀 참조·방향별 diff·응답·revision workspace 경계 검증 |
| 2026-09-17 | OAS-2 | CLI 실제 develop 비교 및 breaking/승인 fixture | 통과 | 실제 명세 호환, breaking exit 1, 승인 exit 0, stale 승인 exit 2 |
| 2026-09-17 | OAS-2 | 실제 HTTP·브라우저 8883 | 통과 | lint·revision 필수 parameter 변경 차단·실제 응답 schema 통과/실패 |
| 2026-09-17 | OAS-2 | 초기 신규 테스트 | 실패 후 해소 | 생성 DTO object import, 없는 revision 400/404 차이, OAS 3.0 빈 required fixture 수정 후 통과 |
| 2026-09-17 | OAS-1 1차 | Python 242개·frontend 19개·build·생성 --check·diff check | 통과 (Python 42 skip) | 최초 ps 권한·URL mock·region 선택 오류 해소 후 통과 |
| 2026-09-17 | OAS-1 1차 | 임시 HTTP 서버 및 실제 브라우저 | 통과 | 미리보기·저장·새로고침 후 값 유지, 편집 폼 배치 확인 |
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

### 2026-09-17 — OAS-2 계약 검사 완료

- 시작: 사용자 요청으로 OAS-1 잔여 편집보다 OAS-2를 진행. feature/openapi-contract-validation에서 기존 OAS-1 변경 유지.
- 변경: api_test/contracts의 로컬 참조 보존 로더·표준 lint·방향별 breaking diff·응답 schema 검증·CLI, workspace 범위의 immutable revision 조회, 계약 검사 API와 생성 라우터/DTO.
- 변경: API 목록의 revision 비교 패널, 빠른 호출의 실제 응답 검사 선택/결과, PR base SHA 비교 CI와 JSON artifact, 명세 hash에 묶인 승인 기록 및 사용 안내.
- 보완: 중첩 참조가 동일 문자열이어도 대상 schema 변경 검출, composition/보안/header 참조 변경은 review 차단, 재귀 schema 유지, 3.0/3.1 read-context required와 불량 dialect 입력 처리. 진단에서 원문 값 제외.
- 검증: Python 259개(217 통과·42 skip), frontend 22개·build·생성 --check·diff check. CLI·실제 HTTP·브라우저 확인 결과는 검증 기록 참조.
- 실패 해소: generator의 자유 형식 response 상속 import는 schema 정의 조정 후 재생성. 새 계약 API의 missing revision을 명시적 404로 수정. required=[]가 OpenAPI 3.0에서 유효하지 않아 제거 fixture로 교정. 테스트 파일 상대 위치 오류는 저장소 기준 경로로 수정.
- 제한: 원격 CI·브랜치 보호·PostgreSQL 실서비스 검증 없음. 저장 케이스 자동 계약 연동 및 인증된 승인 UI는 후속. OAS-1은 여전히 진행.
- 완료: 로컬 구현·검증·문서 갱신. 커밋·병합·푸시·배포 없음.

### 2026-09-17 — OAS-1 1차 operation 메타데이터 편집

- 시작: RUN-2가 반영된 깨끗한 develop에서 feature/openapi-operation-edit 분기. 전체 OAS-1은 진행으로 유지.
- 변경: 기존 POST operation 계약에 create/update/delete action 추가, 생성 DTO 재생성. 수정 가능한 필드는 operationId·summary·description·tags·deprecated로 제한. 삭제 시 sibling method·path 공통 parameter·연결 케이스 유지.
- 보존: bundle의 해당 path 파일만 수정하며 schema 파일·재귀 reference·extension을 유지. inline JSON도 원문 구조를 복제해 필요한 metadata만 수정. revision 기반 저장과 읽기 전용 Example 차단 재사용.
- 화면: API 목록에서 operation을 펼친 뒤 편집. 변경 전후 preview와 삭제 확정, 저장 충돌 메시지 표시.
- 검증: Python 242개 중 200 통과·42 외부 서비스 설정 의존 skip, frontend 19개·build, 생성 코드 --check·git diff --check 통과. 임시 SQLite/HTTP 서버에서 브라우저 저장·새로고침 유지 확인.
- 실패 및 해소: 첫 전체 테스트의 ps 권한 제한은 승인된 실행으로 재검증. URL 문서 조회 mock 회귀는 기존 load 경로 유지로 수정. frontend preview 테스트의 중복 region 선택은 이름으로 지정해 수정. npm 루트 실행 오류는 web/에서 재실행해 해소. 임시 서버 bind 제한도 검증 명령 권한 확장으로 해소.
- 다음: schema/security/request/response 편집과 전체 문서 validation. 이번 작업은 OAS-1 전체 완료가 아님. 커밋·병합·푸시·배포 없음.

### 2026-09-16 — RUN-2 기능 테스트 실행 완료

- 변경: app 수명주기 JobManager, 취소 가능한 프로세스 그룹 실행, 크기·보관·동시 실행 제한, OpenAPI 생성 라우터·DTO, 케이스·파이프라인 실행 화면과 sessionStorage 재조회 연결.
- 추가 수정: 실제 브라우저에서 발견한 케이스 로딩과 결과 복원의 경합을 수정하고 기록 키를 케이스·파이프라인 참조별로 분리.
- 검증: Python 236개(194 통과·42 skip), frontend 17개·build·OpenAPI --check·diff check 통과. macOS process tree 종료 및 실제 UI 실행·새로고침 복원 확인.
- 환경 제한 해소: 샌드박스의 ps·loopback bind 제한으로 관련 검증을 허용된 실행 환경에서 재실행해 통과. npm은 web/에서 실행해 검증 완료.
- 다음: OAS-1. SDK 비동기 연동·영속 job 복구·분산 worker는 미구현이며 운영 계약에 명시.


### 2026-09-15 — RUN-1 완료

- 시작: 깨끗한 develop에서 `feature/run-reports` 분기, RUN-1을 진행으로 변경.
- 변경: `api_test/reports.py`, CLI, runner timeout 분류, 웹 실행 서비스, OpenAPI RunResponse·생성 모델에 공통 보고서 연결. `docs/run-result.schema.json`, `docs/run-reports.md`, 신규 테스트 추가.
- 검증: Python 229개 중 187개 통과·42개 skip. JSON/JUnit 성공·실패·오류·timeout 및 비밀값 제외, 실제 CLI 설정 오류 보고서, pipeline 실패 중단, 웹 Run ID·임시 파일 정리 확인. schema 및 재생성 --check·diff check 통과.
- 환경: 기본 Python에 OpenAPI Generator가 없어 기존 `/private/tmp/fnd4-venv`의 고정 버전 생성기로 재생성·검증 완료.
- 제한: 상세 결과 DB 저장, 비동기 job·취소는 포함하지 않음. 기존 300초 서버 timeout 계약 유지. version·commit은 배포 환경변수 미지정 시 null.
- 다음: RUN-2 job lifecycle·실행 제한 구현. 커밋·병합·푸시는 미수행.

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

## FND-2 develop 통합 및 FND-3 착수 (2026-09-14)

- 상태: 완료. 사용자 승인으로 FND-2를 develop에 병합.
- 충돌 해결: route 분리와 Example 공개 fixture 표시·읽기 전용 차단을 함께 보존.
- 검증: Python 152개, frontend 8개, Vite build, diff check와 충돌 마커 검사 통과.
- 다음: FND-3 전용 브랜치에서 HTTP 계약 및 FastAPI 전환.

## FND-3 FastAPI 전환 (2026-09-14)

- 시작: `feature/fnd-3-fastapi`, FND-2 통합 커밋 `df3ca9a` 기준.
- 상태: 완료. 기존 HTTP 계약을 유지하며 FastAPI route, 요청별 정책/응답, Uvicorn 단일 worker로 전환.
- 변경: handler 직접 테스트를 TestClient로 이전, 중첩 reference/revision, 오류·cookie·upload·ZIP·SPA 계약 고정. API 서버의 StudioHandler 제거.
- 검증: macOS Python 3.13 및 Docker Python 3.12에서 각각 166개, frontend 8개, Vite build, 실제 HTTP 비교 13개, 실제 예제 pipeline 3개 PASS, React 호출/케이스/대시보드, Docker build·동일 healthcheck healthy·실제 SDK ZIP 통과.
- 차단 해소: Git metadata/Docker socket/loopback sandbox 제한은 승인된 재실행으로 해소. 이미지 조회 지연 후 빌드 완료. 테스트 fixture 경로 및 no-op revision 기대값 오류 수정 후 통과.
- 운영 제한: 1 worker 유지. 기존 서비스 교체·원격 푸시 없음. 분리된 encryption 서버의 HTTP 구현은 유지.
- 다음: FND-4. 상세 계약과 검증 범위는 `docs/fnd-3-http-contract.md` 참조.

## FND-4 저장소 전환 (2026-09-14)

- 상태: 완료 — `feature/fnd-4-postgres-redis` 로컬 구현·검증
- 시작: PostgreSQL 영구 저장소, SQLite 읽기 전용 이관, Redis metadata 캐시와 장애 fallback 구현. 실행 이력 저장소도 같은 전환 범위로 검증한다.
- 기준: 기존 HTTP/revision 계약 보존, DB commit 이후 JSON 투영, 이관 검증 실패 시 rollback.

- 변경: DB connection/pool 경계, Studio schema v3와 ownership v2, workspace·사용자·membership·identity 계약, SQLite 읽기 전용 snapshot 이관/전체 row 검증, commit 이후 투영 및 복구 명령, Redis revision metadata cache, Docker 내부 저장소와 secret 파일 설정.
- 결정: 기존 local workspace ID `default`와 시스템 ID `local-user`, `memberships` 테이블명을 보존. 저장소 인스턴스에 불변 RequestContext를 바인딩하고 HTTP 주체는 고정 서버 문맥으로 유지. 일반 문서/OpenAPI에 민감정보가 포함될 수 있어 Redis는 revision metadata만 캐시. HTTP 사용자 선택과 완전한 실행·artifact RBAC는 COL-2/COL-1에서 연결.
- 검증: `/tmp/fnd4-venv/bin/python -m unittest discover -s tests -q`에 FND4 테스트 서비스 URL을 제공하여 206개 모두 통과(skip 없음). 빈/이관 PostgreSQL에 기존 HTTP matrix 각각 14개, PostgreSQL·Redis·복구 테스트 12개 포함. frontend 8개·Vite build·Python compile·diff check 통과.
- 실제 검증: 분리된 `fnd4-validation` Compose 이미지 build와 API/PostgreSQL/Redis/encryption healthcheck 통과. 실제 CRUD·revision 409·body/actor 신뢰 경계·soft-delete·정책 차단 subprocess의 Run ID/대시보드 저장 통과. Redis 중단 중 HTTP fallback 200, PostgreSQL 중단 중 503, DB 재시작 뒤 API 재시작 없는 pool 복구 확인. `pg_dump` → 새 DB `pg_restore` 후 문서 수와 ID/revision/hash/삭제 상태 digest 일치. 최종 이미지의 `repair_projections --all` 통과.
- 환경 차단 및 해소: 최초 Git ref 쓰기, Docker socket·로컬 PostgreSQL TCP가 sandbox에 차단되어 해당 작업에 한정한 권한 확장 후 검증 완료. 처음 추가한 SQLite WAL 설정의 동시 접속 lock 오류는 중복 설정을 제거해 해소.
- 완료 범위: 개발·검증과 두 진행 문서 갱신. 원본 데이터 실제 이관, 기존 환경 배포, 커밋·병합·푸시는 수행하지 않음.

## API-1·API-2·API-3 (2026-09-14)

- 시작: feature/api-exploration-profiles, 기존 빠른 호출·암호화 변수·인증 처리 재사용.
- 변경: 환경 저장·조회·암호화 보존, 공통→환경→케이스 변수 적용, CLI --environment와 웹 실행 연결. No Auth·API Key header/query·Basic·Bearer 프로필을 빠른 호출·케이스·파이프라인에서 재사용.
- 변경: 빠른 호출 JSON/Text/Form Data, 응답 크기·마스킹, 응답 대기 취소·재실행, cURL 복사, case/{tag}/{api_name}/{case_file}.json 저장. 케이스 편집기의 Text·프로필 보존과 환경 선택 지원.
- 검증: 저장·조회 FastAPI 계약, 세 환경, 인증 방식, 케이스 override, 빠른 호출/저장 케이스 전송 URL·인증·본문 일치, 파이프라인 적용·로그 마스킹, 화면 실행·저장·취소 테스트 통과.
- 회귀: python3 -m unittest discover -s tests -q — 217개 중 176개 통과·외부 PostgreSQL/Redis 설정 의존 41개 skip. web/의 npm test 14개, npm run build, git diff --check 통과.
- 조정: 응답 sizeBytes 추가에 맞춰 기존 계약 기대값 3개 갱신. 환경 주소를 소유권 fingerprint와 검증 허용 목록에 포함.
- 상태: 완료 — API-3은 문서에 명시된 1차 인증 범위. 서버 전송 강제 종료·OAuth 2.0 발급·외부 서비스 종단 검증은 포함하지 않음.
- 최종 반영: feature/api-exploration-profiles 작업 트리. 커밋·병합·푸시 없음.

## OpenAPI Generator 서버 구조 전환 (2026-09-14)

- 시작: feature/openapi-generated-server. 기존 API-1·2·3 미커밋 변경을 보존하여 이어서 작업.
- 시작 상태: 진행 — Studio 명세와 생성 라우터·모델, 구현 계층, 앱 진입점 분리 및 재생성 검사. 완료 결과는 아래 2026-09-15 기록 참조.
- 계약: 기존 400/409 오류, secret 보존, 경로 reference, 업로드 제한, 동기 작업 thread pool을 유지.

### OpenAPI Generator 전환 변경·검증·완료 (2026-09-15)

- 변경: openapi/studio.yaml에 프로젝트·케이스·파이프라인·실행·OpenAPI·소유권·업로드·Example 명세 작성. api_test/generated는 Generator가 생성하며 서비스 코드는 별도 유지.
- 변경: api_test/main.py에서 생성 APIRouter를 등록. dependencies.py에서 origin·업로드 제한·thread pool 유지. 기존 업무 operation을 services/로 이동하고 기존 routes/는 호환 어댑터로 전환. react_server.py는 호환 진입점으로 축소.
- 조정: 기본 Generator 모델의 자유 형식 object 상속/import 문제를 사용자 템플릿으로 해소. DTO는 BaseModel과 extra=allow를 사용하고 명시적 null·추가 필드·별칭을 보존. 입력 업무 검증은 기존 서비스에서 수행하여 기존 400/409와 원문 숫자 표현을 유지.
- 검증: python3 -m unittest discover -s tests -q — 222개 중 181개 통과, 외부 PostgreSQL/Redis 설정 의존 41개 skip. web/ npm test 14개 및 npm run build, Python compile, git diff --check 통과.
- 재생성: /tmp/fnd4-venv/bin/python scripts/generate_server.py --check 통과. 모든 operation의 생성 route/implementation 연결과 DTO read/write 계약 검사 추가. CI는 requirements.txt의 동일 고정 버전으로 검사.
- 실제 HTTP: 임시 SQLite·임의 loopback 포트 Uvicorn에서 schema, 프로젝트/케이스 CRUD, revision suffix와 실제 빠른 HTTP 전송 통과. 최초 bind 차단은 검증 명령에 한정된 권한 확장으로 해소. 검증 fixture의 macOS /var→/private/var 경로 차이는 fixture resolve로 해소.
- 완료: feature/openapi-generated-server 로컬 변경. 기존 API-1·2·3 작업 포함 보존. 커밋·병합·푸시·배포·실제 PostgreSQL/Redis 재검증은 수행하지 않음.

### Docker PostgreSQL 기동·SQLite 이관 복구 (2026-09-15)

- 시작: Docker Compose 기동 시 기존 SQLite 이력 보호가 `/api/cases` healthcheck를 400으로 반환해 API가 healthy 상태에 도달하지 못함.
- 변경: PostgreSQL DB·ID·PW를 `.env`의 `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`로 관리하고 API 연결 URL을 Compose가 구성하도록 변경. 기존 secret-file mount를 제거.
- 변경: SQLite 이관이 API 첫 기동으로 생긴 빈 `default/local-user` bootstrap context만 transaction 안에서 제거한 뒤 snapshot으로 대체하도록 수정. 문서·실행·ownership·identity 또는 다른 context가 하나라도 있으면 기존대로 rollback한다.
- 검증: Python 223개 중 181개 통과·외부 서비스 설정 의존 42개 skip, Compose build·config 통과. 실제 Compose에서 PostgreSQL·Redis·encryption healthy, SQLite snapshot의 workspaces 1·users 2·memberships 2·documents 10·revisions 19·audit 20 digest 이관 통과, API healthcheck `/api/cases` 200 및 web 기동 확인.
- 상태: 완료 — Docker 서비스는 실행 상태로 유지. 커밋·병합·푸시는 수행하지 않음.

### OpenAPI 명세 components·tag별 분리 (2026-09-15)

- 변경: `openapi/studio.yaml`은 메타데이터와 외부 `$ref` 조합만 유지하고 `components/headers.yaml`, `components/schemas/{tag}.yaml`, `paths/{tag}.yaml`로 명세를 분리. 여러 tag 공유 모델은 `schemas/common.yaml`에 유지.
- 변경: API 앱은 외부 참조를 해석한 self-contained `/api/schema.json`을 반환하고 내부 `x-studio-*` binding 정보는 제거.
- 검증: OpenAPI Generator 7.24.0 `--check`, Python 224개 중 182개 통과·42개 외부 서비스 설정 의존 skip, frontend 14개·build·diff check 통과. 실제 API 컨테이너에서 20개 path·41개 schema·2개 header 반환 확인.
- 상태: 완료 — 생성 라우터 결과와 기존 HTTP 계약 유지.

## MOCK-1 잔여 항목 개발 — 검증 분리 (2026-09-21)

- 검증 인계 문서: [MOCK-1 계획 이행 검증서](archive/mock-1/verification-plan.md). 계획 요구사항 매핑, M01–M20, 최근 6개 수정, 실제 HTTP/브라우저 및 결과 양식 작성 완료. 검증 실행은 별도 대기.

- 시작: 사용자의 “mock-1 개발 진행 검증은 별도로 진행” 요청에 따라 `feature/mock-server`, 로컬 커밋 `0a6151f` 이후 개발 재개.
- 변경: 동일 seed/scenario 설정 시 state 보존, /api/docs의 해석된 operation 및 media/example 이름을 Mock 화면으로 연결, 생성 schema의 최종 제약 검사와 깊이/배열 제한 명시 오류, 정수 소수 경계 처리, override 필드 타입 검사.
- 변경: 명시적 example/media 선택 시 명세 응답 재생으로 처리하며 CRUD state 비변경. 선택되지 않은 일반 CRUD 동작은 유지. 해당 정책과 seed/scenario 변경 초기화 정책을 UI에 표시.
- 변경: smoke 동시성 수만큼만 제출, 남은 deadline으로 요청 timeout 제한, 미완료 요청 실패 집계와 queued 작업 취소, deadline 이후 executor 종료 대기 제거. 진행 중 요청은 socket timeout 안에서 종료되며 강제 thread 종료를 보장하지 않음.
- 회귀 테스트: state 보존·schema 거부/정수 경계·입력 타입·CRUD media/example·smoke deadline 테스트 작성, 기존 순환 schema와 UI fixture를 변경된 계약에 맞게 수정.
- 검증: 사용자 요청으로 Python/frontend 테스트·build·브라우저·실제 HTTP 검증은 이번에 실행하지 않음. 따라서 결함 해소 검증 완료 또는 MOCK-1 전체 완료로 판정하지 않는다.
- Git: 이번 수정은 미커밋. 이전 `0a6151f`는 로컬 커밋이며 원격 푸시 자동 검토 차단과 develop 병합 보류 상태는 별도 작업으로 남음.

## MOCK-1 2차 수정 검증 (2026-09-21)

- 시작: 개발 모델의 R1–R8 수정 및 회귀 테스트를 독립 검증.
- 결과: resource 격리·ID 충돌·오류 status·pipeline 본문 검증 수정 확인. 설정 적용 시 state 소멸, operation UI 데이터 경로 불일치, schema 위반, override 타입 불일치, CRUD media/example 무시, smoke deadline 미준수 발견.
- 검증: Python 288개 중 246 통과/42 skip, frontend 27개 및 build, 생성 검사·diff check 통과. 추가 ASGI/schema validator/smoke stub으로 잔여 문제 재현. 자세한 결과는 [당시 리뷰](archive/mock-1/review.md) 참조.
- 차단: 브라우저용 임시 loopback 서버 실행은 자동 승인 검토 사용량 한도로 미실행. 실제 브라우저 재검증은 완료하지 않음.
- 완료 범위: 코드 수정에 대한 2차 리뷰, 문서 갱신. MOCK-1은 진행 유지. 제품 코드 수정·커밋·병합·푸시 없음.

## MOCK-1 독립 리뷰 (2026-09-21)

- 시작: `feature/mock-server`의 develop 대비 diff와 untracked 구현을 기존 인계 기준으로 검토.
- 결과: [리뷰 및 수정 인계](archive/mock-1/review.md)의 R1–R8 발견. 리소스 state 혼합·ID 덮어쓰기·status 무시·schema 제약 위반·관리 API 500·본문 검증 누락을 재현. UI 선택 기능과 media type 처리 미충족 확인.
- 검증: 전체 Python 282개 중 240 통과/42 PostgreSQL 관련 skip, frontend 26개 및 build, 생성 코드 검사 통과. 최초 sandbox bind/ps 제한은 권한 확장 재실행으로 해소.
- 실제 브라우저: 임시 DB/fixture로 시작→새로고침 복원→오류 설정→HTTP 500 확인→reset→중지, 콘솔 error 없음. 기존 pipeline/smoke 테스트도 실행했으나 본문 검증 누락으로 내용 정확성 보장은 불가.
- 상태: 진행 — 리뷰 완료, 구현 수정과 재검증 대기. 구현 코드 변경·커밋·병합·푸시 없음. 하단의 개발 모델 완료 보고보다 이 독립 검증 판정을 우선한다.

## MOCK-1 OpenAPI 기반 Mock Server 구현 — 개발 모델 보고 (2026-09-21)

- 상태: 완료 — `feature/mock-server`, clean develop `f033c44` 분기 기준에서 구현 완료. 커밋·병합·푸시는 수행하지 않음.
- 시작: [개발 인계 프롬프트](archive/mock-1/development-prompt.md)에 따라 API·화면·테스트·사용 안내 및 부하 smoke 구현.
- 변경 파일:
  - 계약 및 라우터: `openapi/paths/mock.yaml`, `openapi/components/schemas/mock.yaml`, `openapi/studio.yaml`, `openapi/templates/api.mustache`, `api_test/generated/` (OpenAPI Generator 7.24.0으로 라우터·모델 64개 갱신)
  - 코어 엔진 및 서비스: `api_test/mock_engine.py` (정적 경로 우선 라우팅, Example 우선순위 및 Schema 결정적 합성, 순환참조 깊이 10 제한, 선언형 CRUD state 머신 및 reset, 204/HEAD 무본문 처리, 비차단 latency), `api_test/services/mock.py` (Loopback 127.0.0.1/::1/localhost 전용 바인드 정책, 포트 충돌 감지 및 자동 할당, 생명주기 제어), `api_test/implementations/mock.py`, `api_test/main.py` (lifespan 앱 종료 시 Mock 서버 정리)
  - 부하 smoke 하네스: `api_test/mock_smoke.py` (동시 HTTP 부하 실행, 지연시간 분위수 및 통계 산출)
  - 프론트엔드 UI: `web/src/pages/apis/MockServerPanel.jsx` (실시간 상태·URL·포트·요청수 표시, 시작/중지/초기화/설정갱신, 시나리오/지연/Seed 설정), `web/src/pages/apis/MockServerPanel.test.jsx`, `web/src/pages/apis/ApiList.jsx`
  - 테스트: `tests/test_mock_server.py` (우선순위, 결정성, 제약조건, loopback 정책, 포트 충돌, 생명주기 관리 API 11개 단위/통합 테스트), `tests/test_mock_pipeline.py` (임시 fixture 기반 실제 HTTP loopback Mock 서버 대상 3단계 파이프라인 및 부하 smoke 테스트), `tests/test_generated_server.py`
  - 문서: `docs/api-development-progress.md`, `docs/api-load-test-progress.md`
- 검증:
  - OpenAPI 생성 검사: `python3 scripts/generate_server.py --check` 통과 ("Generated server is up to date.")
  - Python 전체 테스트: `python3 -m unittest discover -s tests -v` — 282개 테스트 중 240개 통과, 42개 skip (외부 PostgreSQL URL 미설정 의존), 0 failures, 0 errors.
  - Frontend 검증: `web/`에서 `npm test` (10개 테스트 파일 26개 테스트 전체 통과), `npm run build` (Vite 8.2.1 클라이언트 빌드 정상 완료).
  - 실제 HTTP 파이프라인: 임시 fixture 프로젝트에서 Mock 서버 시작 후 Setup 생성(`POST /items`) → ID 추출(`body.id`) → 조회(`GET /items/${run.item_id}`) → 의도한 404 오류 검증(`GET /items/non-existent-9999`) 3단계 파이프라인 PASS.
  - 동시 HTTP 부하 Smoke: `example-api.json` 대상 loopback 127.0.0.1:8940에서 10 동시성·100회 요청 실행 결과 성공 100건(에러율 0.0%), 1927.5 RPS, p50 4.30ms, p95 8.04ms, max 10.35ms.
  - 브라우저 검증: 백엔드/React 서버 정상 기동(curl 200 OK) 확인 후 브라우저 서브에이전트 실행 시 Playwright mac-arm64 zip 다운로드 404 환경 문제 발생하여 브라우저 자동 탐색은 중단하고 Vitest JSDOM UI 테스트로 화면 동작 검증.
  - 코드 포맷: `git diff --check` 통과.
- 제한사항:
  - Mock 서버는 보안 정책상 Loopback(127.0.0.1, ::1, localhost) 주소로만 바인드할 수 있으며, 0.0.0.0 또는 외부 IP 바인드는 거부됨.
  - Mock state는 프로세스 메모리에 유지되며, 서버 중지 시 정리되고 재시작 시 초기 시나리오 상태로 시작됨.

## MOCK-1 개발 인계 준비 (2026-09-21)

- 상태: 완료 — 인계 프롬프트 준비 및 구현 완료.
- 시작: 변경사항 없는 로컬 develop `f033c44`에서 `feature/mock-server` 생성. 원격 최신성은 확인하지 않음.
- 변경: [개발 인계 프롬프트](archive/mock-1/development-prompt.md)에 요구사항, 기존 구현 진입점, state·bind 정책, 실제 HTTP/브라우저/부하 smoke 및 후속 독립 리뷰 기준 작성.
- 검증: 브랜치와 작업 트리 확인, `git diff --check` 통과. 문서만 변경하여 코드 테스트와 build는 실행하지 않음.
- 환경: 최초 브랜치 생성은 sandbox의 Git 쓰기 제한으로 실패했고 권한 확장 재실행으로 완료. 현재 차단 사항 없음.
- 다음: 사용자가 선택한 다른 AI 모델의 구현 완료 후 Codex에서 diff 리뷰 및 독립 검증. 이번 작업에서는 모델 실행·기능 구현·커밋·병합·푸시를 수행하지 않음.

## 이전 작업: TST-1·TST-2·TST-3 (2026-09-20)

- 상태: 완료 — `feature/test-coverage-lifecycle`, clean develop에서 분기.
- 시작: 명세 operation/status 커버리지, 사용자 검증 보존 동기화 preview, run별 generator·변수 추출·setup/teardown 구현.
- 보존 규칙: assertion, body, headers, 인증 및 secret은 동기화 대상에서 제외. 생성 기준과 일치하는 method/path/status만 선택 갱신.
- 정리 단계는 본 실행 실패 후에도 수행하며 결과에 phase를 남긴다. 프로세스 강제 종료에서는 정리를 보장하지 않는다.

- 의미 있는 변경: 명세 연결 fingerprint와 보수적 선택 갱신 API/화면, saved-case 결과 metadata, phase별 실행 결과 및 generator/추출 입력 UI. OpenAPI 생성 route/DTO 동기화.
- 검증: 전체 Python 268개 실행(226 통과, 전용 PostgreSQL URL 미설정 42 제외), 후속 응답 범위/default 보완 후 관련 테스트 10개 통과. frontend 24개 및 Vite build 통과. 생성 코드 최신성 검사·git diff --check 통과.
- 실제 HTTP: 임시 로컬 서버에서 setup 응답 추출 → 본 테스트 500 실패 → teardown 200 성공, 추출 변수 전달 및 mainStatus/cleanupStatus 분리 확인.
- 브라우저: 임시 DB에서 미검증 응답, field preview, 선택 저장, 새로고침 후 명세 일치, generator/seed/추출/setup·teardown 저장·복원 확인. 최종 콘솔 오류 없음.
- 검증 환경: 로컬 bind와 프로세스 조회 제한은 허용된 재실행으로 해결. 도구 의존성은 /private/tmp/tst-deps에만 설치. 임시 서버 초기 ROOT 설정 오류를 수정해 저장 검증 완료; 사용자 데이터는 사용하지 않음.
- 제한: sync 자동 변경은 생성 기준과 동일한 method/url/status만, body/assertion은 직접 검토. component 변경은 보수적 영향 표시. operationId 없는 경로 변경은 재연결 필요. 강제 종료·취소·전체 timeout의 teardown은 보장하지 않음. PostgreSQL 통합 재검증은 전용 URL 미제공으로 제외.
- 사용 안내: [테스트 커버리지와 데이터 수명주기](test-coverage-lifecycle.md).
- Git: 커밋·병합·원격 반영 없음.
