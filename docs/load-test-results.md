# 부하테스트 결과 계약과 importer

DB-1은 k6 실행 결과를 `schemaVersion: 1` bundle로 변환한다. DB-2는 이 bundle을 Studio DB에 저장하고 HTTP로 조회한다. DB-3·DB-4는 결과 대시보드·비교 화면을 제공하고 DB-5는 보존·복원·조회 운영 경계를 보강한다. 실제 장시간 LT 부하 실행은 별도 단계다.

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

단, k6가 먼저 기록한 `raw.json` 자체에는 전체 URL tag가 남을 수 있다. 실제 token·API key·개인정보를 URL이나 사용자 tag에 넣지 말고 결과 디렉터리 접근을 제한해야 한다. 원본 보존·삭제는 아래 DB-5의 별도 preview/apply 명령으로만 적용하며, importer의 정규화가 원본 파일을 삭제하거나 암호화하지는 않는다.

## 현재 제한

- 실제 k6 binary를 사용한 Smoke·Target 실행은 LT 단계 범위다. DB-1은 공식 형식의 고정 fixture로 수치 계약을 검증한다.
- 복합 JavaScript threshold 표현은 실측값 계산 대상이 아니다. helper의 판정도 없으면 안전하게 실패로 표시하고 warning을 남긴다.
- exact percentile을 위해 latency 숫자 표본은 메모리에 유지한다. DB-5의 bounded-memory 개선은 저장된 series 조회에 적용한다. importer의 정확한 percentile 표본 메모리는 유지하며 대규모 Soak 입력의 histogram/외부 집계는 별도 변경이 필요하다.
- 서버는 원본 k6 JSON Lines 대신 정규화 bundle만 받는다. 자동 정리는 제공하지 않으며 아래의 운영자 확인 명령을 사용한다.

## DB-2 저장·조회 API

bundle 생성 후 `POST /api/load-tests/runs`에 JSON body로 전송한다. 성공은 `201 {"id":"..."}`, 동일 run ID는 `409`, 잘못된 bundle은 `400`, 4 MiB 초과 body는 `413`이다. schema가 허용하는 미래 확장 필드는 저장하지 않으며 endpoint와 threshold 표기, 숫자 범위, timestamp를 다시 확인한 뒤 한 transaction에 저장한다. 원본 요청·응답, header, URL query, k6 로그는 DB에 저장하지 않는다.

`GET /api/load-tests/runs`는 `project`, `scenario`, `status`, `from`, `to` 필터와 `limit`(기본 20, 최대 100), 반환된 `nextCursor`로 페이지를 읽는다. cursor는 동일한 필터에서만 사용할 수 있다. 목록에는 series나 원본 파일이 없다. `GET /api/load-tests/runs/{id}`는 summary·threshold·endpoint 집계를, `GET /api/load-tests/runs/{id}/series`는 `from`, `to`, `maxPoints`(기본 500, 최대 1000)로 제한한 추이를 반환한다. 축소 시 `rps`·오류율·CPU·메모리는 그룹 평균, VU·프로세스 수는 최대값, `p95Ms`는 그룹 내 최대 p95 상한값이다. 축소된 p95는 전체 표본의 정확한 재계산 percentile이 아니다.

`GET /api/load-tests/compare?baseline={id}&candidate={id}`는 같은 schema version과 시나리오의 summary 요청 수·RPS·최대 VU·p50·p95·p99·오류율 및 endpoint별 p95·오류율의 절대값, 차이와 기준 대비 증감률을 반환한다. endpoint는 p95 악화순으로 정렬한다. 기준값이 0이거나 한 실행에만 있는 endpoint의 증감률은 `null`이다. 프로젝트·환경·최대 VU·실행 상태와 앱 버전·commit 차이는 `conditionWarnings`에 표시한다. 버전·commit 변경은 변경 비교의 참고 정보로 취급한다. schema version 또는 시나리오가 다르면 `400`이다. 모든 조회는 서버가 정한 workspace 멤버십 범위에서만 수행한다.

DB schema v4는 SQLite와 PostgreSQL에 동일하게 적용된다. SQLite snapshot을 PostgreSQL로 이관할 때 결과 4개 테이블도 복사·검증한다. 보존은 아래 preview/apply 명령으로 관리한다. 결과 전용 portable 백업 외에 전체 Studio DB의 문서·실행 이력·사용자 및 원본 파일은 기존 별도 백업 정책에 포함해야 한다.

## DB-3 결과 대시보드

웹 상단의 `부하테스트` 메뉴 또는 `/load-tests`에서 저장된 실행 목록을 연다. 프로젝트는 저장된 `run.project` 값을 그대로 입력하거나 제안 목록에서 고르고, 시나리오·상태·UTC 시작일/종료일을 설정해 `조회`를 누른다. 조회 조건과 다음 페이지 cursor가 URL에 남아 새로고침·공유·브라우저 뒤로 가기에도 같은 목록이 열린다. 목록의 실행 시각을 선택하면 `/load-tests/results?run={id}` 상세로 이동하며 `결과 목록` 버튼은 기존 조회 조건으로 돌아간다.

상세는 KPI, 실패 threshold, endpoint 집계, 실행 환경, importer 경고와 시간 추이를 표시한다. 차트 아래의 표에 같은 구간 수치를 제공한다. 추이 데이터만 실패해도 상세의 나머지 지표는 계속 볼 수 있다. 최대 240개 구간으로 축소될 때 p95는 원본 구간별 p95의 상한이며 전체 요청의 재계산 percentile이 아니다. 서버 CPU·메모리를 수집하지 않은 결과는 `—`로 표시한다.

목록 상단의 최근 같은 시나리오 p95·오류율 변화는 단순 차이다. 최대 VU와 앱 버전 차이는 경고하고 환경·데이터셋 동일성은 확인하지 않으므로 회귀 판정으로 사용하지 않는다. 실행 비교는 상세의 `이전 실행과 비교` 버튼에서 연다. 다음 비교 화면에서 실행 조건과 수치 악화 후보를 확인한다.

## DB-4 실행 비교

`/load-tests/compare?baseline={id}&candidate={id}`에 기준·비교 실행을 저장한다. 상세의 `이전 실행과 비교`는 candidate를 지정하고 기준을 자동 추천한다. 기준·비교 실행 ID 입력은 최근 실행 제안과 `이전 실행 더 보기`를 지원하며 오래된 실행 ID도 직접 입력할 수 있다. `비교 적용`, 새로고침과 브라우저 뒤로 가기에서 선택과 기존 목록 필터를 URL로 복원한다. API 오류는 재시도할 수 있고 시간 추이만 실패하면 요약 비교를 계속 표시한다.

상세 API의 `recommendedBaseline`은 같은 workspace·프로젝트·시나리오·schema version에서 현재 candidate보다 앞선 실행의 metadata 또는 `null`이다. 목록 페이지와 무관하게 `(startedAt, id)` 내림차순의 직전 실행을 선택한다. 시작 시각이 같을 때는 사전순으로 작은 ID를 앞선 실행으로 정의한다. 이는 결정적인 tie 처리이며 실제 인과·실행 종료 순서를 뜻하지 않는다. 추천 후보가 없으면 사용자가 기준 ID를 직접 선택한다. 이후 시각의 최신 실행을 과거 candidate의 기준으로 추천하지 않는다.

지표의 절대 차이는 `candidate − baseline`, 상대 증감률은 `delta / baseline × 100`이다. 오류율은 저장된 0~1 비율을 %로 표시하고 절대 차이에 100을 곱한 **%p**를 사용한다. 예: 25%→50%는 +25 %p, 상대 +100%다. 기준 0의 증감률은 `null`(계산 불가)이며 0에서 비영으로 바뀐 값의 개선·악화 판정도 불가다. 양쪽 0은 동일이다. 신규·제거 endpoint는 값이 있는 실행만 표시하고 차이·판정을 계산하지 않는다.

기본 수치 판정의 허용치는 0이다. latency·오류율 증가와 RPS 감소는 `악화 후보`, 반대 방향은 `개선`, 같은 값은 `동일`이다. 요청 수와 최대 VU는 실행 조건 변화다. endpoint는 p95 **절대 증가량** 내림차순으로 정렬하고 오류율 변화도 함께 표시한다. 이는 실행 데이터의 수치 비교이며 확정된 성능 회귀 판정은 아니다. 프로젝트·환경·최대 VU·상태 차이는 비교 조건 경고, 앱 버전·commit 변경은 참고 정보다. 시나리오·schema 불일치는 비교를 차단한다. 데이터셋은 현재 결과 형식에서 수집하지 않아 항상 확인 불가이며 환경의 미수집 값을 동일성으로 간주하지 않는다.

두 실행의 추이는 각각 최대 240구간을 요청하며 실행 시작 시각을 0초로 맞춘 공통 경과 시간·Y축으로 겹친다. 기준은 실선, 비교는 점선으로 구분하고 동등한 수치 표에 실행·경과 시간·원래 시각을 제공한다. 측정값이 없는 지점은 선을 이어 채우지 않으며 축소 p95는 구간 p95의 상한이다. 가로 스크롤 표는 키보드 초점과 초점 표시를 지원한다.

계획 8절의 임시 통과 기준과 두 실행의 사용자 Threshold를 같은 화면에 제공한다. 읽기 p95≤300ms·p99≤1초와 고유 문서 저장 p95≤1초는 **Target 부하와 해당 작업 종류에만 적용**한다. 비예상 오류율은 <1%이며 raw `errorRate`에는 예상 오류도 포함되므로 이 값으로 임시 오류 기준을 판정하지 않는다. 현재 bundle에는 Target/read/write/정상 입력/경합 정확성/회복/Soak 적용 정보가 없어서 임시 기준은 참고용·판정 불가로 표시한다. 실제 사용자 Threshold의 등록된 실측값·판정을 별도로 확인한다. 서비스 전체의 300ms SLO나 운영 성능·LT 완료를 주장하지 않는다.


## DB-5 조회 예산과 운영 명령

결과 GET API(목록·상세·series·비교)는 **실제 직렬화된 UTF-8 JSON 본문 1 MiB**를 넘으면 `413` 오류를 반환한다. 상세 summary·threshold·endpoint, 비교 endpoint를 조용히 잘라내지 않는다. 목록에서는 `limit`과 필터를 줄이고 series는 기간·`maxPoints`를 줄일 수 있다. 큰 상세·비교는 전체 결과를 아래 portable 백업에서 확인하거나 입력 결과를 의미 있게 나눈다. 기존 4 MiB import 계약을 유지하며 임의의 새 endpoint/threshold/series 개수 제한은 추가하지 않았다.

series는 `(run_id,bucket_at)` 순서의 SQL window/group 집계로 원본 point 전체를 애플리케이션에 가져오지 않는다. DB→Python 결과 row와 응답 point는 최대 `maxPoints`(최대 1,000)이다. 폭은 `ceil(sourcePoints/maxPoints)`이고 평균·최댓값·null 계약은 DB-2와 같다. p95는 그룹 내 구간 p95의 최대값이며 전체 latency percentile을 다시 계산하지 않는다. PostgreSQL의 일반 cursor가 원본 전체를 libpq에 buffer하는 경로도 제거했다. 상세·series·비교는 같은 읽기 snapshot에서 필요한 테이블을 조회하여 정리와 경합해도 일부 자식 행만 사라진 결과를 반환하지 않는다.

정리·백업 명령은 서버가 사용하는 DB 설정(`STUDIO_DATABASE_URL` 또는 secret file, 미설정 시 `--db` SQLite)과 명시한 `--workspace`/`--user`의 **활성 owner/admin** 멤버십을 확인한다. 복원은 명시한 trusted context로 새 격리 DB의 owner를 생성하고 archive workspace 일치를 확인한다. 기본 context는 local `default/local-user`다. editor·runner·viewer는 정리·백업을 실행할 수 없다. 운영 manifest/백업/새 SQLite 복원 파일은 0600, 파일 삭제 quarantine은 0700으로 만든다. 기존 출력 파일과 복원 DB를 덮어쓰지 않는다.

### 보존 기간 점검과 DB 정리

기본 보존 제안은 **종료 시각 `endedAt`이 현재 UTC−30일보다 이른 결과**다. 시작만 오래된 장시간 실행과 cutoff와 같은 종료 시각은 삭제 대상이 아니다. scheduler/자동 삭제는 제공하지 않는다. 운영 전에 백업을 만들고 preview JSON의 실행 ID·프로젝트·종료 시각과 테이블별 행 수를 확인한다.

```bash
python3 -m api_test.load_test_maintenance --db data/studio.db \
  retention-preview --days 30 --output /secure/retention.json

python3 -m api_test.load_test_maintenance --db data/studio.db \
  retention-apply --manifest /secure/retention.json \
  --confirm-sha256 PREVIEW_OUTPUT_SHA256
```

preview stdout에는 정확한 manifest와 SHA256이 나온다. apply는 같은 workspace·cutoff·실행 집합 및 4개 테이블 모든 대상 행의 hash를 transaction 안에서 다시 검사한다. 다른 DB에 잘못 적용하지 않도록 SQLite canonical 경로·파일 inode와 PostgreSQL 접속 서버/DB의 비밀값 없는 fingerprint도 바인딩한다. 새 오래된 실행·변경된 자식 값·다른 DB·멤버십 변경은 적용을 거부하므로 다시 preview해야 한다. child 3개 테이블→run 순서 삭제가 하나의 transaction에 참여하며 실패 시 모두 rollback한다. 비교 기준 추천은 조회 때 계산하므로 삭제된 실행 참조가 남지 않고, 이미 공유된 삭제 run ID의 상세/비교는 `404`다. DB 파일 compaction(`VACUUM`)은 이 명령에 포함하지 않는다.

### 원본 k6 결과와 로그 정리

원본 경로의 승인된 root는 배포 설정 `STUDIO_LOAD_TEST_ARTIFACT_ROOT`이며 기본은 `data/load-tests`다. manifest 안의 root를 신뢰해 새 경로를 선택하지 않는다. root와 조상·run 디렉터리의 심볼릭 링크, traversal, special file을 거부하고 no-follow directory descriptor로 접근한다. **이 원본 파일 정리는 POSIX에서만 제공하며 Windows에서는 안전한 no-follow 지원이 없어 명시적으로 거부한다.** DB 정리·portable 백업·복원에는 이 POSIX 제약이 없다.

```bash
STUDIO_LOAD_TEST_ARTIFACT_ROOT=/approved/data/load-tests \
python3 -m api_test.load_test_maintenance --db data/studio.db \
  artifacts-preview --days 30 --output /secure/artifacts.json

STUDIO_LOAD_TEST_ARTIFACT_ROOT=/approved/data/load-tests \
python3 -m api_test.load_test_maintenance --db data/studio.db \
  artifacts-apply --manifest /secure/artifacts.json \
  --confirm-sha256 PREVIEW_OUTPUT_SHA256
```

DB 보존 대상 run ID의 디렉터리와 모든 파일 경로·크기·SHA256·inode를 정확히 출력한다. 등록되지 않은 디렉터리, 이미 DB에서 삭제된 orphan artifact, 새로운 파일과 quarantine은 자동 탐색·삭제하지 않는다. **원본 writer를 멈추고 artifact preview/apply를 DB retention apply보다 먼저** 진행한다. DB 삭제 후에는 workspace/age를 확인할 run이 없으므로 이 도구로 원본을 정리할 수 없다.

apply는 DB 대상과 파일 inventory를 재검사한 뒤 run 디렉터리를 root 안의 비공개 `.studio-retention-*` quarantine으로 원자 이동하고, 이동한 inode·내용을 다시 확인한 뒤 제거한다. 이동 직전 교체된 파일/디렉터리는 unpreviewed 데이터로 삭제하지 않고 quarantine에 보존한다. **filesystem과 SQL 삭제는 하나의 transaction이 아니다.** 도중 실패하면 오류에 quarantine 경로·capture한 run·삭제된 파일 목록을 제공한다. 남은 quarantine은 운영자가 확인·복구하고, 새 preview로 나머지를 재시도한다. 성공한 artifact apply는 DB 수치를 삭제하지 않으며 DB 정리 manifest는 별도로 적용한다.

### 결과 백업과 격리 복원

이 백업은 **해당 workspace의 정규화 결과 4개 테이블을 완전한 v1 bundle JSON Lines로 복구하기 위한 결과 전용 백업**이다. summary와 모든 threshold/endpoint/원본 series를 유지한다. 새 API 응답 예산이나 차트 축소를 백업에 적용하지 않는다. 문서·테스트 실행 이력·사용자 identity·원본 k6 파일·로그는 포함하지 않으므로 전체 Studio 복구에는 SQLite/`pg_dump` 등 기존 DB 백업 및 artifact 별도 백업을 함께 준비한다.

```bash
python3 -m api_test.load_test_maintenance --db data/studio.db \
  backup --output /secure/load-results.jsonl

python3 -m api_test.load_test_maintenance \
  restore --archive /secure/load-results.jsonl \
  --destination /isolated/NEW-studio.db
```

백업은 consistent read snapshot에서 run을 순차 읽고 마지막 footer에 개수와 SHA256을 기록한다. PostgreSQL은 named server cursor를 사용한다. 관리 transaction에서만 `SET LOCAL transaction_timeout=0`, statement timeout 120초를 적용하며 정상 API의 제한은 유지한다. 실패·중단하여 footer가 없는 백업은 불완전 파일로 남아 복원에 사용할 수 없다. 별도 새 출력 이름으로 다시 만든다.

복원은 첫 validation pass에서 전체 checksum·schema·workspace를 확인한 후 새 DB를 생성한다. 두 번째 insertion pass는 한 transaction이며 같은 checksum을 다시 확인하므로 pass 사이 파일이 바뀌어도 rollback한다. SQLite destination은 새 파일만 허용하고 PostgreSQL `restore --postgres`는 설정한 URL의 **새 빈 전용 DB**에만 허용한다. public 외 다른 사용자 schema/table/view가 있어도 거부한다. 복원은 snapshot에 identity를 싣지 않으며, 명시한 trusted `--workspace`/`--user`로 새 격리 DB의 owner를 생성한다. archive workspace가 그 context와 다르면 거부한다. 기존 운영 DB 덮어쓰기·합치기는 제공하지 않는다. 테스트 복원 후 summary/endpoint/series를 확인하고 별도 운영 교체 절차를 적용한다.

### 실제 HTTP 조회 성능 재현

```bash
.venv/bin/python -m api_test.load_test_benchmark \
  --requests 60 --concurrency 8 --output /isolated/sqlite-http.json

.venv/bin/python -m api_test.load_test_benchmark --postgres \
  --requests 60 --concurrency 8 --output /isolated/postgres-http.json
```

SQLite는 임시 DB, PostgreSQL은 `FND4_TEST_DATABASE_URL`(미설정 시 테스트 전용 loopback 15432)로 생성한 무작위 `db5_benchmark_*` DB만 쓰고 마지막에 제거한다. 앱 운영 `STUDIO_DATABASE_URL`에서 테스트 연결을 추론하지 않는다. HTTP 서버도 임시 loopback socket을 쓴다. 모든 요청에서 summary·500 endpoint·목록 순서·2,500 source point·p95 상한·null 값을 고정 입력과 대조하고 실제 body 크기를 검증한다.

30일 동안 약 667건/일을 가정한 **20,000 metadata 행 + endpoint 500개/series 2,500개인 상세 1건**을 모델링한다. 20,000개 실행 모두의 상세·원본 파일을 채운 전체 저장 용량 모델, production 서버·원격 네트워크·실제 k6 LT-1~LT-5 실행은 이 측정에 포함하지 않는다. warm-up 후 목록·상세·series 각각 60건, 혼합 동시성 8의 p50/p95/max 및 body bytes를 JSON으로 출력한다. 목록 p95≤500ms, 상세 p95≤1,000ms를 통과해야 exit code 0이다. 환경마다 값을 다시 측정한다.


2026-09-29 로컬 macOS의 격리 HTTP 측정 결과는 다음과 같다. 각 backend에서 180건·동시성 8·오류 0이며 본문 최대 크기는 목록 9,044 byte, 상세 89,181 byte, series 38,149 byte다. 상세 조회 기준 1초와 목록 기준 500ms를 모두 만족했다. [원본 측정 JSON](load-test-db5-benchmark.json)에 p50/max 및 fixture 범위를 함께 보존했다.

| backend | 목록 p95 | 상세 p95 | series p95 | 기준 |
| --- | ---: | ---: | ---: | --- |
| SQLite | 10.524 ms | 53.287 ms | 65.110 ms | 통과 |
| PostgreSQL | 24.898 ms | 31.595 ms | 32.338 ms | 통과 |
