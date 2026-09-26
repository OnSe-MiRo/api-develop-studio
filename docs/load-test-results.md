# 부하테스트 결과 계약과 importer

DB-1은 k6 실행 결과를 저장·조회·비교 단계가 공통으로 사용할 `schemaVersion: 1` bundle로 변환한다. 현재 범위는 계약과 변환까지이며 DB 저장·HTTP API·웹 대시보드와 실제 장시간 부하 실행은 포함하지 않는다.

## 파일 구성

- `load-test-result.schema.json`: 정규화 bundle의 JSON Schema 2020-12 계약
- `../api_test/load_results.py`: k6 JSON Lines를 순차 읽어 집계하고 schema를 검증하는 importer
- `../load-tests/k6/studio-summary.js`: k6 `handleSummary`에서 실행 metadata와 threshold 판정을 기록하는 helper
- `../tests/fixtures/load-tests/`: 수작업 계산값이 고정된 Smoke·Target·오류 입력

k6는 종료 summary와 세부 시계열 JSON을 별도로 제공한다. Studio는 upstream summary 전체를 저장하지 않고, `handleSummary` helper가 만든 작은 manifest와 `--out json`의 `Metric`·`Point` 이벤트로 bundle을 만든다. 이 경계는 k6 summary 표현이 바뀌어도 Studio 계약과 집계값을 일정하게 유지한다. 입력 형식은 [k6 custom summary](https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/)와 [k6 JSON output](https://grafana.com/docs/k6/latest/results-output/real-time/json/)을 기준으로 한다.

## k6 스크립트 연결

테스트 스크립트에서 helper를 `handleSummary`로 내보낸다.

```javascript
import { studioHandleSummary } from "./k6/studio-summary.js";

export { studioHandleSummary as handleSummary };
```

실행마다 별도 디렉터리를 먼저 만들고 다음 metadata를 전달한다. `STUDIO_RUN_ID`, `STUDIO_PROJECT`, `STUDIO_SCENARIO`는 필수다.

```bash
STUDIO_RUN_ID=run_20260926_120000_ab12cd \
STUDIO_PROJECT=example-api.json \
STUDIO_SCENARIO=target-mixed \
STUDIO_APP_VERSION=1.0.1 \
STUDIO_COMMIT_SHA=abcdef1 \
STUDIO_OS=linux \
STUDIO_CPU='4 vCPU' \
STUDIO_MEMORY_MB=8192 \
STUDIO_EXECUTION_MODE=docker-compose \
STUDIO_K6_VERSION=2.0.0 \
STUDIO_SUMMARY_PATH=data/load-tests/run_20260926_120000_ab12cd/studio-summary.json \
k6 run \
  --out json=data/load-tests/run_20260926_120000_ab12cd/raw.json \
  load-tests/target-mixed.js
```

현재 DB-1에는 시나리오 스크립트와 fixture 생성기가 포함되지 않는다. 위의 `target-mixed.js`는 LT 단계에서 제공할 실행 파일 이름이며, 지금은 helper 연결 계약을 보여 주기 위한 예시다.

## bundle 생성

```bash
python3 -m api_test.load_results \
  --summary data/load-tests/run_20260926_120000_ab12cd/studio-summary.json \
  --raw data/load-tests/run_20260926_120000_ab12cd/raw.json \
  --output data/load-tests/run_20260926_120000_ab12cd/bundle.json \
  --bucket-seconds 5
```

`.gz`로 끝나는 k6 JSON 출력도 같은 방식으로 읽는다. importer는 전체 JSON event 객체를 메모리에 보관하지 않고 줄 단위로 읽으며, 최종 percentile 계산에 필요한 숫자 표본만 유지한다.

## 집계 규칙

- 시간은 timezone이 포함된 RFC3339로 입력하고 bundle에는 UTC로 기록한다.
- 요청 수는 `http_reqs`, 오류율은 `http_req_failed`, latency는 `http_req_duration`을 기준으로 하며 세 metric의 표본 수가 다르면 결과 생성을 거부한다.
- RPS는 manifest의 전체 시작·종료 시간으로 나눈다.
- p50·p90·p95·p99는 정렬 표본의 `(n - 1) × percentile` 위치를 선형 보간하고 소수점 여섯 자리까지 기록한다.
- series는 기본 5초 단위다. 마지막 구간은 실제 남은 시간으로 RPS를 계산하고 표본이 없는 latency는 `null`이다.
- endpoint는 `name` tag를 우선하고 없으면 `url` tag를 사용한다. origin과 query를 제거하고 숫자·UUID·긴 불투명 path segment를 `{id}`로 바꾼다.
- `studio_cpu_percent`, `studio_memory_mb`, `studio_child_processes` metric이 있으면 같은 bucket에 기록하고 없으면 `null`이다.
- 단순 비교형 k6 threshold(`p(95)<300`, `rate<0.01`, `count>=1` 등)는 원본으로 실측값을 계산한다. helper가 전달한 k6 판정이 있으면 그 판정을 최종 기준으로 사용하고 차이가 있으면 안전한 warning을 남긴다.

## 검증과 거부 조건

다음 입력은 저장 가능한 bundle을 만들지 않는다.

- 지원하지 않는 manifest/schema version, 필수 run metadata 누락, 종료가 시작보다 이른 실행
- `NaN`, 무한대, 음수 latency, 범위를 벗어난 비율·CPU, 정수가 아닌 요청/VU/process 수
- 선언 전 metric point, 실행 시간 밖의 point, 손상된 JSON Lines
- `http_reqs`·`http_req_duration`·`http_req_failed` 누락 또는 표본 수 불일치
- method/name/url tag가 없어 endpoint를 안전하게 정규화할 수 없는 HTTP metric
- schema 불일치, endpoint 합계와 전체 요청 수 불일치, threshold 요약 불일치

오류 메시지에는 원본 event, URL, tag 값이나 credential을 포함하지 않는다.

## 보안과 보존 경계

정규화 bundle은 허용된 실행 metadata, 수치, 정규화 endpoint만 새로 구성한다. header, body, cookie와 원본 tag 객체는 복사하지 않고 URL query와 origin을 제거한다. threshold의 tag filter 값도 `{filtered}`로 대체한다.

단, k6가 먼저 기록한 `raw.json` 자체에는 전체 URL tag가 남을 수 있다. 실제 token·API key·개인정보를 URL이나 사용자 tag에 넣지 말고 결과 디렉터리 접근을 제한해야 한다. 원본 보존·삭제 정책은 DB-5에서 구현하며, importer의 정규화가 원본 파일을 삭제하거나 암호화하지는 않는다.

## 현재 제한

- 실제 k6 binary를 사용한 Smoke·Target 실행은 LT 단계 범위다. DB-1은 공식 형식의 고정 fixture로 수치 계약을 검증한다.
- 복합 JavaScript threshold 표현은 실측값 계산 대상이 아니다. helper의 판정도 없으면 안전하게 실패로 표시하고 warning을 남긴다.
- exact percentile을 위해 latency 숫자 표본은 메모리에 유지한다. 대규모 Soak 결과의 bounded-memory histogram 또는 외부 집계는 DB-5에서 검토한다.
- bundle 저장소·중복 run 처리·조회·비교 API는 DB-2 이후 범위다.
