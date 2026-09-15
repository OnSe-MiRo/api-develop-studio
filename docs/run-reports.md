# RUN-1 실행 보고서

```sh
python3 run_api_tests.py pipelines/example-ownership-local.json --report-json reports/run.json --report-junit reports/junit.xml
python3 run_api_tests.py --case users/get/get.json --environment stage --report-json reports/run.json
```

기존 소유권 확인과 로컬 실행 정책은 동일하게 적용된다. 출력 경로의 부모 디렉터리는 자동 생성되고 같은 파일은 덮어쓴다.

## 공통 계약

[JSON Schema](run-result.schema.json)의 `schemaVersion: 1`을 사용한다. CLI 마지막 요약, JSON과 JUnit, `POST /api/run` 응답의 `result`는 같은 실행 판정을 사용한다. 웹 응답의 `runId`와 `result.runId`는 동일하다. 기존 `exitCode`와 `output`도 유지한다.

- `0`: 성공, `1`: 검증 실패 또는 요청 오류, `2`: 구성·소유권 오류.
- 전체 상태 우선순위: cancelled → timeout → error → failed → passed.
- target마다 project, caseId, 시작·종료 UTC 시각, HTTP status, 마지막 요청 소요 시간, 시도 횟수, assertion 인덱스별 판정을 제공한다. pipeline target은 파이프라인 경로와 step 이름으로 식별한다.
- JUnit은 검증 실패를 `failure`, 요청·설정 오류와 timeout을 `error`로 표현한다. 실패 assertion의 0부터 시작하는 인덱스를 제공한다.
- 원문 요청·응답, header, assertion의 expected/actual/path, exception 문자열은 보고서에 넣지 않는다. 오류 원인은 안전한 category로 제공한다. 기존 사람용 실행 로그의 출력 정책은 유지한다.
- 현재 actor는 `local-user`이며 로그인 사용자 연계는 COL 단계 범위다. `APP_VERSION`과 `APP_COMMIT`을 설정하면 빌드 식별자를 포함하며 미설정 시 null이다.
- CLI artifact reference는 출력 파일명이다. 웹은 임시 JSON을 읽은 후 제거하므로 artifact 목록은 비어 있다. 상세 결과는 이력 DB에 추가 저장하지 않는다.

## 경계

실행한 case/step만 결과에 들어가며 실패 후 실행하지 않은 step은 포함하지 않는다. `cancelled`는 공통 계약의 예약 상태다. 비동기 job, 취소, queue·worker 제한은 RUN-2에서 구현한다. 서버의 300초 프로세스 timeout은 기존 HTTP 오류 계약을 유지하며 완결된 CLI 보고서를 반환하지 않는다. CLI 인수 구문 오류는 argparse의 기존 오류 동작을 유지한다.
