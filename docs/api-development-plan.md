# API 개발 기능 로드맵

## 1. 목적

API Develop Studio를 API 명세 작성 도구나 단순 테스트 실행기에 머물지 않고, 다음 개발 흐름을 하나의 제품에서 수행할 수 있는 REST/OpenAPI 개발 워크벤치로 확장한다.

```text
OpenAPI 가져오기 또는 작성
  → 실행 환경과 인증 선택
  → 빠른 요청으로 탐색
  → 재사용 가능한 케이스 저장
  → 파이프라인과 CI에서 검증
  → 실행 이력과 성능 결과 분석
  → 계약 변경과 회귀 관리
```

이 계획은 현재 REST와 OpenAPI 중심 구조를 우선 완성한다. GraphQL, gRPC, WebSocket과 AsyncAPI는 핵심 흐름이 안정화되고 실제 요구가 확인된 뒤 확장한다.

## 2. 현재 기준과 보유 기능

현재 기준 브랜치는 `feature/developer-docs`이며 기능 코드는 `786d0e3` 이후 상태를 기준으로 분석했다. 통합 대상은 실제 개발을 시작할 때 최신 통합 브랜치에서 다시 확인한다.

현재 제공 기능은 다음과 같다.

- 프로젝트별 Base URL, proxy, TLS, 일반 변수와 암호화된 보안 변수
- API 케이스 작성과 저장하지 않은 현재 값 실행
- 상태 코드, JSON body, assertion과 최대 응답 시간 검증
- 파이프라인, 재시도, 단계 간 응답값 전달
- OpenAPI 3.x·Swagger 2.0 가져오기와 케이스 초안 생성
- OpenAPI 3.x operation 추가와 YAML bundle 저장
- Python, JavaScript, TypeScript, Java, Kotlin, Go, C# SDK 생성
- SQLite 불변 리비전, 낙관적 잠금, 감사 이벤트와 JSON 투영
- CLI, Docker Compose와 내장 예제 API

주요 기능 격차는 다음과 같다.

- 프로젝트당 Base URL이 하나라 개발·검증·운영 환경 전환이 어렵다.
- 현재 케이스 편집기의 인증 UI는 Bearer Token 중심이다.
- OpenAPI 작성은 operation 추가 중심이며 기존 operation, component schema와 security scheme의 편집이 제한적이다.
- CLI 결과가 사람용 출력과 로그 중심이라 CI 보고서와 장기 이력에 적합한 구조화 결과가 부족하다.
- `/api/run`과 SDK 생성은 HTTP 요청 thread에서 하위 프로세스를 동기 실행한다.
- 프런트엔드 자동화 테스트 기반이 없다.
- `X-Studio-Actor`는 감사 식별자이며 인증과 권한 검증이 아니다.

## 3. 개발 원칙

- 현재 JSON 케이스와 CLI 호환성을 유지한다.
- 요청 생성 규칙은 빠른 호출, 저장 케이스와 파이프라인이 공통 모듈을 사용한다.
- 환경별 secret은 평문으로 투영하거나 응답·로그·실행 이력에 남기지 않는다.
- 명세, 케이스와 실행 결과는 서로 추적 가능한 안정 ID를 갖는다.
- 장기 실행 작업은 HTTP request thread와 분리하고 동시 실행 수를 제한한다.
- 새 데이터 구조는 schema version과 migration, 백업 및 복구 방법을 함께 제공한다.
- UI 기능에는 loading, empty, error, 충돌과 좁은 화면 상태를 포함한다.
- 구현과 검증 진행은 [`API 개발 기능 진행 기록`](api-development-progress.md)에 같은 작업 안에서 갱신한다.

## 4. 우선순위

### P0 — 일상적인 API 개발 흐름

| ID | 기능 | 사용자 가치 | 최소 범위 |
| --- | --- | --- | --- |
| FND-1 | 기능 브랜치 안전 통합 | 이미 개발된 기능을 회귀 없이 활용 | 빠른 호출·실행 대시보드를 최신 통합 기준으로 이식 |
| FND-2 | 테스트와 migration 기반 | 기능 증가에 따른 회귀와 DB 호환성 방지 | frontend test, DB schema version, migration runner |
| API-1 | 빠른 API 호출 | 케이스 저장 전 API 탐색 | method, URL, params, auth, headers, body, response와 저장 전환 |
| API-2 | 환경 프로필 | 같은 케이스를 Local·Dev·Stage에서 재사용 | 환경별 Base URL, 변수 override, 활성 환경 선택 |
| API-3 | 공통 인증 모델 | 인증 API를 반복 설정 없이 실행 | API Key, Basic, Bearer, OAuth 2.0과 secret 참조 |
| RUN-1 | 구조화된 실행 결과 | 웹·CLI·CI가 같은 판정 사용 | run ID, target별 결과, 오류 분류, JSON과 JUnit 출력 |
| RUN-2 | 비동기 실행 작업 | 장기 실행의 timeout과 자원 고갈 방지 | job 제출, 상태 조회, 취소, 동시 실행 제한 |
| OAS-1 | OpenAPI 편집 완성 | 실제 계약을 지속적으로 유지 | operation 수정·삭제, schema, security scheme, response 편집 |
| OAS-2 | 계약 검증 | 명세와 구현의 불일치 조기 탐지 | lint, 실제 응답 schema 검증, breaking change 검사 |

### P1 — 테스트 품질과 관측성

| ID | 기능 | 사용자 가치 | 최소 범위 |
| --- | --- | --- | --- |
| TST-1 | 명세–케이스 커버리지 | 테스트가 빠진 API와 응답 탐지 | operation·status별 연결 케이스와 커버리지 |
| TST-2 | 케이스 동기화 | 명세 변경에 따른 테스트 유지 비용 감소 | 영향 케이스 표시, 변경 preview, 선택적 갱신 |
| TST-3 | 테스트 데이터 수명주기 | 동적 데이터와 정리 작업 지원 | 내장 generator, 추출 변수, setup·teardown |
| MOCK-1 | 명세 기반 Mock Server | API 구현 전 클라이언트와 테스트 개발 | example/schema 응답, status·latency·error 선택 |
| OBS-1 | 실행 이력 | 실패 재현과 품질 추세 확인 | 기능 테스트 run 목록, 상세, 검색, 실패 재실행 |
| OBS-2 | 부하테스트 결과 | 처리량과 latency 회귀 확인 | 별도 부하테스트 계획의 목록·상세·비교 대시보드 |
| IOP-1 | 가져오기·내보내기 | 기존 도구 자산 재사용 | cURL, Postman Collection·Environment, HAR |

### P2 — 팀 운영과 확장

| ID | 기능 | 사용자 가치 | 최소 범위 |
| --- | --- | --- | --- |
| COL-1 | 로그인과 RBAC | 외부 다중 사용자 환경의 안전한 협업 | session, Owner·Editor·Runner·Viewer 권한 |
| COL-2 | Workspace 격리 | 팀별 프로젝트와 secret 분리 | 모든 문서·실행·secret query에 workspace 적용 |
| GOV-1 | API lifecycle 관리 | 버전과 폐기 정책 추적 | release, changelog, deprecated 표시와 승인 기록 |
| DOC-1 | 개발자 문서 portal | 소비자가 명세와 예제를 쉽게 탐색 | OpenAPI 기반 검색·예제·인증 안내 |
| EXT-1 | 비동기·비REST 프로토콜 | 제품 적용 범위 확장 | 수요에 따라 WebSocket·AsyncAPI·GraphQL·gRPC 순차 검토 |

## 5. 단계별 개발 계획

### 0단계 — 통합 기준과 안전망

#### FND-1 기능 브랜치 통합

현재 다음 원격 브랜치에 선행 구현이 있다.

- `origin/feature/quick-api-call`: 빠른 호출과 Postman 형식 인증
- `origin/feature/api-execution-dashboard`: 실행 metadata 저장과 대시보드

두 브랜치는 `0e1d278`을 공통 기준으로 하며 현재 통합 코드보다 뒤에 있다. 원본 브랜치를 직접 병합하기보다 최신 통합 브랜치에서 새 기능 브랜치를 만들고 필요한 변경을 기능 단위로 이식한다.

통합 순서:

1. 저장소 규칙의 `develop`과 실제 `origin/dev` 중 사용할 통합 브랜치를 확정한다.
2. 빠른 호출의 request·authorization 공통 모듈부터 이식한다.
3. 현재 응답 시간 검증, OpenAPI bundle, Docker 변경과 기존 테스트를 보존한다.
4. 실행 대시보드의 저장 모델을 RUN-1 공통 실행 모델과 정렬한 뒤 이식한다.
5. 브라우저 URL 직접 접근, 뒤로 가기와 모바일 화면을 회귀 검증한다.

주의사항:

- 기존 branch diff에서 후속 `tests/test_runner.py` 일부가 삭제된 형태로 보이므로 삭제를 통합 결과에 반영하지 않는다.
- 빠른 호출 branch의 Digest·NTLM은 자격정보 검증만 있고 실제 handshake를 완료하지 않으므로 지원 완료로 표시하지 않는다.
- 실행 대시보드는 요청·응답 본문과 인증정보를 저장하지 않는 원칙을 유지한다.

완료 기준:

- 최신 통합 기준의 기능 테스트가 모두 유지된다.
- 빠른 호출과 저장 케이스가 같은 요청 직렬화와 인증 함수를 사용한다.
- 기능 실행 이력이 구조화된 공통 run ID로 저장된다.
- 전체 Python 테스트, frontend test와 `npm run build`가 통과한다.

#### FND-2 기반 구조

- `react_server.py`의 문서, 실행, OpenAPI와 대시보드 route handler를 모듈로 분리한다.
- `web/src/App.jsx`의 공통 shell, 빠른 호출, 편집기와 대시보드를 별도 컴포넌트로 분리한다.
- SQLite에 schema version 테이블과 순서가 보장된 migration runner를 추가한다.
- Vitest와 React Testing Library를 도입해 router, form 변환과 주요 상태를 검증한다.

완료 기준:

- 기존 API와 URL이 변경 없이 동작한다.
- 빈 DB와 이전 DB 모두 최신 schema로 올라간다.
- migration 실패 시 기존 DB가 부분 변경되지 않는다.
- frontend의 loading, empty, error와 router 테스트를 CLI에서 실행할 수 있다.

### 1단계 — 탐색, 환경과 인증

#### API-1 빠른 API 호출

- method, URL, query, header, JSON·text·form-data body 편집
- response status, headers, body, 크기와 전체 소요 시간 표시
- 요청 취소, 다시 실행, cURL 복사와 민감 header 마스킹
- 현재 요청을 새 케이스로 저장하거나 기존 케이스 편집기로 전달

완료 기준: 저장하지 않은 요청을 실행한 뒤 같은 값으로 케이스를 생성해 동일한 HTTP 요청이 전송된다.

#### API-2 환경 프로필

프로젝트의 공통 설정과 환경별 override를 분리한다.

```json
{
  "default_environment": "dev",
  "environments": {
    "local": {"base_url": "http://127.0.0.1:8080", "variables": {}},
    "dev": {"base_url": "https://dev.example.com", "variables": {}},
    "stage": {"base_url": "https://stage.example.com", "variables": {}}
  }
}
```

- 기존 `base_url` 프로젝트는 migration 없이 기본 환경처럼 계속 동작한다.
- 활성 환경은 실행 요청 또는 CLI option으로 선택하며 케이스 파일에 고정하지 않는다.
- 공통 변수 위에 환경 변수를 적용하고 케이스 변수를 마지막에 적용한다.
- secret override는 현재 암호화 서비스로 암호화하고 조회 시 configured 상태만 반환한다.

완료 기준: 하나의 케이스를 파일 수정 없이 세 환경에 실행할 수 있고 선택 환경과 secret이 로그에 노출되지 않는다.

#### API-3 공통 인증 모델

- 1차: No Auth, API Key header/query, Basic, Bearer
- 2차: OAuth 2.0 client credentials와 authorization code
- 후속: 실제 수요가 있는 경우 OAuth 1.0, AWS Signature, Hawk 등
- Digest·NTLM은 사용 가능한 HTTP client와 handshake 테스트가 준비될 때만 지원한다.

인증 설정은 프로젝트 또는 환경에서 이름을 붙여 재사용하고 케이스는 reference만 선택한다. 임시 token은 영구 JSON 투영본에 저장하지 않는다.

완료 기준: 빠른 호출, 케이스와 파이프라인이 같은 인증 profile을 사용하며 token·password·key가 API 응답, 로그와 실행 이력에 노출되지 않는다.

### 2단계 — 실행 자동화와 CI

#### RUN-1 구조화된 실행 결과

공통 결과 schema에 다음을 포함한다.

- run ID, project, environment, actor, app version과 commit
- case·pipeline target과 단계별 시작·종료 시각
- passed, failed, error, timeout, cancelled 상태
- HTTP status, elapsed time과 assertion별 판정
- secret이 제거된 오류 원인과 artifact reference

CLI에 `--report-json`과 `--report-junit`을 추가한다. 사람용 stdout, 웹 API와 CI report가 같은 결과 객체에서 만들어지게 한다.

완료 기준: 같은 실행의 CLI exit code, JSON, JUnit과 웹 판정이 일치하고 CI에서 실패 case 이름과 원인을 확인할 수 있다.

#### RUN-2 비동기 실행 작업

- `POST /api/runs`는 job ID를 즉시 반환한다.
- `GET /api/runs/{id}`로 상태와 결과를 조회한다.
- `POST /api/runs/{id}/cancel`로 허용된 실행을 취소한다.
- worker 수와 사용자·프로젝트별 queue 한도를 설정한다.
- SDK 생성과 향후 부하테스트 실행도 같은 job lifecycle을 재사용한다.

완료 기준: 브라우저 연결이 끊겨도 실행이 추적되고, timeout·취소 후 하위 프로세스와 임시 파일이 남지 않으며 queue 한도를 넘는 요청이 명확히 거부된다.

### 3단계 — 계약 중심 개발

#### OAS-1 OpenAPI 편집 완성

- operation 수정·삭제와 operationId 중복 검증
- component schema CRUD와 schema reference 선택
- security scheme과 operation별 security 적용
- request·response media type, header와 여러 status 편집
- required, enum, nullable, format, constraint와 example 관리
- 저장 전 전체 문서 validation과 변경 preview

완료 기준: 외부 편집기 없이 대표 OpenAPI 3.x 문서의 operation, schema, 인증과 오류 응답을 작성·수정하고 다시 가져왔을 때 의미가 보존된다.

#### OAS-2 계약 검증과 변경 감지

- OpenAPI 구조와 조직 규칙 lint
- 실제 response status, content type, header와 body schema 검증
- 기준 revision과 현재 revision 사이 breaking change 탐지
- path·method 삭제, required 추가, type 축소와 response 제거를 분류
- 허용된 breaking change의 사유와 승인 기록

완료 기준: 호환 변경과 breaking change fixture를 안정적으로 구분하고 CI에서 breaking change를 차단할 수 있다.

#### TST-1·TST-2 커버리지와 동기화

- operation과 status별 연결 케이스 수 및 최근 성공 시각 표시
- 명세가 바뀐 operation과 영향받는 케이스 표시
- 자동 갱신 전에 field별 변경 내용을 preview
- 사용자 편집 assertion과 secret은 자동 갱신에서 보존

완료 기준: 미검증 operation과 response를 찾을 수 있고, 명세 갱신이 사용자 작성 검증을 임의로 덮어쓰지 않는다.

### 4단계 — Mock, 데이터와 관측성

#### MOCK-1 Mock Server

- OpenAPI example 우선, 없으면 schema 기반 결정적 응답 생성
- status, latency와 오류 응답 선택
- 고정 seed와 scenario별 state 지원
- 외부 공개 방지와 bind host 설정

완료 기준: 실제 외부 API 없이 생성·조회·오류 파이프라인과 부하테스트 smoke를 재현할 수 있다.

#### TST-3 테스트 데이터

- UUID, timestamp, 정수 범위와 고정 seed generator
- response 값을 run variable로 추출
- pipeline setup·teardown과 정리 실패 별도 표시
- 임의 shell 또는 Python 실행 대신 허용된 declarative operation 제공

완료 기준: 병렬 실행에서도 변수 범위가 run별로 격리되고 teardown 실패가 본 실행 결과와 구분된다.

#### OBS-1·OBS-2 대시보드

기능 테스트와 부하테스트는 화면 목적은 다르지만 공통 run metadata를 공유한다.

- 기능 테스트: 성공률, 실패 assertion, 환경, 실행자, 재실행
- 부하테스트: RPS, VU, p95·p99, 오류율, 자원과 기준 실행 비교
- 공통: run ID, project, environment, version, commit, actor, timestamps와 status

부하테스트 세부 구현은 [`API 부하테스트 계획`](api-load-test-plan.md)을 따른다.

완료 기준: 사용자가 프로젝트의 기능 실패와 성능 회귀를 각각 찾고 두 결과가 어느 환경과 app version에서 발생했는지 추적할 수 있다.

### 5단계 — 협업과 생태계

#### COL-1·COL-2 인증, 권한과 격리

- 로그인과 session/token 검증
- Owner, Admin, Editor, Runner, Viewer 권한
- workspace별 프로젝트, 문서, 실행, secret과 audit 격리
- `X-Studio-Actor`를 신뢰하지 않고 인증 주체에서 actor 결정
- 권한 변경과 secret 사용에 대한 감사 이벤트

완료 기준: 다른 workspace ID나 문서 reference를 조작해도 데이터와 실행 결과에 접근할 수 없고 권한별 허용·거부 테스트가 통과한다.

#### IOP-1 도구 연동

- cURL 양방향 변환
- Postman Collection과 Environment 가져오기
- HAR에서 요청 생성
- 가져오기 충돌 preview와 secret 후보 제거

완료 기준: 대표 fixture를 가져와 요청 의미를 보존하고 내보낸 cURL을 다시 실행했을 때 동일한 요청을 생성한다.

#### GOV-1·DOC-1 lifecycle과 문서

- API release, 변경 로그와 deprecated operation 표시
- OpenAPI 기반 검색 가능한 개발자 문서
- 환경별 server, 인증 방법, request·response 예시
- SDK artifact와 명세 revision 연결

완료 기준: 소비자가 특정 release의 명세, 변경 내용, 인증 방법과 SDK를 같은 revision 기준으로 확인한다.

## 6. 의존 관계

| 선행 작업 | 후속 작업 | 이유 |
| --- | --- | --- |
| FND-1 | API-1, OBS-1 | 기존 구현을 최신 기준으로 먼저 복구 |
| FND-2 | 모든 DB·UI 기능 | migration과 frontend 회귀 방지 필요 |
| API-2 | RUN-1, MOCK-1, 대시보드 | 모든 실행 결과에 환경 정보 필요 |
| API-3 | 빠른 호출, 케이스, Mock | 요청마다 다른 인증 구현 방지 |
| RUN-1 | RUN-2, OBS-1, OBS-2 | 대시보드와 job이 공유할 결과 계약 필요 |
| OAS-1 | OAS-2, TST-1, MOCK-1 | 안정된 명세 모델이 기준 |
| COL-1 | 외부 공개와 multi-workspace | actor header만으로는 보안 경계가 되지 않음 |

핵심 순서는 `FND → API → RUN → OAS/TST → MOCK/OBS → COL/IOP`로 유지한다. 독립적인 UI 작업을 병렬화하더라도 데이터 계약과 migration이 먼저 승인되어야 한다.

## 7. 공통 비기능 요구사항

### 보안

- secret 평문을 SQLite 일반 컬럼, JSON 투영, 로그와 report에 저장하지 않는다.
- 외부 URL 요청에는 SSRF 방어 정책과 redirect 재검증을 적용한다.
- 업로드, `$ref`, artifact와 case reference의 root 탈출을 거부한다.
- 임의 스크립트 실행 기능을 기본 제공하지 않는다.

### 성능과 안정성

- 목록 API는 pagination과 filter를 제공한다.
- 장기 실행은 bounded worker에서 처리한다.
- DB write는 transaction과 busy timeout을 사용하고 lock 오류를 측정한다.
- 대형 response와 report에는 크기 상한과 streaming 또는 truncation 정책을 둔다.

### 호환성

- 기존 JSON 케이스와 파이프라인은 수정 없이 실행된다.
- Windows와 macOS/Linux에서 `/` reference 규칙을 유지한다.
- CLI option 추가는 기존 기본 동작과 exit code를 깨지 않는다.
- migration 전 백업과 이전 버전 복구 절차를 문서화한다.

### 접근성 및 사용성

- 상태는 색상 외 텍스트와 아이콘으로 표현한다.
- 모든 form과 chart에 keyboard 접근과 대체 정보를 제공한다.
- 직접 URL 접근, 새로고침과 뒤로 가기 상태를 유지한다.
- 오류는 사용자가 수정할 수 있는 원인과 위치를 포함한다.

## 8. 검증 전략

| 영역 | 필수 검증 |
| --- | --- |
| runner·인증·환경 | 정상, 오류, timeout, secret 마스킹과 기존 JSON 호환 테스트 |
| 저장소·migration | 빈 DB, 이전 DB, rollback, 동시 write와 workspace 격리 |
| OpenAPI | import→edit→export round trip, invalid `$ref`, breaking change fixture |
| CLI·CI | exit code, JSON schema, JUnit parser와 artifact 생성 |
| React | router, form 변환, loading·empty·error·conflict와 responsive layout |
| job worker | queue limit, cancel, timeout, 프로세스·임시 파일 정리 |
| 통합 | 빠른 호출→케이스→파이프라인→CI→대시보드 end-to-end |
| 성능 | API 부하테스트 계획과 대시보드 품질 기준 |

공통 최종 명령은 다음을 포함한다.

```bash
python3 -m unittest discover -s tests -v
cd web
npm run test
npm run build
```

frontend test 도입 전 단계에서는 `npm run test`가 아직 없음을 진행 기록에 명시하고 수동 검증 결과를 남긴다.

## 9. 단계별 출시 판단

각 단계는 다음 조건을 모두 만족해야 다음 단계의 기준 기능으로 본다.

- 해당 작업의 완료 기준 충족
- 기존 Python 테스트와 추가 테스트 통과
- React 변경 시 frontend test와 production build 통과
- 데이터 형식, backend API, 사용자 문서와 migration 문서 갱신
- 진행 기록에 변경 파일, 검증 결과, 알려진 제한과 다음 작업 기록
- 통합 대상 브랜치 최신 변경 반영과 `git diff --check` 통과

부분 구현은 기능 flag 또는 명확한 beta 표기로 격리한다. UI에 선택 항목이 노출되지만 실행이 완성되지 않은 인증 방식처럼 오해를 만드는 상태는 출시하지 않는다.

## 10. 당장 착수할 작업

1. `dev`와 `develop` 중 통합 브랜치 이름 확정
2. FND-1용 새 기능 브랜치 생성 및 두 원격 기능 branch의 변경 목록 재검토
3. RUN-1 공통 실행 결과 schema 초안 작성
4. 빠른 호출 request model과 기존 case request model의 field mapping 정의
5. frontend test와 SQLite migration의 최소 기반 설계

첫 번째 구현 milestone은 다음 흐름을 완료한 상태다.

```text
환경 선택
  → 공통 인증을 적용한 빠른 호출
  → 케이스 저장
  → CLI/웹 실행
  → 구조화 결과와 실행 이력 확인
```

## 11. 진행 기록

모든 개발 진행은 [`API 개발 기능 진행 기록`](api-development-progress.md)에 기록한다.

- 작업 시작 전 해당 ID를 `진행`으로 변경한다.
- 변경 범위, 설계 결정, 실행한 검증과 실패 결과를 기록한다.
- 차단 시 원인, 영향과 시도한 해결책을 남긴다.
- 완료 기준을 충족한 경우에만 `완료`로 변경한다.
- 완료 보고 전에 현재 요약, 검증 기록과 변경 이력을 갱신한다.

진행 기록이 갱신되지 않은 작업은 완료되지 않은 것으로 간주한다.
