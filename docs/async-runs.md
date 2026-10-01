# RUN-2 비동기 실행

케이스·파이프라인 화면의 실행 버튼은 작업을 제출하고 상태를 조회한다. 실행 중에는 중복 제출을 막고 **실행 취소** 버튼을 제공한다. 프로젝트·케이스/파이프라인 참조별로 기록하며, 같은 탭에서 새로고침하면 sessionStorage에 보관한 Run ID로 조회를 재개한다. 페이지 이동·연결 해제는 서버 실행을 취소하지 않는다.

## HTTP 계약

| API | 동작 |
| --- | --- |
| `POST /api/runs` | 기존 `/api/run`과 동일한 실행 입력. 202와 Run ID를 즉시 반환 |
| `GET /api/runs/{runId}` | 상태·완료 결과·제한된 실행 출력 조회 |
| `POST /api/runs/{runId}/cancel` | 대기 작업 제거 또는 실행 취소 요청. 반복 호출 가능 |

상태: `queued → running → passed / failed / error / timeout`, 취소 시 `cancelling → cancelled`. 대기 중인 취소는 바로 `cancelled`가 된다. 완료된 작업의 취소는 원래 결과를 반환한다. 실행이 이미 완료되는 시점과 취소가 겹치면 완료 결과가 유지될 수 있다.

완료 결과는 RUN-1 `result`이고 최상위 `runId`와 같다. 취소·전체 timeout은 완결된 CLI 보고서가 없어 `result: null`, `exitCode: null`이다. `cancelled` 확정은 실행 프로세스 정리 후에만 공개한다. 입력 오류는 400, 1 MiB 초과 입력은 413, 한도 초과는 429, 미존재·다른 소유자·만료 ID는 404, 종료 중 제출은 503이다.

## 실행 접수 정책

worker 기본값 2를 유지한다. `/api/run`은 비동기 실행과 공유하는 실행 slot을 즉시 확보할 때만 시작하며 대기열에 들어가지 않는다. 모든 slot이 사용 중이면 HTTP 429를 반환하고 CLI나 job을 만들지 않는다. 바로 결과를 기다리는 호환 호출에 사용하며, 순차 실행하거나 caller가 동시 요청을 제한한다.

대기를 허용할 실행은 처음부터 `POST /api/runs`로 한 번 제출한다. HTTP 202는 **접수**이며 실행 성공이 아니다. 응답의 `runId`를 보관해 `GET /api/runs/{runId}`로 `passed/failed/error/timeout/cancelled`까지 조회한다. 취소는 해당 ID로 요청한다. 대기열이 포화되면 이 API도 429를 반환하며 거부된 요청에 Run ID는 없다.

429 응답은 기존 `error` 문자열을 유지하고 다음 필드를 추가한다. `admission.accepted: false`는 실행/접수가 시작되지 않았음을 뜻한다. `admission.guidance`는 다음 행동 안내다. `Retry-After`는 제공하지 않으며 종료 시각을 추정하지 않는다.

| `code` | 거부 조건 | 다음 행동 |
| --- | --- | --- |
| `RUN_WORKERS_BUSY` | 동기 `/api/run` 실행 slot 없음 | 진행 중 실행 완료 후 명시적으로 다시 실행하거나, 대기가 필요하면 `/api/runs`로 한 번 제출 |
| `RUN_CAPACITY_EXCEEDED` | 전체 미완료 async job 한도 | 기존 Run ID의 완료 확인 후 새 제출 |
| `RUN_USER_LIMIT_EXCEEDED` | 사용자 미완료 async job 한도 | 본인의 기존 Run ID 완료 확인 후 새 제출 |
| `RUN_PROJECT_LIMIT_EXCEEDED` | 프로젝트 미완료 async job 한도 | 해당 프로젝트 작업 완료 후 새 제출 |

둘 이상 한도를 초과하면 전체 → 사용자 → 프로젝트 순서로 사유를 반환한다. queue/user/project 한도는 async의 `queued/running/cancelling` 미완료 job을 센다. 동기 실행은 이 job 수에 포함되지 않지만 실제 실행 slot을 공유하므로 async worker가 기다릴 수 있다. 혼합 호출의 엄격한 FIFO나 starvation 방지는 보장하지 않는다.

서버와 기능 화면은 접수 실패 후 자동 재제출이나 동기→비동기 fallback을 수행하지 않는다. 클라이언트도 202 이후 같은 payload를 다시 제출하지 말고 반환된 ID를 조회한다. 응답이 유실되거나 network timeout이면 이미 접수/실행됐을 수 있으므로 재전송은 중복 실행을 만들 수 있다. 이 API에는 idempotency key 계약이 없으며 자동 재시도를 추가하지 않는다. 프로세스 재시작이나 보관 만료 후 404도 새 제출의 안전성을 보장하지 않는다.

## 설정

서버 시작 환경변수로 설정한다. Compose는 기존 `.env`를 읽는다.

| 변수 | 기본값 | 의미 |
| --- | --- | --- |
| `RUN_WORKERS` | 2 | 동시 실행 수 |
| `RUN_CAPACITY` | 20 | 전체 미완료 작업 수 상한 |
| `RUN_USER_LIMIT` | 10 | workspace·사용자별 미완료 작업 상한 |
| `RUN_PROJECT_LIMIT` | 10 | workspace·프로젝트별 미완료 작업 상한 |
| `RUN_TIMEOUT_SECONDS` | 300 | 프로세스 실행 제한 초, 최대 86400 |
| `RUN_RETENTION` | 600 | 완료 job 조회 유효 기간(초) |
| `RUN_MAX_COMPLETED` | 100 | 메모리에 유지할 완료 job 최대 수 |

대기와 실행 중 작업을 함께 계산한다. 프로젝트 미지정 작업은 공통 미지정 그룹으로 제한한다. 사용자·workspace는 현재 서버의 `LOCAL_CONTEXT`를 사용하며 body의 사용자 식별자는 신뢰하지 않는다. 실제 로그인·권한 연동은 COL 단계에 남아 있다.

## 수명주기와 보관

- FastAPI app별 고정 worker와 제한된 대기열을 사용한다. 브라우저 연결과 독립적으로 실행한다.
- **단일 API 프로세스에서만 사용한다.** 여러 Uvicorn worker·replica의 공유 queue가 아니다. 서버 재시작 후 미완료 작업 재개·job 조회는 지원하지 않는다. 영속 queue/분산 worker는 별도 저장·복구 계약이 필요하다.
- 정상 서버 종료는 대기·실행 작업에 취소를 알리고 worker 종료를 기다린다. POSIX는 별도 프로세스 그룹을 생성하고 그룹 전체를 종료한다. Windows는 새 프로세스 그룹과 `taskkill /T /F`를 사용한다. Windows 실제 실행 검증은 별도 필요하다.
- 각 작업의 보고서·출력·CLI 로그는 임시 디렉터리에 두고 종료 시 제거한다. 임시 artifact는 8 MiB를 넘으면 중단하고, 반환 출력과 JSON은 각각 최대 1 MiB이다. 크기 감시는 실행 중 주기적으로 검사하므로 순간적인 디스크 사용 초과는 가능하다.
- 완료 결과와 기존 CLI 마스킹 출력은 제한된 메모리 job에 보관한다. 요청 payload는 작업이 끝나면 참조를 해제한다. DB 이력에는 기존 metadata만 저장하고 결과 원문·출력을 추가하지 않는다. 실행 전 대기열에서 취소한 job은 실행 이력 DB에 기록하지 않는다.
- `POST /api/run` 동기 호환 API는 기존 응답·300초 timeout 계약을 유지하면서 동일한 동시 실행 상한을 사용한다. 이 API는 job ID 기반 취소·조회 대상이 아니다. 기능 화면은 `/api/runs`를 사용한다.

SDK 생성은 기존 동기 API를 유지한다. `JobManager.submit(task)`의 공통 수명주기는 준비되어 있으며, SDK ZIP artifact 처리와 비동기 API adapter는 후속 연동 대상이다.

## 검증

worker 상한, 사용자·프로젝트 한도, 대기 취소·반복 취소·다른 소유자 거부, TTL·최대 보관 수, API 제출·조회·429·입력 검증, 실제 자식 프로세스 종료와 임시 파일 정리, 프론트엔드 polling·새로고침 복원·취소·연결 재시도를 자동 검증한다.
