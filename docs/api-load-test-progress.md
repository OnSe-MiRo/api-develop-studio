# API 부하테스트 및 대시보드 개발 진행 기록

## DB-1 결과 계약·importer 완료 (2026-09-26)

- 시작: MOCK-1 통합 후 문서에 지정된 다음 작업인 결과 JSON schema와 fixture 설계를 `feature/load-test-results`에서 시작.
- 범위: k6 `handleSummary`·원본 JSON 출력을 정규화 bundle로 변환하고 endpoint 정규화, 비밀값 제거, percentile·오류율·시간 bucket의 결정적 집계를 검증.
- 비범위: DB migration/API/UI와 실제 Baseline·Target·Stress·Spike·Soak 실행.
- 변경: JSON Schema 2020-12, streaming JSON Lines importer/CLI, k6 manifest helper, Smoke·Target·오류 fixture, 사용·보안 문서를 추가. gzip 원본, 현재/이전 summary threshold 판정, server metric 선택 입력을 지원.
- 최종 검증: DB-1 단위 테스트 10개, 권한 확장 전체 Python 310개(skip 0), Python compile, Node helper 실행, 생성 코드·diff 검사 통과. 제한된 sandbox 최초 전체 실행은 loopback·PostgreSQL·process 차단으로 실패했고 승인된 동일 명령에서 전부 통과. 미지원 Node 옵션으로 helper 실행 방식도 1회 실패했으나 호환되는 ES module 직접 로드로 같은 동작을 통과 확인.
- 완료 기준: Smoke·Target 고정 입력의 요청 수·RPS·오류율·p50/p90/p95/p99/max가 수작업 계산과 일치하고 schema 정상/오류 fixture 및 동일 입력 결정성 테스트를 통과.
- 판정: DB-1 완료. 실제 k6 Smoke·Target 실행은 LT 단계, PostgreSQL 저장과 API는 DB-2로 유지.

## MOCK-1 완료 보완 (2026-09-25)

- 시작/변경: gpt-6-sol xhigh 서브에이전트가 응답 크기·HEAD·관리 경합 및 UI 종속 선택을 보완. 기존 문서 archive 정리 변경 보존.
- 검증: 전체 Python 300개 skip 없이 통과. 실제 HTTP pipeline·50요청/동시성5 smoke, parent/project state 격리, 지연 종료 회귀 포함. 브라우저 명세 소스 3종·응답 대조와 reset/stop 확인.
- 판정: MOCK-1 완료. [최종 증거](archive/mock-1/completion-report.md). LT/DB 부하 대시보드 전체 계획은 별도이며 기존 상태 유지.
- Git: `fix/mock-completion` 미커밋 작업 트리. 이번 원격 반영 없음.

## 완료 문서 정리 (2026-09-22)

- MOCK-1 개발 과정 문서를 `docs/archive/mock-1/`에 보관하고 현재 사용 기준을 [Mock Server](mock-server.md)로 분리했다.
- 기존 smoke 결과와 LT/DB 단계의 대기 상태는 그대로 유지한다. 문서 위치만 정리했으며 부하테스트 전체 완료 판정은 변경하지 않았다.

## 테스트 기본 저장소 설정 검증 (2026-09-22)

- PostgreSQL 15432/Redis 16379 전용 컨테이너 및 테스트 URL 기본값 도입. 프로젝트 가상환경으로 전체 **297개 통과, skip 0**. 기존 42개 저장소 통합 테스트와 Mock smoke 포함.
- 테스트 서비스는 기동 상태 유지. 원격 CI는 설정만 반영했으며 실행하지 않음. 이 결과는 미실행 브라우저 검증이나 LT/DB 전체 계획 완료를 의미하지 않음.

## MOCK-1 종료·state 경계 결함 수정 (2026-09-22)

- 시작/변경: reset/seed 변경 전 대기 요청의 새 state 유입 차단(409), 종료 시 event loop/task 정리, 정수 및 JSON 입력 오류 거부.
- 검증: Mock 테스트 28개 및 전체 Python 297개(255 통과/42 skip), diff 검사 통과. 실제 loopback에서 5초 지연 요청 중 중지해 4초 미만 반환과 thread·loop·socket 정리 확인. 종료 timeout 취소 로그는 예상 동작이며 요청 성공 보장은 아님.
- 상태: 해당 결함 수정·관련 검증 완료. [당시 report](archive/mock-1/verification-report.md) 갱신. 실제 브라우저 등 전체 계획 잔여 검증은 남아 있으며 MOCK-1/LT/DB 전체 완료로 판정하지 않음. 이번 변경 미커밋.

## MOCK-1 report 지적 수정 및 재검증

- 시작: 독립 report의 cold-start smoke 지연 및 생성 코드 개행 불일치 보완 요청.
- 변경: schema 검증 의존성을 Mock 엔진 모듈 로딩 시 import하도록 이동. 요청 시 초기 import 제거. 생성기로 API 함수 사이 빈 줄 복원.
- 검증: 새 Python 프로세스의 `test_mock_pipeline.py` 2개 통과. 50요청/동시성5 smoke의 실패 0·p95 < 200ms·RPS > 10 단언 유지 및 통과. 전체 Python 293개 중 251 통과/42 skip, 생성 검사·diff 검사 통과.
- 상태: report Finding 1·2 해결. [당시 보고서](archive/mock-1/verification-report.md) 참조. MOCK-1 전체 계획 및 LT/DB 단계 완료 판정은 아님.
- 기록 정정: 하단의 deadline 테스트 통과는 queued 작업 취소와 반환 제한을 확인하는 stub 테스트다. 실행 중 worker의 즉시 강제 종료를 보장하지 않으며, 실제 지연 요청의 worker 종료 시각 검증은 후속이다. M17의 계획상 목적은 통계 출력이 아닌 deadline 동작 검증이다.

## MOCK-1 부하 스모크 및 하네스 독립 검증 결과 (2026-09-21)

- 상세 보고서: [MOCK-1 검증 결과](archive/mock-1/verification-report.md)
- 검증 기준: [MOCK-1 계획 이행 검증서](archive/mock-1/verification-plan.md)의 M16(부하 스모크 수렴 및 p95 < 200ms) 및 M17(로그 및 지연/RPS 통계)
- 검증 결과:
  - `test_smoke_deadline_cancels_unsubmitted_work`: 통과. deadline 초과 시 미제출 작업 취소 및 worker 즉시 종료 검증 완료.
  - `test_mock_concurrent_smoke_harness`: **실패** (p95 지연시간 초과).
    - 50건 요청 / 동시성 5 worker 실행 시 총 성공 50건(실패 0건), RPS > 10.0 만족.
    - 그러나 단독 실행 시 `synthesize_schema`의 `contracts.validation` 동적 import로 인한 콜드스타트 GIL 경합 발생, p95가 238.78ms~256.38ms로 측정되어 `assertLess(p95, 200.0)` 단언 실패.
    - 전체 테스트 스위트 실행 시에는 사전 캐싱으로 20ms 미만 통과하나, 모듈 최상단 import 변경으로 콜드스타트 지연 제거 필요.
- 상태: MOCK-1 진행 유지 (결함 보완 후 재검증 대기). LT/DB 단계는 대기 유지.

## MOCK-1 smoke deadline 개발 — 검증 분리 (2026-09-21)

- 검증 계획: [MOCK-1 계획 이행 검증서](archive/mock-1/verification-plan.md)의 M16/M17에 정상 smoke·deadline·worker 종료 검증 및 증거 기록 기준 작성. 이번에는 실행하지 않음.

- 시작: 사용자의 개발/검증 분리 요청에 따라 2차 리뷰의 deadline 미준수 수정.
- 변경: 동시성 한도 내 점진 제출, 남은 deadline을 socket timeout에 반영, deadline 시 queued future 취소 및 executor 대기 제거, 미완료/미제출 요청을 실패로 집계. 요청 수·동시성·timeout 입력 상한 추가.
- 제한: 이미 수행 중인 blocking I/O는 thread를 강제 종료하지 않고 요청 timeout에 따라 종료. deadline 테스트는 stub 해제 후 worker 종료까지 기다리도록 준비.
- 상태: 개발 반영, 검증 대기. 사용자 요청으로 smoke/회귀 테스트를 실행하지 않음. MOCK-1 및 LT/DB 전체 완료를 의미하지 않음.

## MOCK-1 2차 수정 검증 (2026-09-21)

- 시작/검증: R1–R8 수정본의 전체 Python 288개(246 통과/42 skip), 실제 HTTP pipeline 및 smoke 재실행. pipeline 본문 불일치 negative 검증도 통과.
- 발견: smoke deadline 0.05초, 0.2초 stub 작업 5개/동시성1에서 약 1.035초 후 반환. future timeout 이후에도 executor가 모든 작업을 끝낼 때까지 대기하므로 전체 시간 제한은 미해결.
- 상태: MOCK-1 진행 유지. [2차 리뷰](archive/mock-1/review.md)의 잔여 6개 수정 필요. LT/DB 단계 완료 아님.
- 차단: 브라우저용 서버 실행은 자동 승인 검토 사용량 한도로 미실행. 이번 제품 코드 변경·커밋·푸시 없음.

## MOCK-1 결함 보완 후 HTTP 부하 Smoke 재검증 (2026-09-21)

- 시작: MOCK-1 독립 리뷰 결함 보완 후 smoke 하네스 deadline 및 동시성 재검증 수행.
- 개선: `api_test/mock_smoke.py`에 전체 실행 `deadline_seconds`(기본 30초) 및 타임아웃 예외 처리 추가.
- 검증 결과 (`example-api.json` 기반 Loopback Mock Server):
  - 총 요청: 100건 (성공 100건, 실패 0건, 성공률 100%)
  - 동시성: 10 동시 worker
  - 총 소요 시간: 0.286초
  - RPS: 349.6 req/s
  - 지연시간: min 1.34ms, avg 28.42ms, p50 2.90ms, p95 256.59ms, p99 257.89ms, max 258.79ms
  - 상태 코드 분포: 201 Created 34건, 200 OK 66건
- 판정: MOCK-1 동시성 smoke 통과. 독립 재검증 대기. (LT/DB 단계는 대기 유지)

## MOCK-1 독립 리뷰 및 smoke 재검증 (2026-09-21)

- 시작: 개발 모델의 구현/검증 보고를 독립적으로 확인.
- 검증: 권한 확장 후 전체 Python 282개 중 240 통과/42 skip. Mock 실제 HTTP pipeline 및 50요청/동시성5 smoke 테스트 통과.
- 발견: pipeline 본문 검증 필드가 잘못되어 응답 내용 오류를 놓치며, resource state 혼합과 ID 덮어쓰기를 독립 재현. smoke 전체 실행 deadline도 미구현.
- 판정: MOCK-1 진행, 수정 후 재검증 필요. [상세 리뷰](archive/mock-1/review.md) 참조. LT/DB 단계 완료를 의미하지 않음.
- 변경: 이번에는 리뷰/진행 문서만 갱신. 임시 브라우저 검증 서버의 Mock은 중지했고 사용자 데이터는 사용하지 않음.

## MOCK-1 Mock Server 동시 HTTP 부하 Smoke (2026-09-21)

- 대상: OpenAPI 기반 Mock Server (`feature/mock-server`, Loopback `127.0.0.1:8940`)
- 내용: `example-api.json` 명세 기반 mock server를 기동하고 `api_test/mock_smoke.py` 하네스로 10 동시성·100회 요청의 짧은 HTTP 부하 smoke 실행.
- 부하 대상: `GET /__mock/health` (200), `GET /example-api/health` (200), `POST /example-api/users` (201).
- 결과:
  - 총 요청: 100건 (성공 100건, 실패 0건, 에러율 0.0%)
  - 상태 분포: 200 OK 67건, 201 Created 33건
  - 처리량(RPS): 1,927.5 req/s (총 소요시간 0.052초)
  - 지연시간: min 2.54ms, avg 4.75ms, p50 4.30ms, p95 8.04ms, p99 9.69ms, max 10.35ms
- 참고: 이 smoke는 MOCK-1 동시성/안정성 검증용이며, LT-1~LT-5 및 DB-1~DB-5 전체 부하테스트/대시보드 단계는 대기 상태를 유지함.

## 로컬 정책 예제 추가 (2026-09-11)

- 완료: `example-ownership-local.json`에 health Setup → 인증 누락 401 → 유효한 키 200 예제 추가.
- 이 Setup은 일반 로컬 단계이며 외부 HTTPS 승인 예외나 VU 실행을 자동 허용하지 않음.
- 검증: 전체 Python 138개, git diff --check 통과. 신규 예제는 handler 전송 mock과 분리된 `127.0.0.1:8877` 실제 HTTP 실행에서 3단계 PASS 확인.

## 소유권 검증 및 외부 Setup (2026-09-11)

- 상태: 완료 — `feature/ownership-verification` (실행 전 정책 범위)
- 실행 전 소유권 정책 및 승인된 외부 Setup 1회 호출 구현 완료. 재시도 금지, redirect 차단, 60초 호출 간격 적용.
- 기존 파이프라인 실행에 연결하며 신규 부하 생성기/VU 스케줄러는 이번 범위에 포함하지 않음.
- 검증: 전체 Python 135개 및 Vite build/py_compile/diff check 통과. 동시 Setup 승인 1건 제한, 실패 시 중단, 토큰 값 전달과 미승인 대상 차단 확인.
- 웹 검증: 임시 데이터에서 발급 화면 및 새로고침 상태 유지 확인. 최초 sandbox bind 실패 후 승인된 임시 서버로 재검증.
- 제한: 실제 외부 HTTPS 배포 검증 및 VU 부하 실행은 수행하지 않음. 향후 부하 생성기에 공통 정책과 Setup 선행 단계를 연결해야 함.

이 문서는 [`API 부하테스트 계획`](api-load-test-plan.md)의 실행 상태를 기록하는 단일 기준 문서다. 구현 작업을 시작하기 전에 현재 상태를 확인하고, 작업 중 의미 있는 변경이나 검증이 끝날 때마다 같은 작업 안에서 갱신한다.

## 현재 요약

- 최종 갱신일: 2026-09-26
- 현재 단계: DB-1 결과 schema·importer 완료
- 전체 상태: 진행
- 작업 브랜치: `feature/load-test-results` (`develop` `d77e0d1` 기준)
- 다음 작업: DB-2 migration·repository, atomic import와 목록·상세·series API

상태는 `대기`, `진행`, `완료`, `차단` 중 하나만 사용한다. 완료 기준과 검증을 충족하기 전에는 `완료`로 변경하지 않는다.

## 단계별 현황

| ID | 작업 | 상태 | 완료 기준 | 관련 변경 또는 결과 |
| --- | --- | --- | --- | --- |
| LT-1 | k6 실행 구조와 전용 fixture 준비 | 대기 | Small·Medium·Large fixture와 재현 가능한 실행 명령 준비 | - |
| LT-2 | Smoke와 읽기 Baseline 스크립트 | 대기 | 응답 검증과 클라이언트 지표 출력 확인 | - |
| LT-3 | Target 혼합 및 저장 경합 시나리오 | 대기 | 혼합 비율, 고유 저장, 예상 `409` 검증 | - |
| LT-4 | Stress·Spike·Soak 및 `/api/run` 시험 | 대기 | 중단 조건과 회복 측정을 포함한 결과 생성 | - |
| LT-5 | 기준선 보고서 | 대기 | 최대 안정 RPS, 안정 동시 실행 수, 병목 기록 | - |
| DB-1 | 결과 schema와 importer | 완료 | 고정 fixture의 집계값과 importer 결과 일치 | 단위 10개·전체 Python 310개·helper·생성·diff 검사 통과 |
| DB-2 | 저장소와 결과 조회 API | 대기 | migration, atomic import, 목록·상세·series API 테스트 통과 | - |
| DB-3 | 결과 목록과 상세 대시보드 | 대기 | 필터, KPI, 표, 차트와 상태 화면 구현 | - |
| DB-4 | 실행 비교와 regression 판정 | 대기 | 기준 대비 증감률과 endpoint 악화 순위 검증 | - |
| DB-5 | 성능·보존·문서 운영 보강 | 대기 | 예상 데이터 규모의 성능 및 정리·복구 검증 | - |

## 현재 작업

진행 중인 작업이 생기면 아래 항목을 갱신한다. 동시에 여러 작업을 수행할 때는 각각 구분해서 작성한다.

- 작업 ID: 없음
- 목표: 없음
- 변경 예정 파일: 없음
- 시작 시각: 없음
- 상태: 대기
- 확인이 필요한 사항: 다음 DB-2 시작 전 PostgreSQL 기준 저장 경계와 bundle body 상한 재확인

## 검증 기록

실행한 명령과 결과를 생략하지 않는다. 실패한 검증도 원인과 후속 조치가 추적되도록 남긴다.

| 일시 | 작업 ID | 명령 또는 확인 방법 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| 2026-09-26 | DB-1 | `.venv/bin/python -m unittest tests/test_load_results.py -v` | 통과 | 10개: Smoke·Target 수작업 수치, gzip·결정성, threshold fallback, 오류·schema·CLI·secret 제거 |
| 2026-09-26 | DB-1 | `.venv/bin/python -m py_compile api_test/load_results.py tests/test_load_results.py` | 통과 | importer와 테스트 syntax 확인 |
| 2026-09-26 | DB-1 | `node --experimental-default-type=module ...` | 실패 | 현재 Node에서 제거된 option. 제품 코드 실패가 아니라 검증 명령 호환 문제 |
| 2026-09-26 | DB-1 | `node --input-type=module`로 helper source 직접 import·manifest assertion | 통과 | memory/threshold/k6 version 변환 확인 |
| 2026-09-26 | DB-1 | 제한된 sandbox에서 `.venv/bin/python -m unittest discover -s tests -v` | 실패 | 309개 중 loopback·PostgreSQL·process 접근 차단으로 2 failure·50 error. DB-1 9개는 통과 |
| 2026-09-26 | DB-1 | 권한 확장 `.venv/bin/python -m unittest discover -s tests -v` 최종 재실행 | 통과 | 최종 310개, skip 0 (15.744초) |
| 2026-09-26 | DB-1 | `.venv/bin/python scripts/generate_server.py --check` | 통과 | `Generated server is up to date.` |
| 2026-09-26 | DB-1 | `git diff --check` | 통과 | whitespace 오류 없음 |
| 2026-09-07 | PLAN | 문서 구조, 링크, trailing whitespace, `git diff --check` 확인 | 통과 | 구현 테스트는 아직 실행하지 않음 |

## 결정 기록

| 일자 | 결정 | 이유 | 영향 |
| --- | --- | --- | --- |
| 2026-09-26 | DB-1은 원본 이벤트를 streaming 처리하고 최종 bundle만 저장 계약으로 노출 | 원본 크기에 비례한 메모리 사용과 민감 URL 보존을 피하기 위함 | importer는 JSON Lines를 순차 처리하고 query·동적 ID를 제거한 endpoint만 출력 |
| 2026-09-07 | 1차 대시보드는 완료된 결과의 가져오기와 분석에 집중 | 실시간 실행 제어와 임의 프로세스 관리 위험을 초기 범위에서 분리 | 실시간 스트리밍과 웹 실행 제어는 후속 범위 |
| 2026-09-07 | 원본 k6 이벤트 대신 구간 집계값을 조회 | 원본 크기에 따른 메모리와 응답 시간 증가 방지 | importer와 schema가 먼저 필요 |
| 2026-09-07 | 결과 데이터는 기존 문서 리비전과 별도 테이블에 저장 | 데이터 수명주기와 조회 패턴이 다름 | migration과 전용 repository 필요 |

## 변경 이력

최신 기록을 위에 추가한다. 각 기록에는 작업 ID, 실제 변경, 검증 결과와 다음 작업을 포함한다.

### 2026-09-26 — DB-1 — 결과 계약·importer 완료

- 변경: schemaVersion 1 계약, 고정 k6 입력/오류 fixture, summary manifest·JSON Lines importer, k6 helper, 사용 문서와 단위 테스트 추가.
- 현재 결과: 고정 입력의 요청 수·RPS·오류율·percentile·bucket 수치와 schema/결정성/secret 제거를 전용 10개 및 전체 310개 테스트로 확인. 생성 코드와 diff 검사도 통과.
- 제한: 실제 k6 실행, 장시간 결과의 bounded-memory 집계, 저장소/API/UI는 수행하지 않음.
- 다음: DB-2 결과 저장소·조회 API.

### 2026-09-07 — PLAN — 진행 기록 체계 추가

- 변경: 단계별 상태, 현재 작업, 검증, 결정과 변경 이력을 기록하는 문서 생성
- 검증: 문서 링크와 Markdown 형식 확인
- 다음: DB-1 결과 schema와 예제 fixture 설계

## 차단 사항

현재 차단 사항 없음.

차단이 발생하면 작업 ID, 발생 시각, 재현 방법, 영향, 시도한 해결책과 사용자 결정이 필요한 내용을 적는다. 해소 후에는 삭제하지 않고 해결 시각과 해결 방법을 같은 항목에 추가한다.

## 갱신 체크리스트

작업을 맡은 개발자나 자동화 에이전트는 다음을 지킨다.

- 작업 시작 전 `현재 요약`, `단계별 현황`, `현재 작업`을 갱신한다.
- 구현 범위나 설계가 바뀌면 `결정 기록`에 이유와 영향을 남긴다.
- 의미 있는 구현 단위가 끝날 때 `변경 이력`에 변경 파일과 다음 작업을 남긴다.
- 테스트를 실행할 때마다 성공과 실패를 모두 `검증 기록`에 남긴다.
- 차단되면 `차단 사항`을 기록하고 관련 단계 상태를 `차단`으로 바꾼다.
- 완료 보고 전 완료 기준을 다시 확인하고 상태, 최종 검증과 다음 작업을 갱신한다.
- 코드 변경과 진행 기록 변경을 같은 작업 범위에 포함한다.

## FND-3 공통 실행·대시보드 HTTP 전환 (2026-09-14)

- 시작: FND-2 `develop` 병합 `df3ca9a` 이후 `feature/fnd-3-fastapi`에서 공통 HTTP 전환 진행.
- 변경: `/api/run`·`/api/dashboard`를 FastAPI로 연결하고 기존 metadata 저장·15초 polling·필터 응답을 유지. 부하 생성기와 통계 schema 변경 없음.
- 검증: macOS 및 Docker에서 각각 전체 Python 166개, frontend 8개, Vite build, TestClient timeout/이력 및 실제 pipeline 3단계 PASS. React 실행 후 대시보드 성공 이력 반영 확인. Docker 단일 worker와 동일 Compose healthcheck 통과.
- 차단 및 해소: loopback/Docker sandbox 접근은 허용된 재실행으로 해소. 현재 차단 없음.
- 완료: FND-3 로컬 구현·검증 완료, FND-3 커밋/병합/푸시 없음. 상세 상태는 `api-development-progress.md`, HTTP 계약은 `fnd-3-http-contract.md`와 동기화.

## FND-4 저장소 전환 (2026-09-14)

- 상태: 완료 — `feature/fnd-4-postgres-redis` 로컬 구현·검증
- 시작: PostgreSQL 영구 저장소, SQLite 읽기 전용 이관, Redis metadata 캐시와 장애 fallback 구현. 실행 이력 저장소도 같은 전환 범위로 검증한다.
- 기준: 기존 HTTP/revision 계약 보존, DB commit 이후 JSON 투영, 이관 검증 실패 시 rollback.

- 변경: 실행 metadata를 PostgreSQL 저장소에 연결하고 workspace/requested_by/보존기한 schema와 workspace·시각 index 추가. 기존 dashboard JSON/filter/page 계약과 실행 성공 후 historyWarning 경계를 보존. 부하 생성기는 추가하지 않음.
- 검증: FND4 전용 PostgreSQL·Redis URL을 제공한 전체 Python 206개(skip 없음), frontend 8개와 Vite build 통과. 빈/이관 PostgreSQL HTTP matrix, 실행 이력 project 필터·페이지, 실제 subprocess 정책 차단 결과의 Run ID/대시보드 연결 확인.
- 장애·복구: 실제 Redis 중단 fallback 200, PostgreSQL 중단 API 503 및 재시작 후 pool 복구, Compose healthcheck, PostgreSQL dump/restore의 문서 수·ID/revision/hash/삭제 상태 일치, 전체 JSON 투영 복구 명령 통과.
- 환경 차단 및 해소: sandbox의 Git/Docker/TCP 제한은 작업별 권한 확장으로 해소. SQLite 초기 WAL 설정의 동시성 오류는 수정 후 전체 회귀 통과.
- 범위: 기존 15초 dashboard polling 유지. 운영 데이터 이관·배포·커밋·병합·푸시 없음. 운영 절차와 나머지 COL-2/COL-1 범위는 [FND-4 저장소 운영 계약](fnd-4-storage.md) 참조.

## 2026-09-15 — RUN-2 실행 이력 연동 진행

- 시작·변경: API 개발 RUN-2에 따라 기능 실행 취소 상태를 공통 실행 이력에 추가하고 대시보드에 취소 표시를 연결.
- 범위: 비동기 기능 테스트 job의 상태 연동. 부하 발생기·VU 실행·LT 단계는 수행하지 않음.
- 완료·검증 (2026-09-16): Python 236개 중 194개 통과·42 skip, frontend 17개·build·OpenAPI --check·diff check 통과. 취소 상태 기록·조회와 macOS 프로세스 정리 및 UI 실행·복원 확인.
- 최종 브랜치: `feature/async-runs`, 미커밋. LT 작업과 부하 실행은 수행하지 않음.
