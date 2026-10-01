# LT-5 잠정 기준선·용량·병목 보고서

측정일: 2026-09-29. 보고서 작성은 완료했지만 전체 부하 캠페인과 SLO 검증은 미완료다.

**최대 안정 RPS와 지속 안정 동시성은 미확정이다. 한 번의 동시 요청에서 모두 성공한 관측 요청 수는 2개다.**

## 관측된 기준선

Medium 데이터셋, 같은 호스트의 macOS·SQLite에서 5 VU Baseline을 실행했다. 754개 요청 ÷ 310.259481초 = **2.430224 RPS**이며, p95는 **53.183 ms**, p99는 69.64049 ms, HTTP 오류율은 0.0%다.
이 처리량에는 1~3초 think time, setup과 graceful stop이 포함된다. 서버의 최대 처리량을 뜻하지 않는다. 같은 조건의 3회 실행이 없어 중앙값은 null로 유지한다. 서로 다른 코드·설정·짧은 window의 p95/p99를 합산하거나 평균 내지 않는다.

`/api/cases`의 p95는 71.39525 ms다. 전체 endpoint 관측값은 machine summary에 보존한다.

## 최초 실패와 회복

| 시험 | 관측 | 판정 |
| --- | --- | --- |
| Target shortened20→50 | 실제 20 VU, 125개 요청, 429 2건 | 다음 단계 미도달·용량 실패 |
| Stress shortened50→200 | 초기 설정 50 VU, 121개 요청, 429 6건 | 다음 단계 미도달·용량 실패 |
| spike 회복 (2 VU 설정·축소) | 61.42995 → 84.4885 ms, 기준선의 137.54% | 120% 초과·실패 |
| stress 회복 (200 VU 설정·축소) | 43.10875 → 62.45055 ms, 기준선의 144.87% | 120% 초과·실패 |

Target의 실제 활성 20 VU와 할당 50 VU를 구분했다. Stress는 초기 50 VU plateau 10초가 끝나기 전에 중단되어 75 VU로 올라가지 않았다. LT-4의 기록과 별도 raw 검증은 실제 peak 50 VU를 확인했으며, 할당 200 VU를 peak로 사용하지 않는다. 실패를 재실행으로 덮어쓰지 않는다.

## 단일 동시 요청과 장애 주입

| 동시 요청 | 200/exit 0 | 429 |
| --- | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 5 | 2 | 3 |
| 10 | 2 | 8 |

측정 snapshot의 worker 설정 2와 [측정 당시 JobManager](../api_test/jobs.py)의 nonblocking `legacy_slot` 거부 구조가 이 결과를 설명한다. 현재 다른 설정이나 지속 부하에서의 최대 동시성을 검증한 것은 아니다.
의도적으로 주입한 500은 명시적으로 축소한 2초 gate에서 중단됐다. stub의 3초 지연은 saved case의 HTTP timeout 2초를 초과했다. Studio subprocess watchdog 300초와는 별도 경로다. delay phase의 HTTP errorRate는 0이지만 run exit 실패 2건을 별도로 기록했다. reset 후 정상 saved run 1회의 exit 0, 정리와 회복도 확인했다.

## 시나리오와 SLO 검증 범위

| 항목 | 상태 | 증거 범위 |
| --- | --- | --- |
| Smoke | 관측 범위 통과 | endpoint별1VU60초·214요청;1회 |
| Baseline | 잠정 | 5VU300초·754요청;동일조건3회/중앙값 미확정 |
| Target | 관측 실패 | 실제20VU429;50VU/전체1200초/3회 미검증 |
| 고유 저장/경합 | 관측 범위 통과 | 50VU단일batch revision4;5/20/50정확히1승자;지속시험 아님 |
| Stress | 관측 실패 | 50VU429중단·회복실패;full단계/SLO/최대RPS 미확정 |
| Spike | 관측 실패 | 축소1→2→1에서p95회복실패;full100VU미검증 |
| Soak | 미확정 | 2VU40초;35VU2시간안정성 미검증 |
| Target 읽기p95≤300/p99≤1000ms | 미확정 | Baseline값으로TargetSLO를 판정하지 않음 |
| Target 고유 쓰기p95≤1000ms | 미확정 | unique50의단일batch값으로TargetSLO를 판정하지 않음 |
| 비예상 오류율<1% | 관측 실패 | 축소Target125요청중429두건=1.6% |
| 정상입력5xx0 | 관측 범위 통과 | 관측normal호출 범위;intentional500별도;production보장 아님 |
| run exit0/고아0 | 부분 검증 | healthy호출/정리확인;429거부·injectedtimeout exit실패 별도 |
| CPU85%/메모리80% 5분 | 미확정 | 실제지속시험 미실행;timer단위테스트만 |
| 중단60/120초 | 부분 검증 | fake timestamp검증·scaled2초fault·실제429중단;full실시간120초미검증 |
| 회복120% | 관측 실패 | Spike/50VUStress p95초과;다른resource통과가 원인증명은 아님 |
| IOPS/latency/Windows/별도발생기 | 미확정 | 수집/실행 미검증 |

## 병목의 증거와 가설

- 확인된 제약은 측정 환경의 동시 실행 2개와 429다. 정책과 queue 사용 흐름을 먼저 검토한다. 이 보고서는 worker를 증가시키지 않았다.
- 확인된 코드 패턴은 [case 목록](../api_test/services/documents.py) → [case_summaries/read_studio_document](../api_test/services/studio.py)다. SQLite 경로는 프로젝트의 JSON 투영을 읽고 파싱한다. 관측된 Medium은 프로젝트당 100개 case와 1/10/100 KiB 본문을 포함한다. 파일 읽기, SQL, serialization의 실제 비중과 최적화 효과는 미측정이다.
- 회복 p95가 기준선의 137.54%와 144.87%가 된 것은 측정 사실이다. 같은 호스트의 부하 경쟁, 짧은 window, 캐시나 파일 읽기의 영향은 가설이다. per-query/file trace가 없어 원인을 단정하지 않는다. lock 오류가 보이지 않았다는 사실도 SQLite 용량의 증거가 아니다. PostgreSQL 부하 경로는 미검증이다.

## 우선 후속 작업

**P0 실행 정책** — 동시 실행 2개, 429 안내와 RUN-2 queue 사용 기준을 확정한다.

`python -m api_test.load_test_harness run-capacity --fixture data/lt-fixtures/medium-01 --output data/load-tests/admission-review`

완료 기준: 이 명령은 단일 batch만 측정한다. sustained executor는 아직 없으므로 별도로 구현·검증하고, 지속 실행 성공과 고아 프로세스 0을 확인해야 안정 동시성을 판정할 수 있다.

**P1 비교 가능한 기준선** — 동일한 코드 hash, fixture, hardware, 발생기와 window로 Baseline 3회를 수집한다.

`python -m api_test.load_test_harness baseline --fixture data/lt-fixtures/medium-01 --output data/load-tests/baseline-repeat-01`

완료 기준: 01/02/03의 새 output으로 반복한다. 동일 조건을 확인한 뒤 run 단위 중앙값을 검토하며 percentile 표본을 pool하지 않는다.

**P1 회복 원인 분리** — 목록 SQL, 투영 읽기·JSON 파싱, serialization과 서버·발생기 CPU를 분리 계측한다.

`python -m api_test.load_test_harness spike --fixture data/lt-fixtures/medium-01 --output data/load-tests/spike-cause --validation-seconds 120 --validation-vus 2`

완료 기준: 기존 실패를 보존하고 같은 window의 120% 조건과 원인 trace를 비교한다. 현재 명령은 query trace나 device IOPS를 수집하지 않으므로 별도 계측이 필요하다.

**P2 데이터 규모와 전체 캠페인** — 실행 정책과 안전 조건을 해결한 뒤 Small/Medium/Large, Target 3회, Stress·Spike·Soak을 격리 환경에서 측정한다.

`python -m api_test.load_test_harness soak --fixture data/lt-fixtures/medium-01 --output data/load-tests/soak-full`

완료 기준: 실제 2시간, 단계별 SLO, 중단·회복과 장시간 추세 근거가 없으면 최대 용량과 안정성은 미확정으로 유지한다. 전체 실행을 이 보고서 생성 과정에서 수행하지 않는다.

**P2 재현과 보존** — 원본, 환경, 실행 코드와 importer 버전을 정규화 결과와 연결해 보존한다.

`python -m api_test.load_test_report --check`

완료 기준: clean clone에서 checked-in JSON만으로 같은 보고서를 만든다. /tmp 경로는 증거 포인터이며 필수 입력이 아니다.

## provenance와 재생성

생성기는 2026-09-29 LT-1~LT-4 snapshot의 주요 결과를 검증한다. 숫자, 분모, 상태, PID와 회복 산술이 모순되거나 중요한 collection이 없으면 보고서를 만들지 않는다. 주요 결과가 달라진 새 snapshot은 별도 검토가 필요하다. source hash와 진단·최종 버전 차이는 evidence 파일에 보존한다. 원본 raw의 독립 검증은 별도이며, 입력 hash가 원본의 진실성을 증명하지는 않는다.

| 입력 | SHA256 |
| --- | --- |
| [load-test-lt1-validation.json](load-test-lt1-validation.json) | `f328a41fa33bdfa0a225bf2c51db5edbbce1cda4edf0528c66c8f7c53bcd4fac` |
| [load-test-lt2-validation.json](load-test-lt2-validation.json) | `06d0fa8c6f322477f9b10fe66947f4373ec118030167492356fd5e53ee12218b` |
| [load-test-lt3-validation.json](load-test-lt3-validation.json) | `ac75abb86e907b01db02cd1cd1eea21cbd3332ec71f58a50b9ad4a6ef918f18e` |
| [load-test-lt4-validation.json](load-test-lt4-validation.json) | `83d084edd5d9eba4be4c8b075a6035cd8809e16d99fe4008e894bdfab1bafb12` |

`python -m api_test.load_test_report`로 재생성하고, `--check`로 파일을 변경하지 않고 일치 여부를 확인한다.
