# 전용 fixture와 격리 k6 실행 하네스

LT-1은 재현 가능한 데이터와 격리 실행·결과 수집 구조를 준비하고, LT-2는 1분 Smoke와 5분 읽기 Baseline을 제공한다. `harness-probe`는 1 VU·단일 iteration의 연결 검증이다. LT-3은 Target 혼합·고유 저장·동일 문서 경합을 제공한다. Stress·Spike·Soak와 실행 용량·회복·기준선 보고서는 LT-4~LT-5에서 수행한다.

## 준비

저장소 루트에서 Python 의존성을 설치한 환경과 [k6 binary](https://grafana.com/docs/k6/latest/set-up/install-k6/)를 사용한다. 애플리케이션에 새 런타임 의존성은 추가하지 않는다. 아래 `python`은 Windows의 Python 또는 macOS/Linux의 `.venv/bin/python`으로 바꿀 수 있다. `--k6`에는 PATH의 `k6` 또는 이미 설치된 binary의 절대 경로를 지정한다.

출력 디렉터리는 **아직 존재하지 않는 새 경로**여야 하며 fixture 내부 경로는 허용하지 않는다. 내부에 스냅샷을 생성해 자신을 재귀적으로 복사하는 경로도 시작 전에 거부한다. 기존 fixture·결과를 덮어쓰거나 삭제하지 않는다. 생성 중 실패한 디렉터리는 증거로 남으며, 재시도에는 다른 경로를 사용한다.

## 데이터 생성과 검증

```bash
python -m api_test.load_test_harness generate --dataset small --root data/lt-fixtures/small-01
python -m api_test.load_test_harness generate --dataset medium --root data/lt-fixtures/medium-01
python -m api_test.load_test_harness generate --dataset large --root data/lt-fixtures/large-01
python -m api_test.load_test_harness verify --root data/lt-fixtures/large-01
```

| 데이터셋 | 프로젝트 | 케이스 | 파이프라인 | 기본 case revision |
| --- | ---: | ---: | ---: | ---: |
| Small | 1 | 10 | 2 | 1 |
| Medium | 20 | 2,000 | 100 | 1 |
| Large | 100 | 20,000 | 0 | 1 |

계획에는 Large의 파이프라인 건수가 지정되지 않아 0개로 둔다. 모든 케이스의 JSON `request.body`는 키 순서 정렬·공백 없는 UTF-8 직렬화 기준으로 **1,024 / 10,240 / 102,400 byte**를 번갈아 사용한다. 케이스 전체 파일 크기나 HTTP 응답 크기를 뜻하지 않는다. 데이터에는 실제 API 키·개인정보를 넣지 않는다. 전용 경로는 `case/load-test/health/project-000-case-0000.json`처럼 `case/{tag}/{api_name}/{case_file}.json` 구조를 따른다.

`--seed` 기본값은 `20260929`다. 같은 dataset·seed·revision depth는 같은 내용과 reference 선택 순서, `fixtureSha256`을 만든다. 문서 ID·revision 시각도 고정해 실행마다 내용이 달라지지 않는다. SQLite 파일 자체의 byte hash는 fixture 식별자로 사용하지 않는다.

모든 케이스에 1~100개의 실제 불변 리비전을 저장하려면 깊이를 지정한다. 예를 들어 다음 명령은 Small의 케이스 10개에 각각 100개씩 저장한다.

```bash
python -m api_test.load_test_harness generate --dataset small --case-revisions 100 --root data/lt-fixtures/small-depth100-01
```

Large×100은 케이스 리비전 **2,000,000개**를 생성한다. 리비전 본문만 약 76 GB, 현재 JSON 투영은 약 0.76 GB이며 SQLite 페이지·인덱스·audit와 실행 스냅샷 복사 공간이 추가된다. 기본 Large의 생성·검증은 revision 1개로 수행하고 100개 깊이는 Small로 검증했다. 전체 Large×100의 디스크·실행 시간·성능을 검증한 것으로 해석하지 않는다.

생성 결과에는 다음 파일과 디렉터리가 있다.

- `data/studio.db`: 현재 schema의 격리 SQLite, 문서·불변 리비전·audit
- `projects/`, `case/`, `pipelines/`: 최신 JSON 투영본
- `logs/`: 전용 로그 경로
- `fixture.json`: 건수·본문 크기·seed·reference 선택 순서·내용 fingerprint
- `verification.json`: 실제 DB·투영·리비전 크기와 무결성 결과

전용 fixture 생성기는 현재 migration을 실행한 뒤 단일 transaction으로 대량 seed를 저장한다. 검증은 SQLite integrity/foreign key, 정확한 문서·리비전·JSON 파일 건수, 모든 리비전 내용 hash, 최신 DB와 JSON 투영의 일치, 본문 byte 수와 manifest reference를 확인한다. 실제 `CollaborationStore` 조회·낙관적 revision 저장 호환성은 단위 테스트에서도 확인한다. 사용 중인 서버의 DB에는 이 seed 경로를 적용하지 않는다.

## 격리 k6 probe

```bash
python -m api_test.load_test_harness probe --fixture data/lt-fixtures/small-01 --output data/load-tests/lt1-probe-01 --k6 k6
```

실행기는 검증된 fixture를 결과 디렉터리의 `fixture/`로 복사한 후 그 복사본만 사용한다. 원본은 재사용 가능한 스냅샷으로 남는다. 서버는 임의의 **127.0.0.1 loopback 포트**에서 시작하며 외부/운영 대상 URL 입력은 제공하지 않는다. 프로젝트·케이스·파이프라인·DB·로그 경로를 격리하고 상속된 PostgreSQL/Redis 설정·proxy·credential·Python path를 전달하지 않는다. k6 anonymous usage reporting을 끄고 config 경로도 실행 디렉터리 안에 둔다.

probe는 health, 프로젝트 목록, 해당 프로젝트의 케이스·파이프라인 목록, 프로젝트·케이스 단건, case revision을 총 **7번** 조회한다. 상태 코드와 본문을 함께 검사하며 `checks rate==1`, `http_req_failed rate==0`, `http_reqs count>=7` threshold를 적용한다. 실제 VU gauge 표본을 기록하도록 1.1초를 기다린다. 원본 HTTP metric의 `name`은 동적 reference가 없는 endpoint 이름이고 URL tag를 수집하지 않는다. 서버와 k6의 대기에는 timeout을 적용하고 성공·실패 모두에서 서버를 종료한다.

`execution.json`에는 fixture 검증·fingerprint, Python/k6/OS·CPU 개수·수집 가능한 메모리와 디스크 용량, app version·commit·working tree dirty 상태와 실행 source hash, 실행 명령, 안전한 UUID run ID, k6 종료 코드, 결과 status와 종료 확인을 기록한다. 미커밋 코드 실행은 HEAD만으로 재현할 수 없으므로 source hash와 변경 트리를 함께 보존한다. k6 종료 후 importer와 schema 검증을 수행하고 스냅샷 정합성을 재검사한 뒤 bundle을 기록한다. importer 또는 정합성이 실패하면 CLI exit 2와 `status:error`를 기록한다. threshold 실패는 CLI exit 1이다. 연결·k6 실패 로그와 부분 결과는 삭제하지 않는다.

| 실행 산출물 | 내용 |
| --- | --- |
| `server.log`, `k6.log` | 격리 서버와 부하 발생기 로그 |
| `server-ready.json` | 임시 loopback 주소 |
| `raw.jsonl` | 실제 k6 Metric/Point 원본 |
| `studio-summary.json` | DB-1 summary manifest |
| `bundle.json` | importer·schema를 통과한 정규화 결과 |
| `execution.json` | 실행 환경·명령·종료 코드·정합성 |
| `fixture/` | 테스트 시작 전 격리 스냅샷 |

k6는 summary 컨텍스트에서 모듈을 다시 초기화할 수 있다. 실행기는 process 시작 직전 UTC 시각을 `STUDIO_STARTED_AT`로 전달하고 `studio-summary.js`가 이를 우선 사용한다. helper를 다른 실행 스크립트에 연결할 때도 이 값을 실행 전에 지정해야 한다. 모듈 내부의 `new Date()`만 시작 시각으로 사용하면 raw sample보다 늦어져 importer가 거부할 수 있다.

생성된 bundle은 [결과 가져오기 API](load-test-results.md#db-2-저장조회-api)로 등록할 수 있다. 하네스는 운영 Studio에 자동 전송하지 않는다.

## LT-2 Smoke와 읽기 Baseline

```bash
python -m api_test.load_test_harness smoke --fixture data/lt-fixtures/medium-01 --output data/load-tests/smoke-01 --k6 k6
python -m api_test.load_test_harness baseline --fixture data/lt-fixtures/medium-01 --output data/load-tests/baseline-01 --k6 k6
```

| 명령 | 부하 | 기본 시간 | 읽기 흐름 |
| --- | --- | ---: | --- |
| `smoke` | endpoint별 1 VU, 합계 7 VU | 60초 | 7개 endpoint를 독립 시나리오로 반복 |
| `baseline` | 합계 5 VU | 300초 | health→프로젝트 목록→케이스 목록→파이프라인 목록→프로젝트 단건→케이스 단건→리비전 순으로 반복 |

모든 요청 이후 seed·VU·iteration·endpoint에서 결정되는 **1~3초 think time**을 적용한다. 프로젝트는 순환하며 케이스는 LT-1의 seeded reference 순서를 사용하고, Baseline VU별 offset을 나누어 특정 문서에만 요청이 몰리지 않도록 한다. 한 번의 읽기 흐름에서는 같은 프로젝트·케이스를 유지한다. 실행 시간 안에 fixture 전체 케이스를 모두 조회했다는 의미는 아니다.

상태 코드 `200`과 JSON 의미를 각각 검사한다. 목록은 예상 reference의 정확한 집합, 프로젝트는 이름·revision, 케이스는 project·revision·method·URL·seed·본문 byte 수, 리비전은 전체 건수·최신부터 연속된 번호를 확인한다. Large의 파이프라인 0개도 정확한 빈 목록으로 확인한다. 응답이 JSON이 아니거나 HTTP 200의 본문이 잘못되어도 check가 실패한다.

`checks rate==1`, `http_req_failed rate==0`을 적용하며 시작 5초 이후 실패 threshold가 감지되면 중단한다. endpoint별 `studio_read_*_requests count>=1`도 확인한다. coverage counter는 setup에서 0으로 선언하여 짧게 중단된 실행의 누락도 실패로 판정할 수 있다. Target의 p95/p99 기준을 Smoke·Baseline 통과 조건으로 적용하지 않는다. 요청 timeout은 5초, graceful stop은 10초, k6 process timeout은 **설정 duration+10초+15초**다. 부하 종료 직전에 시작한 iteration 때문에 실제 전체 실행 interval은 기본 duration보다 길어질 수 있다. importer RPS는 setup·graceful stop을 포함한 manifest의 전체 시간으로 계산한다.

원본에는 method·status·name·scenario·expected_response만 system tag로 남기고 URL tag는 제외한다. metric endpoint 이름에는 reference나 query를 넣지 않는다. k6의 `abortOnFail`/`delayAbortEval` threshold object는 importer가 expression만 정규화해 기존 판정·수치 계약을 유지한다. 잘못된 threshold expression 입력은 원문을 출력하지 않고 거부한다.

`execution.json.workload`에 mode·duration·configured VU·graceful stop·validation 여부·`whole-dataset` 범위를 남긴다. 읽기 부하는 전체 fixture에 걸치므로 bundle의 `run.project`는 실제 첫 프로젝트 대신 **`load-test/{dataset}.json`**이라는 데이터셋 구분자를 사용한다. 예: `load-test/medium.json`. 이는 저장된 프로젝트 문서 reference가 아니며 결과 목록에서 dataset 전체 실행을 구분하는 값이다. fixture fingerprint는 `execution.json`에 보존하며 기존 dashboard bundle이 fixture 동일성을 자동 판정하는 계약은 확장하지 않는다.

개발 검증에는 기본보다 짧은 시간만 지정할 수 있다. VU 변경과 기본보다 긴 실행 옵션은 제공하지 않는다.

```bash
python -m api_test.load_test_harness smoke --fixture data/lt-fixtures/small-01 --output data/load-tests/smoke-validation-01 --validation-seconds 5
python -m api_test.load_test_harness baseline --fixture data/lt-fixtures/small-01 --output data/load-tests/baseline-validation-01 --validation-seconds 25
```

`--validation-seconds`는 Smoke 2~59초, Baseline 2~299초의 정수만 허용한다. 짧은 실행은 `validationMode:true`, `smoke-read-validation` 또는 `baseline-read-validation`로 기록해 기본 성능 실행과 비교하지 않는다. 매우 짧은 Baseline은 7개 endpoint 흐름을 끝내기 전에 종료되어 coverage threshold가 실패할 수 있으므로 연결 검증에는 25초를 권장한다. threshold 실패는 정상적으로 보존되는 failed bundle·CLI exit 1이고, 실행 timeout·importer·스냅샷 정합성 실패는 error record·CLI exit 2다. 양쪽 모두 서버를 종료하고 원본 fixture를 보존한다. 최종 성공 여부는 `execution.json.status`와 `postRunIntegrity`로 확인한다. 스냅샷 정합성 검증까지 통과한 뒤에만 `bundle.json`을 생성하며, 무결성 실패에는 정상처럼 보이는 bundle을 남기지 않는다. HTTP threshold 실패 bundle은 정합성을 통과한 경우 `failed` 상태로 보존한다.

기본 시간의 단일 실행은 스크립트와 계측 경로 검증이다. Baseline 3회 반복·중앙값과 Small/Medium/Large의 성능 비교, 확정 SLO·용량 보고서는 후속 LT-5의 검증 범위다.

## LT-3 혼합 부하와 저장 경합

```bash
python -m api_test.load_test_harness target --fixture data/lt-fixtures/medium-01 --output data/load-tests/target-01
python -m api_test.load_test_harness unique --fixture data/lt-fixtures/medium-01 --output data/load-tests/unique-50 --concurrency 50
python -m api_test.load_test_harness contention --fixture data/lt-fixtures/medium-01 --output data/load-tests/contention-5 --concurrency 5
python -m api_test.load_test_harness contention --fixture data/lt-fixtures/medium-01 --output data/load-tests/contention-20 --concurrency 20
python -m api_test.load_test_harness contention --fixture data/lt-fixtures/medium-01 --output data/load-tests/contention-50 --concurrency 50
```

Target는 하나의 `ramping-vus` 시나리오에서 **20 VU 600초 유지→0초 전환→50 VU 600초 유지**한다. graceful stop은 10초이며 두 독립 시나리오의 overlap으로 70 VU가 되지 않는다. 시간·VU 축소는 명시적인 validation에서만 허용한다.

```bash
python -m api_test.load_test_harness target --fixture data/lt-fixtures/medium-01 --output data/load-tests/target-validation --validation-seconds 40 --validation-vus 2
```

`--validation-seconds`는 총 2~1,198초의 짝수이며 두 plateau에 절반씩 사용한다. `--validation-vus 1|2`는 축소 시간과 함께 사용하며 1→해당 VU로 기능 검증한다. 생략하면 축소 시간에도 20→50 VU다. `validationMode:true`와 `target-mixed-validation`으로 기록하고 기본 20분의 용량 검증으로 해석하지 않는다.

혼합 비율은 **완료된 200개 workload HTTP 요청 블록** 기준이다. 목록70·단건70·리비전20·고유 PUT20·경합 PUT10·run POST10으로 35/35/10/10/5/5를 만든다. 고유 저장은 생성+3수정의 4 PUT, 경합은 5개 동시 PUT이므로 이 블록은 논리 작업177개다. 초기6작업으로 모든 종류를 확인한 후 seed/VU별 순서를 섞고 요청 흐름마다 1~3초를 기다린다. 부분 실행은 목표 비율과 다를 수 있으며 `execution.json.traffic`에 실제 건수·비율을 기록한다. 경합 문서를 만드는 준비 PUT2개는 support로 별도 기록하므로 전체 client HTTP202개 중의 비율도 함께 제공한다. `/api/run` 내부의 health 호출은 k6 client 요청 건수에 포함되지 않는다.

고유 저장은 VU별 새 `case/load-test/write/unique-vu-{id}-iteration-{n}.json`을 생성하고, `_storage` 없는 최초 PUT의 revision1부터 응답 revision을 사용해 3회 수정한다. `unique --concurrency 5|20|50`은 VU마다 한 흐름씩 실행하며 최종 revision4를 확인한다. 새 쓰기 본문은 1 KiB다. 경합은 별도 문서를 revision1로 만든 뒤 한 VU의 `http.batch`로 동일한 baseline revision을 가진 5/20/50개 요청을 동시에 보낸다. `batch`와 `batchPerHost`는50이다. 정확히1개200/revision2와 나머지409/currentRevision2를 확인하며, 409를 예상 응답으로 인정하는 callback은 이 경합 요청에만 적용한다. 다른 쓰기의409·5xx·잘못된409 body는 실패다.

사후 검증은 원본 문서의 fingerprint·모든 리비전·JSON 투영이 그대로임을 확인하고, 허용된 새 문서의 project·worker·iteration·내용·1~4 또는1~2 연속 리비전·audit·투영을 확인한다. 예상 밖 문서·원본 수정·미완료 쓰기는 거부하고 bundle을 생성하지 않는다. 저장이 추가된 목록도 원본 reference 누락·중복·허용되지 않은 새 reference를 거부한다.

`/api/run`은 복사본에 추가한 전용 project·saved health case만 사용한다. project base URL은 서버가 바인딩한 새 loopback 포트다. 전용 `run_api_tests.py` wrapper는 trusted repository의 실제 CLI/report를 사용하며 case/project/file/log/tmp 경로를 복사본에 고정하고 **정확한 prepared project·URL·GET** guard를 항상 적용한다. redirect도 허용하지 않는다. runner URL/method를 변조한 실제 CLI 회귀에서 network 함수가 호출되지 않음을 확인했다. application의 기본 소유권 계약과 동시 실행 worker2는 변경하지 않는다. HTTP429 또는 `exitCode!=0`은 실패로 기록한다.

POSIX 서버는 전용 process group에서 시작한다. 종료 시 부모가 먼저 종료되더라도 남은 group을 정리하고, SIGTERM을 무시하는 실제 테스트 자식도 종료됨을 확인했다. Windows의 자식 tree 정리는 실제 검증하지 않았다.

**2026-09-29 측정:** 축소1→2 VU/40초는45 HTTP(43 workload+2support), unique2·경합2·saved run2, 오류0·무결성 통과다. unique50은200 PUT·50문서/revision4, 경합5/20/50은 각각1승자와4/19/49 예상409를 통과했다. 반면 축소20→50 VU는 **20 VU 단계에서 `/api/run`429 두 건, 오류율1.6%로 중단**되어50 VU에 도달하지 않았다. 전체1,200초 Target은 미실행이며 Target 용량 통과·확정 SLO를 주장하지 않는다. [LT-3 원본 경로·source hash·측정 기록](load-test-lt3-validation.json)을 참고한다.

새 importer의 `summary.vusMax`는 실제 활성 `vus` 표본의 최대값이다. `vus_max`는 할당 capacity로 별도 기록하며 도달한 단계로 간주하지 않는다. 활성 표본이 없으면 기존 정수 계약의0과 unknown warning을 반환한다. 기존 저장 bundle은 자동 변경하지 않으며 원본 raw와 manifest를 다시 import해야 한다. 위 실패의 기존 보고값50을 실제 활성20으로 재집계한 별도 bundle도 보존했다.

## LT-4 중단·회복과 실행 용량

```bash
python -m api_test.load_test_harness stress --fixture data/lt-fixtures/medium-01 --output data/load-tests/stress-01
python -m api_test.load_test_harness spike --fixture data/lt-fixtures/medium-01 --output data/load-tests/spike-01
python -m api_test.load_test_harness soak --fixture data/lt-fixtures/medium-01 --output data/load-tests/soak-01
python -m api_test.load_test_harness run-capacity --fixture data/lt-fixtures/medium-01 --output data/load-tests/run-capacity-01
python -m api_test.load_test_harness fault --fixture data/lt-fixtures/medium-01 --output data/load-tests/fault-01
```

| 명령 | 기본 모델 |
| --- | --- |
| Stress | 50→75→100→125→150→175→200 VU, 각각300초 유지. 계획의 무제한 증가에 안전 상한200 VU/7단계/35분을 둔다. |
| Spike | 5→100 VU30초 상승,120초 유지,1초에5 VU로 하강. 이후300초 읽기 Baseline으로 회복 측정. |
| Soak | 계획상 Target50 VU의70%인35 VU,7,200초. 이는 검증된 안정 동시성의70%가 아니다. |
| Run capacity | 같은 서버에서1·2·5·10 VU의 단일 동시 요청 batch. 전부200/exit0인 최대값을 `maxObservedSuccessfulConcurrency`로 기록하며 지속 안정 용량으로 해석하지 않는다. |
| Fault | 전용 stub의500 응답과3,000ms 지연을 각각 주입·관측한 후 정상으로 reset. 지연은 saved case의HTTP timeout2초를 초과한다. Studio subprocess watchdog300초는 변경하거나 검증하지 않는다. |

전·후 읽기 Baseline은 각각5 VU/300초이며 **같은 server PID·port·SQLite·snapshot**을 사용한다. 중간 재시작으로 누적 자원을 숨기지 않는다. 전 Baseline이 실패하면 부하 profile을 시작하지 않는다. profile이 중단되거나 무결성 검증이 실패해도 원인 기록 후 가능한 같은 서버의 recovery를 측정한다. fault는 stub reset 후 정상 saved run1회를 추가해 실행 slot 재사용도 확인한다. 각 phase 종료 후 자식·private temporary directory가 정리됐는지 최대5초의 settle 후 확인한다.

짧은 기능 검증은 아래처럼 명시한다. 기본 시간의 campaign 완료로 표시하지 않는다.

```bash
python -m api_test.load_test_harness stress --fixture data/lt-fixtures/medium-01 --output data/load-tests/stress-validation --validation-seconds 40 --validation-vus 2
python -m api_test.load_test_harness spike --fixture data/lt-fixtures/medium-01 --output data/load-tests/spike-validation --validation-seconds 40 --validation-vus 2
python -m api_test.load_test_harness soak --fixture data/lt-fixtures/medium-01 --output data/load-tests/soak-validation --validation-seconds 40 --validation-vus 2
python -m api_test.load_test_harness fault --fixture data/lt-fixtures/medium-01 --output data/load-tests/fault-validation --validation-seconds 10 --validation-stop-seconds 2
```

`--validation-seconds`는10~120초이며 Baseline은25초로 축소한다. Stress plateau 시간을 단계 수에 맞춰 나누고 Spike는상승/유지/하강을1/4·1/2·1/4로 구성한다. `--validation-vus 1|2`는 Stress·Spike·Soak에서만 허용한다. 기본 중단 timer는 validation에서도 **1분 이동 window의5xx/network 오류율>5%, CPU>95% 또는 메모리>90%의120초 지속**을 유지한다. timer도 줄이려면 `--validation-stop-seconds 2~30`을 별도로 지정하며 변경 여부를 기록한다. semantic body/revision 실패와 `/api/run`429는 더 높은 부하로 진행하기 전에 중단한다. capacity의1/2/5/10 batch는429만 발생하고 cleanup이 검증되면 admission 결과를 계속 수집한다. 실행/semantic/network·5xx 오류나 child/tmp cleanup 실패·unknown은 다음 동시성 증가를 막고 사유를 기록한다.

중단 monitor는 k6 원본을 offset부터 증분 읽어 부분 마지막 줄을 기다리며 전체 Soak 파일을 반복 읽지 않는다. server resource는 기본5초, 짧은 validation·capacity·fault는1초 간격이다. CPU는 **현재 관측 가능한 server tree의 CPU 시간 증가/경과 시간/logical host CPU 수**, RSS는 live tree 합계다. shared page 중복과 sample 사이에 끝난 자식 CPU는 정확히 측정하지 못하고, host 전체 CPU나 load generator 자원을 뜻하지 않는다. thread/handle은 server process 범위다. DB/WAL byte·자식·tmp·log 수를 기록하고, physical disk IOPS/latency·관측 불가 항목은 `null`로 유지한다.

`server-metrics.jsonl`은 원본 k6와 따로 기록한다. 정상 종료된 phase의 interval 안에 있는 CPU/RSS/children만 `enriched-raw.jsonl`로 합쳐 importer의 series에 연결한다. native `raw.jsonl`은 보존한다. 외부 중단·timeout·무결성 실패는 `complete:false`이며 bundle을 만들지 않는다. 중단된 profile의 허용된 write prefix(예: unique revision1~3)도 내용·audit·투영을 엄격히 확인하지만,4회 저장 완료로 판정하지 않는다. 전/후 원본 fixture fingerprint는 유지한다.

회복은 읽기 p95·오류율, Baseline 끝의 안정 window에서 CPU/RSS/thread/handle 평균, 요청 후 child를 기준선120%와 비교한다. CPU 등 기준0→양수 또는 미수집은`unknown`, 양쪽0은동일, 오류율·child의0→양수는실패다. 중단 후 데이터를 보기 위해 server를 재시작하지 않는다. `campaign.json`의 profile·recovery·cleanup 판정을 함께 확인하며 실패를 재실행해 통과로 바꾸지 않는다.

Soak 성장값은 관측된 sample trend다. 계단형 증가도 기록하지만 한 번 감소했다고2시간 안정성을 증명하지 않는다. `soakStability`는 명확한 증가 후보 외에는`unknown`으로 유지한다. **full Stress stage의 SLO·최대 안정 RPS 분석은 아직 없으며 `stableStressRps:null`이다.** 지속 안정 동시성·병목·장시간 추세 분석과 최종 기준선 보고서는 LT-5의 증거가 필요하다. 현재 full35분 Stress·전체 Spike·2시간 Soak은 실행하지 않았다.

phase마다 `phase.json`, 원본·summary·resource·정상 phase의bundle을, 전체 실행에는 `campaign.json`·server log·source hash를 보관한다.500 주입이나 admission429 때문에 campaign status가 failed일 수 있고 이것을 감추지 않는다. 자원/회복 unknown도 통과로 바꾸지 않는다. [LT-4 검증 기록](load-test-lt4-validation.json)의 실제 측정 범위를 확인한다.

## LT-5 보고서 재생성

[잠정 기준선·용량·병목 보고서](load-test-baseline-report.md)와 [machine summary](load-test-baseline-summary.json)는 checked-in LT-1~LT-4 validation JSON에서 생성한다.

```bash
python -m api_test.load_test_report
python -m api_test.load_test_report --check
python -m unittest discover -s tests -p test_load_test_report.py -v
```

`--evidence-dir`와 `--output-dir`로 입력과 출력 경로를 지정할 수 있다. 생성은 JSON 4개만 사용하며 `/tmp`의 raw나 실행 파일은 필수 입력이 아니다. `--check`는 파일을 변경하지 않고 byte-equivalent 내용의 일치를 확인한다. 숫자·상태·분모·회복·같은 server PID·완료/정리 증거가 모순되면 기존 결과를 덮어쓰지 않고 실패한다. 현재 생성기는 2026-09-29 snapshot의 주요 결과를 검토한 계약으로 사용한다. 새로운 캠페인이나 주요 결과가 들어오면 결론과 입력 계약을 먼저 재검토해야 한다.

Baseline 754개 요청/310.259481초의 2.430224 RPS는 think time과 setup/grace를 포함한 관측 처리량이다. 최대 안정 RPS와 sustained 동시성, 3회 중앙값은 미확정으로 유지한다. 한 번의 1/2/5/10 동시 요청에서는 모두 성공한 관측 수가 2개였다. 회복 실패와 429를 정상으로 바꾸지 않으며, HTTP errorRate 0인 delay phase의 run exit 실패도 별도로 기록한다. 보고서 작성 완료가 전체 부하 계획이나 SLO 검증 완료를 의미하지 않는다.

## 검증 경계

현재 검증은 macOS의 같은 호스트에서 k6와 SQLite Studio를 실행한 결과다. 환경 제한으로 loopback bind가 거부되는 경우 검증 명령에 필요한 권한을 받은 환경에서 재실행해야 한다. probe의 7개 요청과 단일 Smoke·Baseline의 RPS·p95는 실행 연결·읽기 계측 값이며 확정된 서비스 용량·SLO 기준선이 아니다. LT-4는 같은 서버의 resource·중단·회복·단일 batch admission을 기록한다. physical disk IOPS/latency, sustained 안정 동시성·full campaign·정확한 장시간 추세 판정은 미검증이다. Windows 실행은 경로와 subprocess API 호환성을 고려했지만 실제 Windows 기기에서는 아직 검증하지 않았다.

2026-09-29의 실제 건수·크기는 [LT-1 검증 기록](load-test-lt1-validation.json), 기본 60초 Smoke·300초 Baseline의 실행 metadata·수치는 [LT-2 검증 기록](load-test-lt2-validation.json)을 참조한다.

자동 회귀 검증:

```bash
python -m unittest discover -s tests -p test_load_test_harness.py -v
node load-tests/k6/studio-summary.test.mjs
node load-tests/k6/read-model.test.mjs
node load-tests/k6/mixed-model.test.mjs
node load-tests/k6/campaign-model.test.mjs
python -m unittest discover -s tests -p test_load_test_campaigns.py -v
python -m unittest discover -s tests -p test_load_test_mutations.py -v
python -m unittest discover -s tests -p test_load_results.py -v
```

k6 원본 형식과 system tags는 [JSON output](https://grafana.com/docs/k6/latest/results-output/real-time/json/), [options reference](https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/)를 따른다.

읽기 부하 구성은 [constant-vus executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-vus/)와 [threshold abort options](https://grafana.com/docs/k6/latest/using-k6/thresholds/)를 따른다.

VU metric 의미는 [k6 metrics reference](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/)를 따른다.

시나리오 종료와 grace는 [k6 graceful stop](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/graceful-stop/), executor 설정은 [k6 scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/)를 따른다.

## P0 반복 실행과 비동기 접수 검증

기존 `run-capacity`는 1/2/5/10의 단일 동시 batch이며 지속 실행 증거와 구분한다. 다음 명령은 같은 격리 서버에서 before Baseline → sync 1 VU 반복 → sync 2 VU 반복 → async 5개 제출/조회 → after Baseline을 기록한다.

```bash
python -m api_test.load_test_harness run-sustained --fixture data/lt-fixtures/medium-01 --output data/load-tests/admission-sustained-01
python -m api_test.load_test_harness run-sustained --fixture data/lt-fixtures/medium-01 --output data/load-tests/admission-sustained-validation-01 --validation-seconds 10
```

sync phase는 기본 각 60초, 명시적 validation은 각 10~120초다. VU는 1→2 고정이며 worker 기본 2를 증가시키지 않는다. 매 HTTP 200 응답의 exit 0, report/response Run ID 일치, 준비된 case의 terminal passed와 대상 HTTP 200을 확인한다. raw에서 **VU별** 성공 수와 첫/마지막 성공 시각·span을 기록하고, 각 VU가 최소 2회 성공하며 성공 span이 설정 시간의 절반 이상인 경우만 반복 실행 검증을 통과한다. phase elapsed에는 startup·정리가 포함되므로 이것만으로 실행 지속 시간을 판정하지 않는다. 정확히 60초 동안 모든 순간의 동시 실행이나 최대 안정 용량을 입증하는 시험은 아니다.

queue phase는 준비된 local stub의 지연을 500ms로 고정한 뒤 5개를 한 번씩 제출한다. 202/고유 Run ID 5개, **GET에서 실제 queued와 running 관측**, 동일 ID/report의 terminal passed/exit 0 5개를 요구한다. 한 번의 batch이므로 queue의 장시간 처리량·공정성을 판정하지 않는다. 조회 deadline은 15초이며 조회 round 사이에서 확인한다. round 안의 최대 5개 GET은 각각 timeout 5초이므로 15초에서 즉시 끝남을 보장하지 않는다. 전체 queue workload는 k6 최대 30초와 grace 5초로 제한한다. 접수 실패·network ambiguity·terminal 오류는 새 제출로 재시도하지 않는다. phase 종료 후 child/tmp가 0으로 검증되지 않으면 다음 VU/queue로 진행하지 않는다. 실패는 failed, 누락된 cleanup 관측은 unknown이며 둘 다 증가를 막는다.

`campaign.json`의 `admissionStatus`와 각 `admissionValidation`은 반복 실행/queue/정리 판정이다. 기존 `status`는 전후 읽기·CPU/RSS/thread/FD 회복 판정도 반영하므로 admission이 passed여도 recovery 실패면 campaign은 failed다. raw·summary·phase·source hash·실행 PID와 원본 fixture 불변성을 보존한다. `maximumStableConcurrency`는 null이다. 과거 LT-5 생성 보고서의 실패/unknown은 이 검증으로 덮어쓰지 않으며, 다음 P1 동일 조건 3회 기준선과 회복 원인 분리에서 추가 판단한다.

실행 API 선택·429와 중복 제출 주의사항은 [접수 정책](async-runs.md#실행-접수-정책)을 따른다.

2026-10-01 Small/각10초 실제 검증은 admission passed지만 thread 회복 4.5→5.461538(121.37%)로 전체 campaign failed다. sync1 32회·sync2 각31회, async5개 terminal passed·모든 phase child/tmp0을 확인했다. [별도 검증 기록](run-admission-validation.json)의 진단 실패와 최종 실행을 함께 보존한다.
