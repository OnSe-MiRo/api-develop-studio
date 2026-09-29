# OBS-1 기능 테스트 실행 이력

`/dashboard`에서 Run ID를 누르면 영구 실행 상세를 연다. 프로젝트·기간은 집계와 목록에, 결과·Run ID/대상 검색은 목록에 적용된다. 검색은 최대 200자의 부분 일치이며 `%`, `_`, `!`도 문자 그대로 처리한다. 기존 20건 페이지네이션을 유지한다.

## 저장 계약

Studio DB migration 5는 `executions.detail_json`을 추가한다. 과거 행은 `NULL` 그대로 보존하며 상세 결과를 만들어내지 않는다. RUN-1 보고서 중 아래 metadata만 저장한다.

- 서버 context의 실행자, 요청 환경, 실행 시작 시 확인한 프로젝트별 기본/선택 환경
- `APP_VERSION`, `APP_COMMIT` (설정이 없으면 미수집)
- case 참조/ID, 프로젝트, setup/test/teardown, 상태, HTTP status, 소요 시간, 시도 횟수, 오류 분류
- assertion index(0 기반)와 통과 여부

본문·헤더·인증정보·출력·예외 문자열·assertion 기대값/실제값은 제외한다. 기존 coverage용 targets metadata는 DB에 유지하고 화면 목록에는 실행 대상만 노출한다. SQLite와 PostgreSQL 모두 workspace 조건을 적용한다. 현재 서버는 기존 `LOCAL_CONTEXT` 실행자를 사용하며 SSO 도입을 의미하지 않는다.

## API

| API | 동작 |
| --- | --- |
| `GET /api/dashboard?search=...` | Run ID·실행 대상 부분 검색. 기존 필터와 조합 |
| `GET /api/executions/{runId}` | 작업 큐 만료/서버 재시작 이후에도 보존된 상세와 재실행 대상 조회 |
| `POST /api/executions/{runId}/rerun` | 서버가 이력에서 대상을 선택하여 기존 비동기 큐에 제출, 새 Run ID와 202 반환 |

재실행 본문으로 환경·대상·실행자를 바꿀 수 없다. 요청 크기는 1 MiB까지다. 없는 이력은 404, 재실행 대상이 없거나 저장 파일이 삭제되었으면 409, 큐 한도는 기존 429를 따른다. 삭제 여부는 제출 시 검사하며 제출 후 변경은 기존 runner 오류 계약으로 처리한다.

## 재실행 의미와 경계

알려진 실패 케이스는 해당 케이스만, 파이프라인 내 실패는 setup/teardown·입력 연결을 보존하도록 해당 파이프라인 전체를 다시 실행한다. 보고서 없이 timeout/취소된 실행은 원래 저장 대상 전체가 표시된다. 저장 전 preview, 성공한 실행, 상세가 없는 과거 이력은 재실행하지 않는다.

현재 저장된 파일·인증 설정을 사용하며 과거 revision snapshot을 재현하는 기능은 아니다. 명시 선택한 환경은 유지하고 기본 환경 요청은 현재 프로젝트 기본 설정을 사용한다. 화면에 실행할 대상과 이 의미를 표시한다.

이력은 기존 웹 동기 실행 및 실제 worker에 진입한 비동기 실행의 저장 지점에 연결된다. CLI 단독 보고서 import, worker 시작 전 큐 취소/서버 강제 종료의 영구 job ledger, 보존 정책, 분산 worker, 과거 assertion 값 복원은 범위 밖이다. 저장 실패는 기존 `historyWarning`으로 알린다.

## 검증

`tests/test_functional_history.py`는 재개방, metadata 최소화, 기본 환경, literal 검색, workspace 격리, preview/과거/삭제 차단, 파이프라인 재실행, HTTP 상태와 큐 제출을 검증한다. PostgreSQL 검증은 `tests/test_postgres_storage.py`, 화면 검증은 `web/src/pages/dashboard/ExecutionDetail.test.jsx`에서 수행한다. 최종 결과는 `api-development-progress.md`에 기록한다.
