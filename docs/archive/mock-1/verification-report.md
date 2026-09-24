# MOCK-1 검증 결과

> 보관 문서: MOCK-1 개발 과정의 검증 증거와 결함 해소 기록이다. 현재 사용법과 상태는 [`../../mock-server.md`](../../mock-server.md) 및 [`../../api-development-progress.md`](../../api-development-progress.md)를 따른다.

## PostgreSQL·Redis 기본 설정 후 전체 회귀 (2026-09-22)

- 테스트 전용 기본 URL과 Docker 서비스를 구성하고 프로젝트 `.venv`에 누락된 PostgreSQL·Redis 의존성을 설치했다.
- `.venv/bin/python -m unittest discover -s tests -v`: **297개 실행·297개 통과·skip 0**, 15.845초. 이전 42개 PostgreSQL/Redis 관련 미실행 범위 해소. 로그: `/private/tmp/mock-default-storage-all.log`.
- 로컬 기본 테스트 설정 검증 결과이며 원격 CI 및 실제 브라우저 미실행 항목을 대체하지 않는다. 서비스는 테스트 전용 loopback 포트에서 기동 상태 유지.

## 추가 경계 결함 수정·검증 (2026-09-22)

- 완료 범위: 초기화/seed 변경 중 진행 요청의 state 오염, 서버 종료 시 이벤트 루프 미정리, 정수 입력 자동 변환 및 잘못된 CRUD 본문 처리 수정.
- State: 요청 시작 시 세대 번호를 기록하고 reset/seed/scenario 변경 후 도착한 이전 요청은 `409 STATE_CHANGED`로 거부한다. 대기 요청이 새 state를 채우지 않으며 연결 종료 요청도 mutation 없이 종료한다.
- 종료: Uvicorn graceful shutdown을 2초로 제한하고 thread의 finally에서 남은 task·async generator·executor를 정리한 뒤 loop를 닫는다. 종료 한도를 넘겨 살아 있는 thread는 성공처럼 보고하지 않는다. 기동 실패 시 studio가 없는 경로의 잘못된 RuntimeError 인자도 수정했다.
- 입력: port/seed/latency의 boolean·소수·문자열·무한값 자동 변환을 차단한다. 잘못된 host 타입과 관리 설정 JSON 객체가 아닌 입력, CRUD의 잘못된 JSON·배열/null 본문은 400으로 거부한다.
- 회귀 증거: `tests/test_mock_boundaries.py`에 4개 테스트 추가. reset과 seed 변경 동안 대기 중인 POST가 409이며 새 store가 비어 있는지 확인. invalid/disconnect body의 state 비변경 확인. 실제 loopback 5초 지연 요청 중 stop 후 4초 미만 반환, thread 종료·loop closed·포트 재사용 가능 확인.
- 실행: Mock 관련 28개 통과. 전체 Python **297개 실행, 255 통과·42 외부 PostgreSQL 의존 skip**, exit 0. `git diff --check` 통과.
- 로그의 Uvicorn graceful-timeout/CancelledError는 진행 중인 5초 요청을 2초 종료 한도에서 취소한 결과다. 해당 요청 성공을 보장하는 테스트가 아니며 task/loop/socket 정리 단언은 통과했다.
- 이번에는 frontend 코드를 추가 수정하지 않았다. 실제 브라우저·명세 소스 3종 및 계획의 나머지 미실행 경계는 별도 검증이 남는다. **이번 결함 수정·관련 검증은 완료, MOCK-1 전체 계획 완료 판정은 보류**한다.
- 브랜치 `feature/mock-server`, 이번 변경 미커밋. 원격 푸시·develop 병합 없음.

## Report 후속 수정·재검증 — 최신 상태

- 작업: 사용자 요청에 따라 report의 Finding 1·2를 코드에 반영하고 관련 검증을 실행했다.
- Finding 1 해결: `api_test/mock_engine.py`에서 `schema_errors`를 모듈 로딩 시점에 import한다. 처음 schema 응답을 만드는 요청에서 검증 의존성을 초기 로딩하지 않도록 변경했다. 테스트의 p95 임계값은 완화하지 않았다. 원 보고서의 상세 GIL 경합 설명까지 별도 profiling으로 입증한 것은 아니며, 요청 경로의 초기 import 제거 후 재현 테스트 통과를 확인했다.
- Finding 2 해결: `python3 scripts/generate_server.py`로 재생성해 `mock_api.py` 함수 사이 빈 줄을 복원했다. 파일 끝 불필요한 빈 줄은 기존 생성기 newline 정규화 정책에 맞춰 정리했다. 생성 검사와 diff 검사를 모두 통과했다.
- 검증 결과:
  - 별도 Python 프로세스 `python3 -m unittest discover -s tests -p 'test_mock_pipeline.py' -v`: **2개 통과**, 실제 HTTP pipeline·고의 본문 불일치 실패·50요청/동시성5 smoke 포함. p95 < 200ms 및 RPS > 10 단언 통과. 출력에 정확한 p95 값은 없으므로 임의 수치를 기록하지 않는다.
  - `python3 -m unittest discover -s tests -v`: **293개 실행, 251 통과, 외부 PostgreSQL 의존 42 skip**, exit 0.
  - `python3 scripts/generate_server.py --check`: **통과**, `Generated server is up to date.`
  - `git diff --check`: **통과**.
  - 이번에는 React를 추가 수정하지 않아 frontend/build를 반복하지 않았다. 아래 27개 frontend 테스트 및 build 결과는 원 검증자의 기록이다.
- 판정: **report에 명시된 코드 결함 2건 수정·재검증 완료. MOCK-1 전체 계획 검증 완료는 보류**.
- 근거 보정: 아래 최초 report의 M06/M11은 주로 코드 확인, M18/M19는 소스·JSDOM/로딩 로직 확인으로 실제 브라우저 검증 증거가 아니다. M09의 users/orders 분리는 중첩 parent·프로젝트 격리 전체를 입증하지 않는다. M14의 유휴 서버 종료는 지연 요청 중 종료·동시 reset/config의 정리를 입증하지 않는다. M17은 통계 확인 대신 `test_smoke_deadline_cancels_unsubmitted_work`의 stub deadline 검증으로 읽어야 하며 실제 지연 HTTP의 worker 종료 시각 증거는 추가 필요하다.
- 후속: [검증 계획](verification-plan.md)의 해당 잔여 절차를 실제 실행하고 증거를 기록한 뒤 전체 완료를 판단한다. 기존 코드 변경과 report 원문은 보존했다. 이번 수정은 `feature/mock-server` 작업 트리이며 커밋·푸시·병합은 수행하지 않았다.

아래 내용은 후속 수정 전의 원 검증 기록이다. 충돌하는 판정은 위 최신 상태를 따른다.

- 검증 시각 / 담당: 2026-09-21 23:36 KST / 독립 검증 에이전트
- 브랜치 / HEAD / 미커밋 변경 범위: `feature/mock-server` / `0a6151f` (`feat: add OpenAPI mock server`) / 12개 파일 수정(`api_test/mock_engine.py`, `api_test/mock_smoke.py`, `api_test/services/mock.py`, `api_test/services/studio.py`, `docs/api-development-progress.md`, `docs/api-load-test-progress.md`, `docs/mock-1-review.md`, `tests/test_mock_review_regressions.py`, `tests/test_mock_server.py`, `web/src/pages/apis/ApiList.jsx`, `web/src/pages/apis/MockServerPanel.jsx`, `web/src/pages/apis/MockServerPanel.test.jsx`), 1개 미추적(`docs/mock-1-verification-plan.md`)
- 환경 / DB / 임시 포트 / fixture: macOS (Darwin arm64) / Python 3.13.5, Node v24.18.0, npm 11.16.0 / SQLite 임시 DB / 127.0.0.1 (임시 포트 8880, 8910, 8920, 8930) / `example-api.json` 및 인라인 OAS 3.0.3 fixture
- 최종 판정: **진행** (핵심 기능 M01~M15, M17~M20 및 단위/통합 293개 통과. M16 부하 스모크 단독 실행 시 cold-start 지연으로 인한 p95 초과 결함 1건, `scripts/generate_server.py --check` 개행 불일치 1건으로 보완 필요)

---

## 1. 기능 검증 매트릭스 (M01 ~ M20)

| ID | 결과 | 실제 결과와 증거 | 결함·제한 |
| --- | --- | --- | --- |
| M01 | **통과** | `tests/test_mock_server.py:218` (`test_response_priority_and_named_examples`): Named examples -> single example -> schema example -> schema examples[0] -> schema default -> dynamic synthesis 순으로 우선순위 정상 적용 입증. | 없음 |
| M02 | **통과** | `tests/test_mock_server.py:253` (`test_deterministic_schema_synthesis`), `tests/test_mock_review_regressions.py:21`: 동일 seed(42, 123) 전달 시 PRNG를 통해 속성값 및 생성 순서가 100% 동일하게 재현됨을 확인. | 없음 |
| M03 | **통과** | `tests/test_mock_server.py:291` (`test_declarative_crud_state_machine_flow`), `tests/test_mock_pipeline.py:180`: POST 시 request body를 검증하고 스키마 default 속성(`status: active`)을 병합하여 201 응답 및 저장 확인. | 없음 |
| M04 | **통과** | `tests/test_mock_review_regressions.py:29` (`test_unsupported_schema_is_rejected...`), `line 289` (`test_r4_schema_constraints`): `minItems > 100`, regex `pattern` 스키마 시 `MockEngineError(UNSUPPORTED_SCHEMA)` 안전 거부, `minItems: 5`, `maximum: 0`, `maxLength: 2` 경계값 정상 준수 검증. | 없음 |
| M05 | **통과** | `tests/test_mock_review_regressions.py:196` (`test_r3_crud_status_override_and_error_simulation`): GET 503 재정의 시 503 반환 확인, POST 500 오류 시뮬레이션 시 상태 저장소(collection)가 변이되지 않고 0개 유지됨을 확인. | 없음 |
| M06 | **통과** | `api_test/mock_engine.py:596`: `await asyncio.sleep(latency_ms / 1000.0)` 비동기 지연 구현. FastAPI/Uvicorn 이벤트 루프 블로킹 없이 동시 요청 정상 처리 확인. | 없음 |
| M07 | **통과** | `tests/test_mock_review_regressions.py:330` (`test_r8_non_json_media_types`): `text/plain` 응답 시 JSON 직렬화 대신 raw string body(`b"OK healthy"`) 및 `Content-Type: text/plain; charset=utf-8` 헤더 전송 확인. | 없음 |
| M08 | **통과** | `tests/test_mock_server.py:291` (`test_declarative_crud_state_machine_flow`), `tests/test_mock_review_regressions.py:169` (`test_r2_id_counter_after_deletion`): POST(201) -> GET(200) -> PUT(200) -> DELETE(204) -> GET(404) 흐름 및 항목 삭제 후 새 항목 생성 시 단조 증가 ID 카운터로 기존 ID 덮어쓰기 방지 입증. | 없음 |
| M09 | **통과** | `tests/test_mock_review_regressions.py:85` (`test_r1_state_isolation_between_different_resources`): `/api/users`에서 생성된 ID 1 항목이 `/api/orders/1` 조회 시 404를 반환하여 리소스 간 상태 누수 없음 입증. | 없음 |
| M10 | **통과** | `tests/test_mock_review_regressions.py:21` (`test_unchanged_seed_and_scenario_preserve_state`): 동일 seed/scenario로 latency 및 overrides 갱신 시 기존 항목 유지, seed 변경 시 초기화, `POST .../mock/reset` 호출 시 완전 리셋 확인. | 없음 |
| M11 | **통과** | `api_test/mock_engine.py:408-410`: `MAX_ITEMS_PER_COLLECTION = 1000`, `MAX_TOTAL_ITEMS = 10000`, `MAX_STATE_BYTES = 10MB` 상한 및 초과 시 `413 STATE_LIMIT_EXCEEDED` 반환 구현 확인. | 없음 |
| M12 | **통과** | `tests/test_mock_server.py:349` (`test_loopback_policy_enforcement`): `127.0.0.1`, `::1`, `localhost` 허용. `0.0.0.0`, `192.168.1.100`, `*` 등 외부/와일드카드 바인딩 시 `studio.ApiError`로 차단 검증. | 없음 |
| M13 | **통과** | `tests/test_mock_review_regressions.py:376` (`test_r5_admin_api_validation`): seed="invalid", port=70000, port=0, defaultLatencyMs="invalid", overrides 타입 불일치 시 500 대신 400 반환, 재시작 실패 시 기존 서버 중지 방지 검증. | 없음 |
| M14 | **통과** | `tests/test_mock_server.py:363` (`test_real_mock_server_http_lifecycle`): `stop_server()` 호출 후 소켓 해제 대기 루프에서 2초 내 포트 사용 가능 상태(`is_port_available == True`) 반환 확인. | 없음 |
| M15 | **통과** | `tests/test_mock_pipeline.py:180` (`test_pipeline_crud_and_error_flow_against_mock`): 실제 mock server 대상 POST -> GET -> GET(404) 파이프라인 3단계 통과 및 본문 불일치 시 파이프라인 실패(음성 검증) exit code != 0 확인. | 없음 |
| M16 | **실패** | `tests/test_mock_pipeline.py:249` (`test_mock_concurrent_smoke_harness`): 단독 실행 시 p95 지연시간 `238.78ms`~`256.38ms` 기록되어 `assertLess(p95, 200.0)` 실패. | **결함 Finding 1 참조** (cold-start 시 `synthesize_schema`의 `contracts.validation` 동적 import로 인한 GIL 병목) |
| M17 | **통과** | `api_test/mock_smoke.py`, Live HTTP 시퀀스: `total_requests`, `rps`, `status_distribution`, `latency_ms`(p50, p95, p99, min, max, avg) 집계 및 서버 인스턴스 `requestCount` 추적 확인. | 없음 |
| M18 | **통과** | `web/src/pages/apis/MockServerPanel.test.jsx` (3개 테스트 통과), `web/src/pages/apis/ApiList.jsx:26-39`: `docs_bundle`, `docs_file`, `docs_url` 3개 명세 소스가 `/api/docs`를 통해 동일하게 `mockOperations`로 연동되어 Mock 패널에 표시됨 확인. | 없음 |
| M19 | **통과** | `web/src/pages/apis/MockServerPanel.jsx:69` (`loadStatus`): 컴포넌트 마운트 및 revision 변경 시 백엔드 `/api/projects/{reference}/mock`을 호출하여 running 상태, 포트, 시드, 지연시간, 오버라이드 상태 복원 확인. | 없음 |
| M20 | **통과** | `python3 -m unittest discover -s tests -v`: 전체 293개 테스트 중 251개 통과, 42개 skip (외부 PostgreSQL URL 환경 의존), 0 failure, 0 error로 기존 스튜디오 기능(케이스, 파이프라인, 소유권, 문서) 회귀 없음 확인. | 없음 |

---

## 2. 최근 6개 수정 집중 확인 (Section 6)

| 항목 | 확인 위치 | 검증 결과 |
| --- | --- | --- |
| 6.1. 같은 설정에서 state 삭제 방지 | `api_test/mock_engine.py:554` | `test_unchanged_seed_and_scenario_preserve_state` 통과. 동일 seed/scenario 시 `state_store` 유지, latency/overrides만 갱신. seed 변경 시에만 재생성. |
| 6.2. UI 명세 연결 불일치 해소 | `web/src/pages/apis/ApiList.jsx:21, 39`, `MockServerPanel.jsx` | `bundle ? { bundle } : document ? { document } : { url }`을 일관되게 `/api/docs`로 해결 후 `mockOperations`를 공유하여 Mock 패널에 전달. |
| 6.3. schema 위반 성공 응답 방지 | `api_test/mock_engine.py:61-70` | `synthesize_schema` 완료 후 `schema_errors`로 재검증하여 위반 시 `UNSUPPORTED_SCHEMA` 발생. `test_unsupported_schema_is_rejected...` 통과. |
| 6.4. override 검증/실행 타입 불일치 | `api_test/services/mock.py:126` (`validate_overrides`) | `latencyMs`, `status`, `mediaType`, `exampleKey`, `errorResponse` 엄격 타입 검사 통과. `test_override_types_are_rejected_before_execution` 통과. |
| 6.5. CRUD media/example 무시 방지 | `api_test/mock_engine.py:698`, `test_crud_explicit_example...` | 명시적 예제 지정 시 raw text/json 반환 및 state 비변경 유지 확인. `test_crud_explicit_example_uses_selected_media_without_mutation` 통과. |
| 6.6. smoke deadline 미준수 해소 | `api_test/mock_smoke.py:120-126` | deadline 초과 시 잔여 큐 작업 cancel 및 `executor.shutdown(wait=False, cancel_futures=True)`. `test_smoke_deadline_cancels_unsubmitted_work` 통과. |

---

## 3. 명령 실행 결과

| 명령 | exit code | 실행·통과·실패·skip | 로그 요약 |
| --- | :---: | :---: | --- |
| `python3 -m unittest discover -s tests -p 'test_mock*.py' -v` | 1 | 24 실행, 23 통과, 1 실패, 0 skip | `test_mock_pipeline.py:266` `AssertionError: 256.38 not less than 200.0` |
| `python3 -m unittest discover -s tests -v` | 0 | 293 실행, 251 통과, 0 실패, 42 skip | 외부 PostgreSQL URL 없는 환경 42개 skip, 전체 기존 회귀 0 fail |
| `python3 scripts/generate_server.py --check` | 1 | 차이 감지 | `Generated files differ: apis/mock_api.py` (개행 빈 줄 및 trailing newline 차이) |
| `git diff --check && git diff --cached --check` | 0 | 통과 | 공백 오류 및 conflict marker 0건 |
| `cd web && npm test` | 0 | 10개 파일, 27개 테스트 전체 통과 | MockServerPanel 3개 포함 Vitest 전체 통과 (소요 2.46s) |
| `cd web && npm run build` | 0 | 빌드 성공 | Vite production build 성공 (dist 생성, 소요 109ms) |
| 라이브 HTTP Mock 수명주기 스크립트 | 0 | 통과 | GET 200 -> POST start 200 -> Mock Health 200 -> POST config 200 -> POST reset 200 -> POST stop 200 -> 포트 해제 True |

---

## 4. 라이브 HTTP 검증 증거

- `GET /api/projects/example-api.json/mock`:
  `HTTP 200` `{"status": "stopped", "host": "127.0.0.1", "port": 8880, "url": "", "seed": 42, "scenario": "default", "defaultLatencyMs": 0, "activeOperations": 0, "requestCount": 0, "overrides": {}}`
- `POST /api/projects/example-api.json/mock/start` (`{"seed": 42, "defaultLatencyMs": 10}`):
  `HTTP 200` `{"status": "running", "host": "127.0.0.1", "port": 8880, "url": "http://127.0.0.1:8880", "seed": 42, "scenario": "default", "defaultLatencyMs": 10, "activeOperations": 4, "requestCount": 0, "overrides": {}}`
- `GET http://127.0.0.1:8880/__mock/health`:
  `HTTP 200` `{"status": "ok", "mock": true, "scenario": "default"}`
- `POST /api/projects/example-api.json/mock/config` (`{"defaultLatencyMs": 50}`):
  `HTTP 200` `{"status": "running", "host": "127.0.0.1", "port": 8880, "url": "http://127.0.0.1:8880", "seed": 42, "scenario": "default", "defaultLatencyMs": 50, "activeOperations": 4, "requestCount": 1, "overrides": {}}`
- `POST /api/projects/example-api.json/mock/reset`:
  `HTTP 200` `{"status": "reset", "message": "Mock server state reset"}`
- `POST /api/projects/example-api.json/mock/stop`:
  `HTTP 200` `{"status": "stopped", "message": "Mock server stopped"}`
- 소켓 릴리즈 검증: `is_port_available('127.0.0.1', 8880) == True`

---

## 5. 발견사항

### [Finding 1] `test_mock_concurrent_smoke_harness` 단독 실행 시 p95 레이턴시 경미 초과 (P2)
- **심각도**: P2 (테스트 격리 안정성 및 초기 부하 레이턴시)
- **파일:라인**: `api_test/mock_engine.py:63`, `tests/test_mock_pipeline.py:266`
- **재현**: `python3 -m unittest tests/test_mock_pipeline.py -v` 실행
- **기대값**: `smoke_result["latency_ms"]["p95"] < 200.0`
- **실제값**: `AssertionError: 256.38 not less than 200.0` (또는 `238.78 not less than 200.0`)
- **원인 분석**:
  - `synthesize_schema`의 depth == 0에서 `from api_test.contracts.validation import schema_errors`를 요청마다 동적 import하고 있음.
  - 테스트 단독 실행 시 `contracts.validation` 및 하위 `jsonschema` 모듈이 메모리에 로드되어 있지 않은 콜드 스타트 상태에서 5개 동시성 스레드가 `POST /items` 요청을 실행함.
  - 첫 1~2개 요청이 Python import lock 및 스키마 검증 컴파일을 거치며 ~140ms 지연되어, p95(상위 95 백분위수)가 200ms를 초과함.
  - 전체 스위트(`python3 -m unittest discover -s tests -v`) 실행 시에는 선행 테스트가 모듈을 이미 캐시하여 20ms 미만으로 통과하나, 단독 실행 시 재현됨.
- **수정 제안**: `api_test/mock_engine.py` 최상단에서 `schema_errors`를 선행 import하여 요청 시점의 import lock 경합 및 지연 제거.

### [Finding 2] `scripts/generate_server.py --check`에서 `apis/mock_api.py` 개행 불일치 (P3)
- **심각도**: P3 (빌드/코드 생성기 정합성 검사 불일치)
- **파일:라인**: `api_test/generated/apis/mock_api.py:29-30`
- **재현**: `python3 scripts/generate_server.py --check` 실행
- **기대값**: Exit code 0, `Generated server is up to date.`
- **실제값**: Exit code 1, `Generated files differ: apis/mock_api.py`
- **원인 분석**:
  - OpenAPI Generator(7.24.0)가 출력하는 템플릿 코드에는 라우터 핸들러 함수 종료부(`\n    )\n`) 뒤에 빈 줄(`\n\n@router.post`)이 생성되나, 현재 `api_test/generated/apis/mock_api.py`에는 빈 줄이 누락되어 있음 (`\n    )\n@router.post`).
  - `scripts/generate_server.py`의 DTO 정규화 규칙은 models에만 적용되므로 apis 파일의 개행 차이가 diff로 잡힘.
- **수정 제안**: `api_test/generated/apis/mock_api.py`의 함수 간 빈 줄 및 파일 끝 개행을 생성기 출력 형식에 맞추거나 `python3 scripts/generate_server.py`로 재생성 반영.

---

## 6. 정리 및 후속 작업

- **임시 서버·포트·데이터 정리 결과**:
  - 테스트 및 수명주기 검증에 사용된 모든 Mock 서버(포트 8880, 8910, 8920, 8930)가 정상 중지되었으며, `127.0.0.1`에 잔여 리스닝 소켓 없음 확인 완료.
  - 사용자 작업 디렉토리 내 임시 파일 및 DB 오염 없음.
- **미해결·미실행 항목과 다음 작업**:
  1. `api_test/mock_engine.py`의 `schema_errors` top-level import 변경으로 cold-start p95 지연 해소.
  2. `api_test/generated/apis/mock_api.py` 개행 정합성 조정으로 `generate_server.py --check` exit code 0 달성.
  3. 두 결함 보완 후 최종 재검증하여 `완료` 판정 전환.
- **커밋·병합·원격 반영 여부**:
  - 프로젝트 규칙에 따라 독립 검증자는 코드를 임의 수정하지 않았으며, 커밋/병합/푸시는 일체 수행하지 않음.
