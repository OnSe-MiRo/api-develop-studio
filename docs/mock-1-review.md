# MOCK-1 독립 리뷰 및 검증 (2026-09-21)

## 2차 수정 검증 — 최신 판정

**수정 일부 확인, 완료 보류.** 아래는 R1–R8 보완 코드에 대한 독립 재검증 결과다. 최초 리뷰 내용은 이 아래에 이력으로 유지한다. 이번에도 제품 코드는 변경하지 않았다.

| 항목 | 재검증 결과 |
| --- | --- |
| R1 state 격리 | 기존 `/api/users` → `/api/orders/1` 누출 재현 해소. 전체 collection 경로와 마지막 item parameter 사용 확인 |
| R2 ID 충돌 | 삭제 후 새 ID 3 생성, 기존 ID 2 데이터 보존 확인 |
| R3 응답 정책 | 오류 status 503 적용 및 오류 시 state 비변경 테스트 통과. CRUD example/media 정책은 잔여 문제 |
| R4 schema | 기존 minItems 5·maximum 0·maxLength 2는 수정. 다른 유효 schema와 필수 순환 참조는 여전히 위반 |
| R5 입력 검증 | 기존 잘못된 seed/port/latency·port 0 테스트 통과. override 문자열 latency 검증/실행 불일치 잔존 |
| R6 pipeline | `expected.body` 및 exact_body 모드로 수정됨. 잘못된 본문에서 실패하는 negative test와 실제 HTTP pipeline 통과 |
| R7 화면 | 설정 UI는 추가됐지만 실제 프로젝트의 명세 데이터 경로와 불일치하여 operation 목록이 비게 됨 |
| R8 media | 일반 text/plain 회귀 테스트 통과. 저장된 CRUD 항목 GET/PUT/PATCH는 application/json 강제 유지 |

### 남은 발견사항

1. **P1 · 설정 적용이 기존 state를 지움** — `api_test/mock_engine.py:549–550`, `web/src/pages/apis/MockServerPanel.jsx:195`. UI는 지연/override만 바꿔도 seed와 scenario를 매번 전송하고 엔진은 값이 동일해도 state store를 교체한다. 항목 생성 후 `update_config(seed=42, scenario='default', default_latency_ms=1)`만 호출했는데 같은 항목 GET이 200에서 404로 바뀌는 것을 재현했다. 실제 seed/scenario 변경일 때만 명시된 정책에 따라 초기화하고, 지연/응답 설정 변경 시 기존 state를 보존해야 한다.
2. **P2 · operation 선택 UI가 실제 저장 형식에 연결되지 않음** — `web/src/pages/apis/MockServerPanel.jsx:41`. 패널은 `project.document.paths`를 읽지만 부모 ApiList는 `docs_file.document`, `docs_bundle`, `docs_url`를 해석한다. 부모의 해석된 operations도 패널에 전달되지 않는다. 새 UI 테스트는 실제 저장 계약에 없는 `project.document` fixture를 사용하여 문제를 놓친다. 기존 명세 해석 경로를 재사용하고 세 소스 형식에 대한 화면 통합 검증이 필요하다. 이 항목은 소스/테스트 계약 추적으로 확인했으며 이번 실제 브라우저 재검증은 미수행이다.
3. **P2 · schema 위반 응답 잔존** — `api_test/mock_engine.py:81–89,133` 및 integer/string 분기. 독립 jsonschema 검증에서 `minItems:101`은 100개만 생성, integer `minimum:1.5`는 실수 1.5 생성, `pattern:^[0-9]+$`는 `mock_string` 생성으로 실패했다. required child 순환 참조도 `{child:{child:{}}}`로 잘라 required 위반이다. 제한을 넘거나 생성할 수 없으면 명시적으로 거부해야 하며, 단지 non-null인지 검사하는 현재 순환 회귀 테스트로는 적합성이 입증되지 않는다.
4. **P2 · 승인된 override가 요청 처리 중 TypeError 발생** — `api_test/services/mock.py:105–112`, `api_test/mock_engine.py:598–599`. `latencyMs:"10"`을 int로 검사하지만 원래 문자열을 반환한다. 해당 검증 결과를 엔진에 전달하면 `'>' not supported between instances of 'str' and 'int'` 발생. 입력 타입을 엄격하게 거부하거나 정규화된 값을 반환해야 한다. mediaType/exampleKey/errorResponse 타입 검증도 필요하다.
5. **P2 · CRUD 응답은 선택한 example/media type 무시** — `api_test/mock_engine.py:663–677`. text/plain named example을 지정한 저장 항목 GET이 `application/json`과 저장 객체를 반환하는 것을 ASGI 호출로 재현했다. 일반 응답에만 적용된 R8 수정을 CRUD 경로에도 일관되게 적용해야 한다.
6. **P2 · smoke 전체 deadline이 작업을 중단하지 않음** — `api_test/mock_smoke.py:70–88`. future 대기만 timeout 처리하고 executor context 종료는 모든 queued/running 작업을 기다린다. 0.2초 작업 5개, 동시성1, deadline 0.05초의 제한된 stub 재현에서 약 1.035초 후 반환하고 5개 작업이 모두 실행됐다. 기한 후 queued 작업 취소, 새 요청 제출 중단, 진행 중 요청의 남은 시간 제한 및 종료 대기를 함께 설계해야 한다.

### 실행 결과 및 범위

- Python 전체: 288개 실행, **246 통과·42 외부 PostgreSQL 관련 skip**. 실제 HTTP pipeline/본문 불일치 negative case 및 smoke 포함.
- frontend: 10개 파일 **27개 통과**, production build 통과.
- OpenAPI 생성 최신성 검사 및 `git diff --check` 통과.
- 기존 독립 재현과 추가 ASGI/schema validator/smoke stub 재현 실행. 결과는 위 개별 항목에 기록했다.
- 새 브라우저 검증용 임시 서버 실행은 자동 승인 검토 사용량 한도로 실행되지 않았다. 안전성 거절은 아니며 브라우저 재검증 완료로 보고하지 않는다. 우회 실행하지 않았고 이번 임시 서버는 생성되지 않았다.
- 판정: MOCK-1 진행 유지. 잔여 6개 발견사항 수정 및 실제 브라우저·종료/동시성 경계 재검증 필요. 커밋·병합·푸시 없음.

판정: **수정 필요, MOCK-1 완료 보류**. `feature/mock-server`의 develop `f033c44` 대비 변경 및 untracked 구현 파일을 검토했다. 이번 리뷰에서는 구현 코드를 수정하지 않았다. 아래 내용을 개발 모델에 전달해 보완 후 재검증한다.

## 발견사항

### R1 · P1 · 서로 다른 리소스의 state가 혼합됨

- 위치: `api_test/mock_engine.py:435–446`.
- collection key가 전체 경로가 아닌 첫 segment이고, item ID도 마지막 parameter가 아닌 첫 parameter다.
- 재현: `/api/users`, `/api/users/{id}`, `/api/orders`, `/api/orders/{id}`를 가진 명세에서 `POST /api/users {"name":"user"}` → `GET /api/orders/1`이 사용자 데이터를 200으로 반환한다. 엔진 ASGI 호출로 확인.
- 수정 기준: 컬렉션 전체 경로와 상위 parameter 값을 포함한 명시적 state 매핑을 사용하고, resource/parent scope를 격리한다. 중첩 경로와 공통 `/api` prefix 회귀 테스트가 필요하다.

### R2 · P1 · 삭제 후 자동 생성 ID가 기존 항목을 덮어씀

- 위치: `api_test/mock_engine.py:286–289`.
- 재현: 항목 1·2 생성 → 1 삭제 → 새 항목 생성 시 `len(col)+1`이 2가 되어 기존 2를 덮어쓴다. 엔진 호출로 기존 `second` 데이터가 `third`로 바뀌는 것을 확인.
- 수정 기준: reset 가능한 단조 증가 counter 또는 충돌 없는 결정적 ID를 사용하고 명시적 중복 ID의 처리도 정의한다. 동시 생성과 삭제 후 생성에서 데이터 보존을 검증한다.

### R3 · P2 · CRUD 경로가 선택한 status와 명세 응답을 무시함

- 위치: `api_test/mock_engine.py:451–480`.
- 재현: 저장된 항목 GET에 `overrides={"/api/users/{id}":{"status":503}}`를 지정해도 200과 저장 데이터가 반환된다. POST도 example/schema 대신 요청 body를 그대로 저장·반환하므로 명세 기반 기본값/응답 필드를 보장하지 않는다.
- 수정 기준: 상태 변경 여부와 선택 응답의 처리 순서를 정의하고 CRUD/일반 경로에 같은 status·example 정책을 적용한다. 오류 응답 선택 시 state가 의도치 않게 변경되지 않는지도 검증한다.

### R4 · P2 · Schema 제약을 위반한 응답을 성공으로 생성함

- 위치: `api_test/mock_engine.py:90–113` 및 composition/순환 참조 처리.
- 재현: `minItems:5`인 배열이 3개만 생성되고, `maximum:0`인 정수는 1, `maxLength:2`인 문자열은 `mock_string`을 반환한다. `synthesize_schema` 직접 호출로 확인.
- 수정 기준: 지원 제약을 만족하는 값을 생성하고 지원하지 못하는 조합은 명시적으로 거부한다. 순환/깊이 초과를 무조건 null로 바꾸어 non-null schema를 위반하지 않도록 한다. 독립 schema validator로 생성 결과를 검증한다.

### R5 · P2 · 관리 API 입력 검증 및 포트 계약이 불완전함

- 위치: `api_test/services/mock.py:255–271`, `update_config`, `MockServerInstance.base_url`.
- 실제 HTTP 재현: start `{"seed":"invalid"}` 및 `{"port":70000}` → 500; config `{"defaultLatencyMs":"invalid"}` → 500. start `{"port":0}` → 200/running이지만 `http://127.0.0.1:0` 반환.
- generated request model이 존재해도 현재 route는 raw body를 서비스에 전달하므로 서비스 검증이 필요하다.
- 수정 기준: 정수/boolean/null, 유한 범위, scenario 및 override 구조를 mutation 전에 검사해 일관된 400을 반환한다. port 0은 거부하거나 실제 할당 포트를 반환한다. IPv6 주소는 URL bracket을 적용한다. 잘못된 재시작 요청이 기존 서버를 중지하지 않도록 한다.

### R6 · P2 · 파이프라인 테스트가 응답 본문을 검증하지 않음

- 위치: `tests/test_mock_pipeline.py:161–167`; 비교 구현 `api_test/runner.py:558–568`.
- `expected.exact_body` 객체는 runner의 본문 검증 계약이 아니다. `response_validation_modes({"status":200,"exact_body":{...}})`가 `(False, False)`를 반환하는 것을 확인했다.
- 현재 fixture가 기대하는 `status:"active"`는 POST 요청 body에도 없고 state 생성 과정에서 합성되지 않아도 테스트가 통과한다.
- 수정 기준: `expected.body`와 필요한 `validation_modes`를 사용한다. 의도적으로 잘못된 본문에서 테스트가 실패함을 확인하고 생성→추출→조회→오류의 내용까지 검증한다. fixture 저장 경로도 `case/{tag}/{api_name}/{case_file}.json` 규칙을 따른다.

### R7 · P2 · 화면에서 operation별 status/example/media type을 선택할 수 없음

- 위치: `web/src/pages/apis/MockServerPanel.jsx`의 startServer/applyConfig 및 입력 UI.
- 실제 브라우저에서 port·seed·전역 scenario·전역 latency만 제공됨을 확인했다. API의 overrides는 표시/편집되지 않고 `applyConfig`에도 전달되지 않는다.
- 수정 기준: operation별 status·example·media type·latency·오류 설정을 화면에서 선택하고 서버 상태 재조회/새로고침으로 복원한다. 조회 실패 시 이전 running 상태를 확정 상태처럼 표시하지 않도록 한다. 단일 프로세스, state 소멸, 명세 snapshot 정책을 사용 설명에 추가한다.

### R8 · P2 · 비 JSON 응답도 JSON으로 전송함

- 위치: `api_test/mock_engine.py:177–181`, `:516–523`.
- 코드 확인: `text/plain` 등의 media type을 골라도 resolver가 media type을 반환하지 않고 최종 `_send_json`이 JSON 직렬화와 `application/json`을 강제한다. 명세의 문자열 example이 따옴표가 포함된 JSON 문자열이 된다.
- 수정 기준: 선택 media type을 실제 Content-Type과 직렬화에 반영하거나 지원하지 않는 타입을 명시적으로 거부한다. JSON/text fixture의 HTTP header와 raw body를 검증한다.

## 추가 보완이 필요한 경계

- 본문/전체 state/응답 byte 상한이 없다. 항목 개수 1000 제한만으로 메모리 사용량을 제한하지 못한다.
- stop은 3초 join 이후 loop를 강제 중단한다. 최대 5초 latency 요청 및 동시 config/reset/stop의 취소·자원 정리를 별도 검증해야 한다. config가 관리 thread에서 event loop 소유 state를 직접 교체하는 구조도 정리한다.
- 시작 실패/timeout을 성공 응답과 구분하고 실제 thread 생존 여부를 상태에 반영해야 한다.
- smoke의 `timeout_seconds`는 요청별 timeout으로만 쓰이며 전체 실행 deadline이 아니다. 총 요청 수·동시성·전체 시간 제한과 오류 응답 검증을 추가한다.
- 위 항목은 코드에서 확인한 미충족 경계이며, 장애/고부하 재현까지 완료한 결과로 간주하지 않는다.

## 이번 검증 결과

- 전체 Python: `python3 -m unittest discover -s tests -v` — 282개 실행, 240 통과, 외부 PostgreSQL 관련 42 skip. 최초 sandbox의 bind/ps 제한으로 실패한 뒤 권한 확장 재실행 통과. 관련 실제 HTTP 파이프라인 및 50요청/동시성5 smoke도 포함하지만 R6 때문에 본문 정확성은 입증하지 못한다.
- frontend: `web/`에서 `npm test` — 10개 파일, 26개 테스트 통과. `npm run build` 통과.
- 생성 코드: `python3 scripts/generate_server.py --check` 통과.
- 브라우저: 임시 DB/fixture, loopback Studio 8957 및 Mock 8880에서 화면 접근→시작→새로고침 복원→오류 scenario 적용→실제 HTTP 500→reset→중지 확인. 콘솔 error 없음. 이는 제공된 화면의 검증이며 R7 누락 기능까지 충족한 것은 아니다.
- 독립 재현: R1–R4/R6 엔진·runner 호출, R5 실제 관리 HTTP. R7 브라우저+소스, R8 소스 추적으로 확인.
- 사용자 프로젝트/DB를 브라우저 검증에 사용하지 않았다. 임시 Mock 서버는 중지했다.

## 개발 모델 후속 작업 지시

원래 `docs/mock-1-development-prompt.md`와 이 리뷰의 R1–R8 및 경계 항목을 반영하라. 먼저 각 재현을 실패하는 회귀 테스트로 만들고 수정하라. 기존 사용자 변경을 보존하고 범위 밖 리팩터링은 하지 않는다. 구현 후 전체 테스트·생성 검사·build·실제 HTTP/브라우저·제한된 smoke를 다시 수행해 두 진행 문서를 동기화한다. 미수행 검증과 미해결 문제를 남김없이 보고하고, 독립 재검증 전에는 MOCK-1 전체 완료로 표시하지 않는다. 커밋·병합·푸시는 하지 않는다.
