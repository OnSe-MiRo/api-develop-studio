# API 부하테스트 및 대시보드 개발 진행 기록

## LT-1~LT-5 develop 통합·원격 반영 (2026-10-01)

- 시작: 사용자 요청으로 LT-1~LT-5의 34개 파일을 `feature/load-test-harness`의 `bea88f32`에 커밋했다. 게시 대상은 `origin/feature/load-test-harness`와 `origin/develop`이다.
- 통합: 최신 `develop`의 `6206f173`에 포함된 OBS-1 변경을 기능 브랜치에 반영한다. 제품 코드는 충돌 없이 합쳐졌고 개발 진행 기록의 충돌은 양쪽 이력을 보존해 해결했다.
- 검증: 통합 후 전체 Python 392개(skip 0, 99.090초), 프런트엔드 48개·production build, 생성 코드·LT-5 보고서 정합성, 공백 검사가 통과했다. 기존 부하 측정의 실패·unknown과 미검증 범위는 해당 측정 시점의 기록이다.
- 로컬 반영: 기능 커밋 `bea88f32`와 최신 develop 통합 커밋 `95e5c563`을 로컬 `develop`에 병합한다. 검증된 기능 브랜치와 제품 코드가 동일하며 진행 기록만 게시 상태에 맞춰 갱신했다.
- 원격 차단: `git push -u origin feature/load-test-harness`는 자동 승인 검토에서 원격 저장소와 코드 전송에 대한 구체적 승인 부족으로 거부됐다. 원격 `develop`은 `6206f173`이며 원격 기능 브랜치는 없다. `https://github.com/OnSe-MiRo/api-develop-studio.git`의 두 브랜치 게시에 대한 사용자 승인이 남아 있다.

## LT-5 잠정 보고서·재현 도구 완료 / 전체 캠페인 미완료 (2026-09-29)

- 완료: checked-in LT-1~LT-4 JSON만 사용한 기준선·용량·병목 보고서와 machine summary, input SHA256·deterministic `--check`·모순/누락 fail-closed 검증을 완료했다. 임시 원본 경로가 없어도 재생성하며 UTF-8 경로를 지원한다.
- 결론: Baseline은754개/310.259481초=2.430224RPS·p95 53.183ms의 잠정 관측값이다. think time을 포함하며 최대 안정 RPS·sustained 동시성·3회 중앙값은null이다. 단일 동시 요청 관측2와 측정 당시worker2 제약, Target/Stress429·Spike/Stress 회복 실패·Soakunknown을 분리했다.
- 증거/가설: code/admission으로 확인된 거부 구조와 case 목록의 투영 읽기/JSON 패턴을 기록했다. 파일I/O·SQL·같은호스트 영향이나 회복 실패 원인은 아직 가설이다. normal HTTP오류와 의도적인 timeout의 run exit실패를 구분하고 전체 시나리오/SLO coverage·우선 후속 명령/완료 기준을 작성했다.
- 검증: 신규9개·전체Python382(skip0,44.620초), compile·diff·report check 통과. 독립 raw32개 count/error/p95/p99/RPS 및 회복7개 산술 일치,13개 모순 입력 거부, generator+JSON4개만 복사한 standalone/Unicode 경로·반복byte동일·stalecheck무수정·NaN거부를 확인했다.
- 산출물: [잠정 보고서](load-test-baseline-report.md), [machine summary](load-test-baseline-summary.json), [검증·provenance](load-test-lt5-validation.json). LT-5 보고서 작성은 완료했지만 전체 부하 계획과 SLO 검증은 미완료다. fullcampaign·지속 안정 용량·stageSLO·physicalIOPS/Windows는 미검증이며 새로운 load나 tuning은 수행하지 않았다.
- Git/다음: `feature/load-test-harness`의 LT-1~LT-5 미커밋 변경을 보존했다. 커밋·푸시·병합·브랜치 삭제 없음. 다음은 보고서 P0 실행 정책 검토와 P1 동일 조건3회 기준선·회복 원인 분리다. 새 LT 단계 번호를 만들지 않는다.


## LT-5 의미 있는 변경·관련 검증 (2026-09-29)

- 변경: checked-in LT-1~LT-4 JSON만 읽는 report CLI, input SHA256·deterministic `--check`, Korean 잠정 보고서와 machine summary를 추가했다. `/tmp` 포인터는 필수 입력이 아니고 UTF-8로 생성·검사한다.
- 근거: Baseline754/310.259481초=2.430224RPS·p95 53.183ms·case목록71.39525ms는관측값이며 maximum이 아니다. 최대안정RPS·sustained동시성·3회중앙값은null, 단일 batch 관측2·Target/Stress429·회복실패·미검증SLO를 분리했다.
- 검증: 신규9개 테스트로 nonfinite/음수·분모/예상409·falsepass·PID/정리/완료·missingcollection·회복산술·normal500·determinism/check무수정을 확인했다. 최초 aborted fault의 nullsummary 경계와 모순된 snapshot을 받아들이던 draft 검증은 fail-closed로 수정했다.
- 독립 확인: 주 에이전트는 원본32개를 importer 없이 집계해 count/error/p95/p99/RPS가2e-6 이내 일치함과 회복7개 산술을 확인했다. generator+JSON4개만 복사한 별도 경로에서도 byte동일·Korean경로·check무수정·NaN거부를 확인했다. input hash는 raw 진실성의 증명이 아니며 독립 raw 감사와 구분한다.
- 상태: 기능·관련 검증 완료, 주 에이전트의 최종 전체 회귀/보고서 독립 검토 대기. product tuning·새 load·Git 게시 작업 없음.


## LT-5 시작 (2026-09-29)

- 시작: `feature/load-test-harness`의 LT-1~LT-4 미커밋 변경을 보존하고 실제 측정 기반 기준선·용량·병목 보고서를 작성한다.
- 범위: checked-in LT-1~LT-4 evidence를 입력으로 하는 재현 가능한 report CLI·Korean 보고서·machine summary, input hash·산술 검증·최초 실패·SLO/시나리오 coverage·우선 후속 명령/완료 기준.
- 판단 경계: maximum stable RPS·sustained run capacity는unknown, single batch admission2·worker2 제약은별도 증거다. 다른 source/시간/window의 percentile이나 median을 합치지 않는다. fullcampaign·최적화·product tuning·Git 게시 작업 없음.
- 검증: generator의 정상/불일치·unknown·deterministic/check 경계를 구현 에이전트가, raw/source 산술과 보고서 내용을 주 에이전트가 독립 확인한다. `/tmp` 포인터는필수 입력으로 사용하지 않는다.


## LT-4 로컬 구현·검증 완료 / 회복 실패·unknown 보존 (2026-09-29)

- 구현: bounded Stress/Spike/Soak·1/2/5/10 admission·controlled500/지연 timeout 명령, 같은 PID의 before/profile/after, 증분 rawtail·CPU/RSS/thread/FD/child/DB/WAL·tmp/log 기록과 enriched series, 중단·recovery·cleanup 판정을 완료했다. before/cleanup 미검증은 load 증가를 막고 worker2는 유지한다.
- 실제 측정: single synchronized batch에서1/2는200/exit0,5는2성공+3x429,10은2성공+8x429였다. `maxObservedSuccessfulConcurrency:2`이며 sustained 안정 최대값이 아니다.40초 축소Stress/Spike/Soak의 요청·무결성·같은 PID·child/tmp0을 확인했다.
- 실패/unknown: Spike recovery p95는61.43→84.49ms로120%를 초과했다. 실제50VU Stress는 약3.50초,121HTTP(84x200+31예상409+6x429)에서 중단해75VU로 증가하지 않았고 recovery43.11→62.45ms도 실패했다.40초 Soak은 functional 요청 통과지만2시간 trend 안정성unknown이다. 실패를 재실행하여 통과값으로 대체하지 않는다.
- 최종 fault/interrupt:500은 명시적인scaled2초 gate로 중단,3초stub지연은caseHTTP2초 timeout2건을 관측했다. reset후 saved run1회의200/exit0·정상 slot 재사용과 recovery56.12→64.13ms·child/tmp0을 확인했다.500 주입의 aborted 상태는 전체failed로 보존했다. 별도SIGINT에서 관측4PID 모두 종료·raw보존·incomplete phase/no bundle·tmp0·serverStopped를 확인했다.
- 검증: 전체Python372(skip0,89.240초) 통과 후 최종 narrow capacity/recovered-run 보완은 관련29개(8campaign+6mutation+15harness,1.302초)와 최종 실제fault로 확인했다. 현재discoverable373개 전체를 실행했다고 주장하지 않는다. Node campaign6 assertions/mixed7/read6/summary·compile·diff 통과.
- 한계/다음: 같은 호스트macOS·SQLite Medium의 축소·단일 batch 검증이다. full35분Stress/fullSpike/2시간Soak, 실제120초CPU/메모리 지속, physical diskIOPS/latency·host전체CPU·Windows tree·Studio300초watchdog는 미검증이다. StableStressRps=null, stageSLO/지속 안정 동시성·엄밀Soaktrend·최종보고는LT-5로 남긴다. [명령](load-test-harness.md), [source hash·원본 경로·진단/최종 구분](load-test-lt4-validation.json).
- Git: `feature/load-test-harness`의LT-1~LT-4 미커밋 변경을 보존했다. 커밋·푸시·병합·브랜치 삭제 없음. 다음은LT-5 기준선·용량·병목 보고서다.


## LT-4 의미 있는 변경·관련 검증 (2026-09-29)

- 변경: focused campaign/monitor module과 executor presets를 추가하고 같은 PID의 before→profile→after Baseline, nullable CPU/RSS/thread/FD/child/DB/WAL·tmp/log 기록, 증분 raw tail·monotonic 중단timer·resource series 연결을 구현했다. before 실패는 profile을 막고 semantic/429는 추가 증가를 중단한다.
- 검증: campaign7개·mutation6개(중단 prefix/audit 포함), 기존 importer13개, Node campaign6 assertions·mixed7/read6/summary 회귀 통과. 최초 malformed/empty control body의 JSON decode가500이던 경계는 generic400으로 수정 후 통과했다.
- 실제 진단: 같은 server의1/2/5/10 admission에서1/2 성공·5는3건429·10은8건429를 기록했다. controlled500은 scaled2초 window로 중단,3초 stub 지연은 caseHTTP2초 timeout으로 관측됐다. 축소Stress·Spike·Soak의 요청·무결성·자식/tmp 정리를 확인했다.
- 실패 보존: 축소Spike의 회복 p95가61.43→84.49ms로120%를 초과했고,50VU Stress는4296건을 감지해75VU로 올라가기 전에 중단됐다. 후자의 회복p95도43.11→62.45ms로 실패했다. 단순 재실행으로 통과값을 선택하지 않는다.
- 제한: full campaign 미실행, Soak trend 판정unknown, physical diskIOPS/latency와 Windows 자식tree 미검증. StableStressRps는null이며 지속 안정 용량·stageSLO/최종보고는LT-5로 남긴다. 현재 최종SIGINT·전체 회귀 독립 검증을 기다린다.


## LT-4 시작 (2026-09-29)

- 시작: `feature/load-test-harness`의 LT-1~LT-3 미커밋 변경을 보존하고 Stress·Spike·Soak·실행 용량·장애/회복 계측을 구현한다.
- 범위: 상한이 있는 재현 가능한 캠페인 명령, 동일 격리 서버의 전/후 Baseline, `/api/run` 동시1/2/5/10, 제어 가능한 local stub delay/error·runner timeout, 증분 raw tail·서버 자원·중단/회복 기록.
- 경계: 기존 worker2·20VU429 실패를 보존한다. full2시간Soak/Stress/Spike는 실제 실행 증거 전 미검증이며 축소 검증의 시간/VU·중단 timer는 명시적으로 구분한다. production·외부 URL·사용자 데이터·Git 게시 작업은 없다.
- 검증: 관련 테스트/짧은 local 검증을 구현 에이전트가, 실제 독립 캠페인·전체 회귀를 주 에이전트가 진행한다. resource unknown을0 또는 통과로 취급하지 않는다.


## LT-3 구현·로컬 검증 완료 / Target 용량 실패 (2026-09-29)

- 변경: Target20→50 VU의600초/600초 plateau, 완료200 workload HTTP 기준35/35/10/10/5/5 비율과 준비 traffic 분리, 고유 생성+3수정, 같은 revision의5/20/50 batch 경합, 전용 saved-case runner와 허용 쓰기의 SQL/revision/audit/JSON 검증을 구현했다. 원본 fixture는 불변이며 application 저장/실행 계약과 worker2를 변경하지 않았다.
- 기능 검증: 격리 Medium의40초1→2 VU Target은45HTTP(43workload+2support), unique2·경합2·saved run2·오류0·무결성·정상 종료를 통과했다. unique50은200PUT·50문서/revision4, 경합5/20/50은 정확히1승자·4/19/49 예상409/currentRevision2·투영 일치를 통과했다. 주 에이전트의 별도 barrier HTTP 계약 검증도 동일하게 통과했다.
- **Target 용량 실패:** 축소20→50 VU는 약5.8초, 실제20 VU 단계에서 `/api/run`429 두 건(125요청·오류율1.6%)으로 threshold가 실패했다. failed bundle과 원본·무결성·정상 종료를 보존했다. **50 VU 단계와 전체1,200초 Target은 미검증**이며 용량·SLO 통과를 주장하지 않는다. 실행 제한2를 유지하고 후속 LT-4의 실행 용량·중단·회복 계측으로 연결한다.
- 실측 보완: k6의 `vus_max`50은 할당 capacity였고 실제 `vus` peak는20이었다. importer는 활성 표본만 사용하도록 수정하고 missing sample은0/unknown warning으로 기록한다. 원본 artifact는 유지하며 별도 재집계 bundle의20을 확인했다. 기존 저장 bundle의 자동 migration/재집계는 없다.
- 최종 검증: 전체 Python364(skip0,46.197초), frontend45/build, 하네스15·mutation5·importer13, Node mixed7·read6·summary 회귀, compile·diff 검사 통과. 변조 URL/method의 실제 CLI가 network 호출 전에 거부됨을 확인했고, 부모가 먼저 종료된 뒤 SIGTERM을 무시하는 실제 자식의 private group도 종료했다.
- 판정/다음: LT-3 구현·로컬 기능 검증 완료; Target 용량은 실패 상태다. 같은 호스트macOS/SQLite/Medium 범위이며 Windows 자식 tree·운영·PostgreSQL 부하·장시간 campaign은 미검증이다. [명령](load-test-harness.md), [실행 source hash·수치·제한](load-test-lt3-validation.json). 다음은 LT-4 Stress·Spike·Soak 및 `/api/run` 용량·회복 시험이다.
- Git: `feature/load-test-harness`에 LT-1~LT-3 미커밋 변경을 보존했다. 커밋·푸시·병합·브랜치 삭제 없음.


## LT-3 시작 (2026-09-29)

- 시작: `feature/load-test-harness`의 LT-1·LT-2 미커밋 변경을 보존하고 Target 혼합·고유 저장·동일 문서 경합을 구현한다.
- 범위: 기본 20→50 VU·단계별10분 Target, HTTP workload 기준35/35/10/10/5/5 비율과 별도 준비 요청 기록, 생성+3회 수정, 같은 revision의5/20/50 동시 PUT, 격리 saved case의 `/api/run`과 저장 사후 무결성.
- 계약: 생성 PUT은 `_storage`를 생략하고 수정은 직전 응답 revision을 사용한다. 예상409도 body.currentRevision을 확인하며 `/api/run`의429/exitCode 오류는 실패로 기록한다. 원본 fixture는 불변이고 복사본의 허용된 새 문서만 검증한다.
- 실행 경계: 새 loopback 서버·SQLite·case/project/log/tmp와 전용 runner wrapper에 한정한다. 외부 URL·사용자 데이터·운영 부하·LT-4~LT-5와 Git 게시 작업은 포함하지 않는다. 전체20분 Target은 검증 증거가 없으면 미실행으로 남긴다.
- 검증: 단위·Node·짧은 실제 k6를 구현 에이전트가, 전체 회귀·축소 Target·독립5/20/50 경합·고유 저장은 주 에이전트가 확인한다.


## LT-2 최종 검증·완료 (2026-09-29)

- 판정: Smoke·읽기 Baseline의 로컬 구현·검증 완료. 기본 60초 Smoke(7 endpoint×1 VU, 요청214)와 300초 Baseline(5 VU, 요청754)에서 상태·본문 checks 각각428/1,508 모두 통과, 오류율0·threshold 통과·endpoint7·fixture 불변·정상 종료를 독립 확인했다.
- 최종 검증: 주 에이전트 전체 Python 354개(skip 0, 94.869초), frontend 45개·build, Node 읽기 모델 6개·summary 시작시각 회귀, `git diff --check` 통과. 구현 에이전트의 하네스12·importer11도 통과했다.
- 최종 source 검증: output preflight·bundle-after-integrity 보완을 포함한 실제 3초 validation Smoke는 요청10·VU7·오류0·threshold·schema·fingerprint·서버 종료를 통과했다. 기본 부하 스크립트와 importer는 기본 실행 이후 변경하지 않았고, 실행별 source hash와 validation 여부를 [측정 기록](load-test-lt2-validation.json)에 보존했다.
- 경계: 같은 호스트 macOS/SQLite의 Medium에서 각 기본 모델 1회 검증이다. p95 Smoke 56.45045ms·Baseline 53.183ms는 이번 실행 수치이며 확정 SLO·용량·3회 중앙값·전체 dataset 비교를 의미하지 않는다. LT-3~LT-5·운영 부하·Windows·서버 자원 시계열은 후속 범위다.
- Git/다음: `feature/load-test-harness`에 LT-1·LT-2 미커밋 변경을 보존했다. 커밋·푸시·병합·브랜치 삭제 없음. 다음은 LT-3 Target 혼합 및 저장 경합 시나리오다.


## LT-2 기본 실행 검증 완료·최종 회귀 대기 (2026-09-29)

- 독립 기본 Smoke: 격리 Medium에서 60초, endpoint별 VU1(합계7), 요청214·checks428/실패0·오류율0·p95 56.45045ms·endpoint7·series13·threshold 통과. 서버 로그에서 프로젝트20개와 케이스 reference30개 순환을 확인했다.
- 독립 기본 Baseline: 같은 전용 Medium 스냅샷에서 300초·VU5, 요청754·checks1,508/실패0·오류율0·p95 53.183ms·endpoint7·series63·프로젝트20개 순환·threshold 통과. 두 실행 모두 fixture fingerprint 불변, 원본→summary→bundle·서버 종료를 확인했다.
- 최종 보완: 스냅샷 정합성과 fingerprint를 통과한 뒤에만 bundle을 기록한다. timeout/무결성 오류는 정상처럼 보이는 bundle을 남기지 않고, threshold 실패는 무결성 통과 후 failed bundle로 보존한다. 관련 12개 하네스 테스트 통과; 이 기록 순서와 output preflight는 부하 모델 변경 없이 별도 검증했다.
- 경계: macOS 같은 호스트·SQLite·Medium에서 각 기본 모델 1회 검증이다. 확정 용량·SLO·3회 중앙값·Small/Medium/Large 성능 비교는 판정하지 않는다. [명령](load-test-harness.md), [실행 metadata·측정값](load-test-lt2-validation.json).
- 현재: 최종 짧은 실제 k6 검증과 주 에이전트 전체 회귀 확인 후 LT-2 완료 상태를 확정한다. 미커밋·미푸시·미병합.


## LT-2 의미 있는 변경·중간 검증 (2026-09-29)

- 변경: 기본 Smoke 7 endpoint×1 VU×60초와 Baseline 5 VU×300초를 같은 격리 실행기로 연결했다. 전체 dataset 범위·duration/VU·validation 모드를 metadata에 기록하고 `load-test/{dataset}.json` 구분자를 사용한다. reference 순환·1~3초 think time, 상태·본문 의미·coverage 검증과 duration/grace/process timeout 경계를 추가했다.
- 회귀: 하네스 12개(config·원본 보존·timeout/threshold/무결성 실패의 종료 기록·중단·fixture 내부 출력 거부), importer 11개(object threshold 수치·verdict 동일성과 잘못된 expression 거부 포함), Node 읽기 모델 6개(선택·pacing·안전한 metric 이름·본문 오류), summary 시작시각 회귀 통과.
- 실패/해소: 실제 k6의 abort threshold가 raw JSON에서 객체로 기록되어 첫 짧은 실행과 주 에이전트 첫 60초 Smoke의 importer가 거부했다. expression만 정규화하는 owning importer 수정과 실제 원본 replay로 해소했다. 수정 후 독립 60초 Smoke는 214요청·428 checks/실패 0·VU7·오류0·7 endpoint·threshold·bundle·정합성·서버 종료를 통과했다.
- 안전 보완: 실행 output을 fixture 내부에 지정하면 복사본을 다시 포함하는 재귀 복사가 발생할 수 있어 디렉터리 생성 전에 거부한다. 동일·하위·다단계 하위 output에서 fixture 파일 집합과 fingerprint 불변을 검증했다. 실제 실행과 별개로 이 preflight 보완을 검증했다.
- 테스트 보완: 실패 경계 테스트의 첫 mock은 플랫폼 조회의 내부 subprocess에도 적용되어 목적한 k6 경계에 도달하지 못했다. 플랫폼 metadata를 별도 stub해 timeout·threshold·무결성 실패 3종 모두 기록·종료·원본 보존을 검증했다.
- 현재 검증: 독립 기본 300초 Baseline과 전체 회귀를 주 에이전트가 진행 중이다. 이 증거 전 LT-2 완료 판정을 보류한다. Git 게시 작업 없음.


## LT-2 시작 (2026-09-29)

- 시작: `feature/load-test-harness`의 LT-1 미커밋 변경을 보존하고 Smoke·읽기 Baseline을 구현한다.
- 범위: endpoint별 1 VU·60초 Smoke, 5 VU·300초 읽기 Baseline, dataset 전체의 seeded reference 순환·1~3초 think time, 상태·본문 의미 검증, 안전한 endpoint metric·summary/importer 연결.
- 실행 경계: 새 격리 fixture 스냅샷·loopback 서버에만 실행한다. 짧은 검증은 별도 validation metadata/scenario로 구분한다. LT-3~LT-5, 운영 부하와 Git 게시 작업은 수행하지 않는다.
- 검증: 관련 단위·Node·짧은 실제 k6 검증은 구현 에이전트가, 전체 회귀·기본 60초 Smoke/300초 Baseline은 주 에이전트가 독립 실행한다.


## LT-1 구현·검증 완료 (2026-09-29)

- 변경: 전용 fixture 생성·검증 CLI, 격리 SQLite·JSON 투영·로그와 실행 전 복사 스냅샷, 1 VU·단일 iteration k6 probe, 환경·명령·source hash·dirty 상태·종료 기록 및 DB-1 importer 연결을 구현했다.
- 데이터 검증: Small(1/10/2)에서 case revision 100개씩 총 1,003개, Medium(20/2,000/100) 총 2,120개, Large(100/20,000/0) 총 20,100개 revision을 실제 생성했다. 전체 DB integrity/foreign key·revision hash·본문 1/10/100 KiB·JSON 투영 일치·manifest fingerprint를 확인했다. Large는 기본 revision 1개이며 전체 Large×100은 미실행이다.
- 실제 k6: v2.3.0/macOS의 격리 Small depth100에서 7개 HTTP 요청, VU 1, 오류율 0, threshold 통과, summary→raw→bundle schema 통과, 전후 fingerprint 일치와 서버 종료를 확인했다. 주 에이전트도 새 Small depth3에서 독립 probe를 통과했다.
- 검증: 신규 Python 8개, 주 에이전트 전체 Python 349개(skip 0, 162.468초), frontend 45개·build, Node summary 시작시각 회귀 테스트, `git diff --check` 통과. 생성기·메타데이터 최종 변경은 관련 8개와 실제 probe로 재확인했다.
- 실패/해소: sandbox loopback bind는 해당 검증 명령의 권한 확장으로 해소했다. 실제 k6가 summary 컨텍스트에서 모듈을 다시 초기화해 raw가 시작 시각보다 앞서는 문제는 launcher의 `STUDIO_STARTED_AT` 전달로 수정했다. 1.1초 gauge 대기로 짧은 실행의 실제 VU 1을 기록한다.
- 판정: LT-1 로컬 준비 완료. 같은 호스트 SQLite 연결 검증이며 처리량/SLO 기준선이 아니다. Windows·운영 부하·장시간 시나리오·서버 자원 시계열·저장 경합·`/api/run` 용량은 후속 범위다. [사용 명령](load-test-harness.md), [측정 기록](load-test-lt1-validation.json).
- Git/다음: `feature/load-test-harness` 미커밋 상태. 커밋·푸시·병합·브랜치 삭제 없음. 다음은 LT-2 Smoke와 읽기 Baseline 스크립트다.


## LT-1 시작 (2026-09-29)

- 시작: 최신 `develop`의 DB-1~DB-5 완료 상태에서 `feature/load-test-harness`로 LT-1을 시작했다.
- 범위: Small·Medium·Large 전용 fixture, 1/10/100 KiB 본문과 최대 100 case revision, 격리 SQLite·JSON 투영·로그, k6 실행 metadata와 원본→summary→bundle 연결.
- 완료 기준: fixture 건수·크기·리비전·투영 정합성을 검증하고 짧은 1 VU 하네스 검증 명령을 재현한다. LT-2~LT-5 장시간 시나리오·용량 판정과 운영 대상 부하는 후속 범위다.
- 확인: 현재 PATH에 k6 binary가 없으며 실제 k6 실행 가능 환경을 확인 중이다. Git 커밋·푸시·병합·삭제는 수행하지 않는다.


## DB-2~DB-5 develop 통합·원격 반영 (2026-09-29)

- 시작: 사용자 요청으로 `feature/load-test-operations`의 DB-2~DB-5 변경을 커밋하고 `origin/develop`에 통합·푸시한다. 선행 DB-2~DB-4 변경을 포함하며 브랜치는 삭제하지 않는다.
- 원격 확인: `git fetch origin` 후 기능 브랜치 기준과 `origin/develop`이 모두 `6fe85d2`여서 추가 선행 변경은 없다.
- 검증: 게시 전 전체 Python 341개(skip 0, 46.170초), 프런트엔드 45개, production build·생성 코드 검사가 통과했다. 새 생성 라우터의 EOF 빈 줄을 형식만 보완한 뒤 생성 정합성·스테이징 공백 검사도 통과했다.
- 반영: 기능 커밋 `99b7821`을 `origin/feature/load-test-operations`에 푸시하고 로컬·원격 일치를 확인했다. 해당 커밋을 충돌 없이 `develop`에 통합하며, 이 기록을 포함한 merge commit의 게시 대상은 `origin/develop`이다. 병합 과정의 제품 코드는 검증된 기능 커밋과 동일하고 두 진행 문서만 통합 상태로 갱신했다.
- 상태 기준: 아래 단계별 미커밋 기록은 당시 이력이다. 현재 통합 브랜치는 `develop`이며 최종 merge commit과 원격 일치는 Git 이력·refs에서 확인한다. 기능 브랜치와 기존 브랜치는 삭제하지 않는다.

## DB-5 운영 보강 완료 (2026-09-29)

- 시작: `feature/load-test-operations`에서 선행 DB-2~DB-4 미커밋 변경을 보존하고 SQL series 축소·응답 크기 예산·보존 preview/apply·격리 백업/복원·실제 HTTP API 성능 검증을 구현한다.
- 범위: 30일 모델 20,000 run metadata, 상세 endpoint 500개/series 2,500 point 검증. 실제 LT-1~LT-5 부하 실행 및 커밋·푸시·병합·브랜치 삭제는 포함하지 않는다.
- 운영 경계: 기존 DB 정리·백업은 owner/admin만 허용하고 복원은 명시한 trusted context로 새 격리 DB만 생성한다. 종료 시각 기준 기본 30일 보존, manifest 해시로 명시 적용하며 stale preview는 거부한다. DB 4개 테이블은 같은 transaction에서 정리하고 원본 artifact는 승인된 root에서 별도 preview/apply로 처리한다. 새 격리 DB에만 복원한다.
- 의미 있는 변경: SQL window/group series 축소·consistent read snapshot·실제 UTF-8 1 MiB GET 응답 예산을 적용했다. 종료 시각 기준 30일 preview와 원본 DB identity/4개 테이블 hash를 검증하는 owner/admin 명시 apply, private quarantine 원본 파일 정리, checksum/schema/workspace를 검증하는 새 격리 DB portable 복원을 구현했다. 기존 4 MiB bundle과 12,000-point legacy 결과의 완전 백업을 유지한다.
- 중간 검증: DB-5 운영 SQLite/ASGI 15개 통과(12.072초), 선행 저장소/importer 21개 독립 통과, 실제 SQLite/PostgreSQL HTTP 각 180건·동시성 8·오류 0. 목록 p95 10.524/24.898ms, 상세 p95 53.287/31.595ms, series p95 65.110/32.338ms로 조회 기준을 만족했다. 결과 범위·본문 크기는 [측정 JSON](load-test-db5-benchmark.json)에 기록한다.
- CLI 검증: 격리 임시 DB에서 backup→DB/artifact preview→artifact apply→DB apply→새 DB restore를 실제 subprocess 명령으로 수행했다. run 1건·원본 파일 1개 정리, 복원 1건의 summary와 전체 series 원본 일치를 확인했다. 사용자 데이터는 사용하지 않았다.
- 검증 실패/보완: 첫 운영 테스트 2건은 Unicode fixture가 예산보다 작았던 기대값과 기존 local bootstrap 범위를 잘못 단언한 테스트를 수정해 통과했다. OpenAPI 수정 직후 생성 `--check` 차이는 owning generator 재생성 후 통과했다. 첫 전체 Python 341개 중 PostgreSQL 복원 guard 2건에서 `%` SQL문자와 parameter 문법 충돌을 발견해 문자 없는 `LEFT(...,3)` 접두사 비교로 수정한 후 최종 전체 재검증에서 모두 통과했다.
- 제한: 원본 파일 삭제는 POSIX no-follow descriptor에서만 제공하고 Windows는 명시적으로 거부한다. filesystem은 SQL과 별도이며 writer 중지·private quarantine 복구 절차가 필요하다. portable 백업은 정규화 결과 전용이며 전체 Studio/identity/artifact 백업은 별도다. 실제 LT-1~LT-5·production·전체 20,000건 상세 저장 용량 검증은 포함하지 않는다.
- 최종 독립 검증: `.venv/bin/python -m unittest discover -s tests -v` 341개 전부 통과(skip 0, 46.820초). PostgreSQL SQL 축소·stale retention·4개 테이블 정리·portable 복원·다른 사용자 schema 보호 2개 통합 테스트를 포함한다. `web/` 프런트엔드 45개(13파일), `npm run build`, 생성 코드 `--check`, `git diff --check` 통과. DB-5 React 코드 변경은 없으며 표시 계약·수치·unknown/p95 의미를 유지한다.
- 완료: DB-5 로컬 구현·독립 검증 완료. DB-1~DB-5/OBS-2 결과 대시보드 완료이며 실제 LT-1~LT-5는 대기다. `feature/load-test-operations`의 선행 DB-2~DB-4와 DB-5 모두 미커밋·미푸시·미병합이고 브랜치 삭제도 수행하지 않았다. 다음은 LT-1 k6 실행 구조·전용 fixture 준비다.



## DB-4 실행 비교 완료 (2026-09-29)

- 시작: `feature/load-test-comparison`에서 DB-2·DB-3 선행 미커밋 변경을 보존하고 실행 비교를 구현한다.
- 범위: 같은 프로젝트·시나리오 이전 실행 추천, 기준·비교 URL 상태, 지표와 endpoint 증감·악화순 정렬, 경과 시간 정렬 추이, 임시 기준·사용자 threshold, 조건 불일치 경고.
- 검증 계획: golden 수치·0 기준·신규/제거 endpoint·추천 시간/tie·workspace 경계·추이 정렬·비동기 선택 경합 테스트, frontend build 및 주 에이전트 독립 브라우저 검증.
- 제한: DB-5 보존·운영 성능·실제 LT 부하 실행과 Git 게시 작업은 범위 밖이다. 실제 브라우저 증거 확보 전 완료로 표시하지 않는다.
- 의미 있는 변경: `/load-tests/compare` 기준·비교 URL과 이전 실행 추천을 추가했다. 저장소에서 candidate 이전 `(startedAt,id)` 순서·workspace 경계를 보장하고 summary 7개 지표, endpoint p95 악화순·%p/상대% 구분, 조건 경고·버전 참고정보, 경과 시간 정렬 6개 추이와 동등한 표를 구현했다.
- 기준 처리: 허용치 0의 수치 악화 후보를 표시하되 0 기준·신규/제거 endpoint는 판정 불가다. 임시 기준은 Target/read/write/비예상 오류 등의 적용 의미가 현재 bundle에 없어 참고용·판정 불가로 표시하고 실제 사용자 threshold와 함께 제공한다.
- 중간 검증: frontend 44개(13파일), production build, 저장소/API·importer Python 21개, 생성 코드 `--check` 통과. 새 테스트의 중복 text query와 synthetic endpoint 요청 합계·commit 형식 오류를 수정한 뒤 통과했다. 당시 독립 검증 대기로 완료 판정을 보류했으며, 최신 판정은 아래 DB-4 최종 검증·완료 기록을 따른다.


## DB-3 결과 목록·상세 대시보드 완료 (2026-09-28)

- 시작: `feature/load-test-dashboard`에서 `/load-tests` 목록과 `/load-tests/results?run=...` 상세 화면을 구현한다. DB-2 결과 API를 사용하며 DB-4 비교 UI와 실제 LT 실행, 커밋·푸시·병합은 범위 밖이다.
- 예정 파일·검증: React 라우터·상단 메뉴·전용 화면과 스타일·테스트, 결과 사용 문서. URL 필터·cursor, KPI·표·접근 가능한 추이 차트, 로딩·빈 결과·오류·부분 데이터·모바일 상태를 검증하고 `npm test`, `npm run build`, 실제 브라우저 확인을 수행한다.
- 의미 있는 변경: 목록 필터·cursor와 상세 run을 URL에 보존하고, 요약 KPI·threshold/endpoint/환경 표, 6개 지표 SVG 추이와 동등한 데이터 표, 경고 및 부분 오류 상태를 구현했다. 최신 같은 시나리오 단순 차이에 비교 조건 미검증 주의를 표시하고 축소 p95 상한 규칙을 설명한다.
- 중간 검증: 타깃 React/라우터 7개, 전체 프런트엔드 34개(11파일), `npm run build`, `git diff --check` 통과. 추가 테스트 첫 실행에서 프로젝트 datalist 내부 label 연결 실패 1건을 발견해 `htmlFor`/`id`로 수정하고 재실행에서 모두 통과했다. 실제 브라우저 검증을 이어서 진행한다.
- 브라우저 중간 검증: 임시 격리 데이터 26개 실행에서 첫 페이지 20건→다음 페이지 6건 이동과 데스크톱 가로 넘침 없음을 확인했다. 목록의 최근 변화 안내에서 내부 단계명을 제거하고 사용자 판단 안내로 바꿨다. 상세·모바일·키보드 검증은 계속 진행한다.
- 접근성 보완·검증 (2026-09-28): 목록·시간 추이·threshold·endpoint 표의 가로 스크롤 영역에 `tabIndex=0`, 이름 있는 region과 초점 표시를 추가했다. 상세 표 3종의 키보드 초점을 확인하는 테스트를 포함해 전체 프런트엔드 35개(11파일), build, diff check 통과. 최종 브라우저·전체 Python 검증은 주 에이전트가 진행한다.
- 최종 검증: 전체 Python 322개(skip 0, 16.635초), 프런트엔드 35개(11파일), production build 통과. 실제 브라우저에서 20건→6건 cursor 이동, 프로젝트·상태·UTC 날짜 필터, 상세 새로고침·뒤로 가기의 URL 보존, KPI·실패 threshold·endpoint 값, CPU·메모리 미수집 표시, 존재하지 않는 실행의 오류·재시도·목록 복귀를 확인했다. 콘솔 오류·경고 없음.
- 모바일·키보드: 390px 화면의 페이지 scrollWidth 375px로 가로 넘침 없음. 시간 추이 표의 키보드 초점·테두리와 ArrowRight 스크롤 0→40px, endpoint·목록 스크롤 영역의 초점을 실제 브라우저에서 확인했다.
- 환경 참고: IAB 날짜 달력 팝업 클릭 중 호스트 탭이 종료되어 새 탭에서 native 날짜 입력·URL 새로고침으로 복구 검증했다. 애플리케이션 JavaScript 오류는 없었으며 제품 결함으로 분류하지 않았다.
- 완료: DB-3 로컬 구현·검증 완료. `feature/load-test-dashboard`에 선행 DB-2 미커밋 변경을 그대로 이어받았고 DB-3 변경도 미커밋이다. 커밋·푸시·병합·삭제는 수행하지 않았다. 다음은 DB-4 실행 비교이며 DB-5 운영 보강과 LT 실제 부하 실행은 후속 범위다.
- 최종 정리: 주 에이전트 독립 재실행의 프런트엔드 35개와 생성 코드 `--check`가 통과했다. 임시 QA 서버를 정상 종료하고 브라우저 QA 탭·viewport를 정리했다. 사용자 데이터는 사용하지 않았다.

## DB-2 저장소·조회 API 완료 (2026-09-27)

- 시작: `feature/load-test-storage`에서 전용 SQLite/PostgreSQL migration, 원자적 bundle 저장, 목록·상세·시계열·비교 API를 구현한다. DB-3 화면과 LT 실행, 커밋·푸시·병합은 범위 밖이다.
- 예정 파일: `api_test/migrations.py`, `api_test/load_test_store.py`, API 라우트·계약, PostgreSQL 이관, 관련 테스트와 사용 문서. 2만 건 목록 조회 계획·시간 및 SQLite 문서 쓰기 경합을 검증한다.
- 의미 있는 변경: schema v4에 결과 전용 4개 테이블과 목록·series 인덱스를 추가하고, 허용 필드만 저장하는 repository와 keyset cursor 목록·상세·시계열 축소·비교 API를 OpenAPI 생성 라우트에 연결했다. 4 MiB 전송 상한과 workspace 권한 경계를 적용했다.
- 중간 검증: 고정 Smoke bundle 직접 저장·조회와 ASGI POST/GET 정상 흐름, DB-2 저장소/API 테스트 7개 통과. 2만 건 목록은 지정 인덱스 계획을 사용했고 p95 500 ms 단언을 통과했다. PostgreSQL·전체 회귀는 이어서 확인한다.
- 최종 변경: PostgreSQL 이관에 결과 4개 테이블을 포함하고, 중복 동시 등록·자식 INSERT 실패 원자 rollback·workspace 분리·문서 쓰기 경합을 테스트했다. 비교 결과에는 endpoint별 p95·오류율 변화와 p95 악화순 목록이 포함된다. `docs/load-test-results.md`에 업로드·조회·축소 규칙을 기록했다.
- 검증: DB-2 SQLite/ASGI 9개, PostgreSQL 저장·SQLite snapshot 이관 2개, migration 4개, 전체 Python 322개(skip 0) 통과. 실제 Uvicorn loopback POST→목록→상세→series·중복 409 검증, OpenAPI 생성 `--check`와 `git diff --check` 통과. 2만 run metadata의 SQLite 목록은 `load_test_runs_project_started` 인덱스를 사용했고 20회 측정 p95 0.6 ms(로컬 임시 DB)였다. 최초 전체 3건 실패는 migration 버전·경로 allowlist의 오래된 테스트 기대값으로 확인해 갱신한 뒤 재실행에서 통과했다.
- 완료: DB-2 로컬 코드·검증 완료. DB-3 화면, DB-4 자동 추천·판정 UI, DB-5 보존·운영 보강과 실제 LT 실행은 후속 범위다.

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

## DB-4 최종 검증·완료 (2026-09-29)

- GPT-6 Sol high 구현 후 주 에이전트가 전체 Python 324개(skip 0, 17.295초), 프런트엔드 45개(13파일), production build, 생성 코드 `--check`, `git diff --check` 통과를 확인했다. 마지막 보완은 기록된 VU 0을 미수집으로 표시하지 않는 회귀 수정이다.
- 실제 브라우저: candidate 직전 실행 추천(더 최신 실행 제외), p95 +38.5 ms/+20%, 오류율 +25 %p/+100%, POST +39 ms → GET +29 ms 악화순, 0·5초 추이 정렬, 조건 경고와 사용자 threshold를 확인했다. 목록→상세→비교, 새로고침·뒤로 가기, 시나리오 불일치 거부와 추천 없음 안내도 통과했다.
- 390px 화면에서 페이지 너비 375px, 표의 키보드 초점과 방향키 스크롤 0→40px, 콘솔 오류·경고 없음을 확인했다. 임시 검증 서버 정상 종료, 탭 정리와 viewport 복원을 완료했다.
- 판정: DB-4 로컬 구현·검증 완료. 표시하는 회귀 후보는 수치 악화이며 통계적 유의성 판정이 아니다. 적용 의미가 없는 임시 SLO는 참고용·판정 불가로 유지한다.
- Git: `feature/load-test-comparison`에 DB-2·DB-3 선행 변경을 보존한 미커밋 상태. 커밋·푸시·병합 없음. 다음 DB-5 운영 보강과 실제 LT 실행은 후속 범위다.

## 현재 요약

- 최종 갱신일: 2026-10-01
- 현재 단계: DB-1~DB-5/LT-1~LT-5 로컬 도구·잠정 보고서 완료; 전체 캠페인/SLO 미완료·실패/unknown 보존
- 전체 상태: 진행
- 반영 브랜치: 로컬 `develop` (LT-1~LT-5와 최신 OBS-1 통합); 원격 게시 승인 대기
- 다음 작업: 보고서 P0 실행 정책 검토 → P1 동일 조건3회 기준선·회복 원인 분리

상태는 `대기`, `진행`, `완료`, `차단` 중 하나만 사용한다. 완료 기준과 검증을 충족하기 전에는 `완료`로 변경하지 않는다.

## 단계별 현황

| ID | 작업 | 상태 | 완료 기준 | 관련 변경 또는 결과 |
| --- | --- | --- | --- | --- |
| LT-1 | k6 실행 구조와 전용 fixture 준비 | 완료 | Small·Medium·Large fixture와 재현 가능한 실행 명령 준비 | 전체 건수·본문·투영 검증, Small depth100·실제 k6 7요청·VU1·오류0·bundle·종료 통과 |
| LT-2 | Smoke와 읽기 Baseline 스크립트 | 완료 | 응답 검증과 클라이언트 지표 출력 확인 | 기본60초/300초·요청214/754·오류0·7endpoint·bundle·종료, Python354·Node 회귀 통과 |
| LT-3 | Target 혼합 및 저장 경합 시나리오 | 완료 | 혼합 비율, 고유 저장, 예상 `409` 검증 | 로컬 구현/기능 검증 완료; unique50·경합5/20/50 통과, Target20VU429 실패·50/전체20분 미검증 |
| LT-4 | Stress·Spike·Soak 및 `/api/run` 시험 | 완료 | 중단 조건과 회복 측정을 포함한 결과 생성 | 로컬 bounded구현·축소 결과 완료; Spike/50VUStress회복 실패·Soakunknown·관측admission2·fullcampaign 미검증 |
| LT-5 | 기준선 보고서 | 완료 | 최대 안정 RPS, 안정 동시 실행 수, 병목 기록 | 잠정 보고서/재현 완료; maximum/sustained/median null·관측2·실패/unknown·후속 기준 명시; 전체캠페인 미완료 |
| DB-1 | 결과 schema와 importer | 완료 | 고정 fixture의 집계값과 importer 결과 일치 | 단위 10개·전체 Python 310개·helper·생성·diff 검사 통과 |
| DB-2 | 저장소와 결과 조회 API | 완료 | migration, atomic import, 목록·상세·series API 테스트 통과 | 전체 Python 322개·실 HTTP·생성·diff 검사 통과, 2만 건 목록 p95 0.6 ms |
| DB-3 | 결과 목록과 상세 대시보드 | 완료 | 필터, KPI, 표, 차트와 상태 화면 구현 | Python 322개·프런트엔드 35개·build, 실제 브라우저 URL·수치·390px·키보드·오류 복구 검증 통과 |
| DB-4 | 실행 비교와 regression 판정 | 완료 | 기준 대비 증감률과 endpoint 악화 순위 검증 | Python 324개·프런트엔드 45개·build·생성·실제 브라우저 수치·URL·390px·키보드 검증 통과 |
| DB-5 | 성능·보존·문서 운영 보강 | 완료 | 예상 데이터 규모의 성능 및 정리·복구 검증 | Python 341개·frontend 45개/build·양 backend HTTP·CLI 보존/복원·생성/diff 통과; 로컬/POSIX 범위와 metadata 모델 명시 |

## 현재 작업

진행 중인 작업이 생기면 아래 항목을 갱신한다. 동시에 여러 작업을 수행할 때는 각각 구분해서 작성한다.

- 작업 ID: LT-5
- 목표: 실제 evidence의 기준선·용량·병목·SLO coverage와 우선 후속 보고서
- 변경 파일: `api_test/load_test_report.py`, `tests/test_load_test_report.py`, 생성 보고서/summary, README·사용 문서·LT-4 PID evidence 보강·두 진행 기록
- 시작 시각: 2026-09-29
- 상태: 완료 (보고서/재현; 신규9개·전체382·독립raw/repro/adversarial 검증 통과)
- 확인이 필요한 사항: 최대안정RPS·sustained동시성·fullcampaign/SLO는미확정이며 보고서 완료와 분리한다.

## 검증 기록

실행한 명령과 결과를 생략하지 않는다. 실패한 검증도 원인과 후속 조치가 추적되도록 남긴다.

| 일시 | 작업 ID | 명령 또는 확인 방법 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| 2026-09-29 | DB-5 | `.venv/bin/python -m unittest discover -s tests -v` (수정 후 독립 재실행) | 통과 | 341개, skip 0, 46.820초; PG guard·복원·정리 포함 |
| 2026-09-29 | DB-5 | `web/`의 `npm test`, `npm run build`, generator `--check`, `git diff --check` | 통과 | frontend 45개/13파일; 생성 최신; React DB-5 수정 없음 |
| 2026-09-29 | DB-5 | 실제 Uvicorn HTTP `.venv/bin/python -m api_test.load_test_benchmark --requests 60 --concurrency 8` 및 `--postgres` | 통과 | 각 180건/오류 0; SQLite 목록/상세 p95 10.524/53.287ms, PG 24.898/31.595ms; metadata 20,000 + 상세 1건(500 endpoint/2,500 series) |
| 2026-09-29 | DB-5 | 격리 CLI backup→DB/artifact preview→artifact apply→DB apply→new DB restore | 통과 | run 1건/파일 1개; summary·전체 series 복원 원본 일치; 사용자 데이터 비사용 |
| 2026-09-29 | DB-5 | 첫 전체 Python 341개 검증 | 실패 후 해소 | PostgreSQL 2건 guard SQL `%` literal/parameter 충돌; `LEFT(...,3)` 접두사 비교로 수정 후 전체 통과 |
| 2026-09-29 | DB-5 | 운영 SQLite/ASGI 15개, wrong-source DB·stale·rollback·symlink·quarantine 교체·backup checksum·12,000-point legacy·UTF-8 예산 | 통과 | 12.072초; 명시 적용과 새 격리 복원 경계 확인 |
| 2026-09-29 | DB-4 | 최종 증거 확인·진행 기록 동기화 | 통과 | Python 324개, 프런트엔드 45개, build·생성·diff 검사 및 실제 브라우저 비교 수치·URL·390px·키보드 검증 완료 |
| 2026-09-28 | DB-3 | 주 에이전트 독립 `cd web && npm test`, 생성 코드 `--check`, `git diff --check` | 통과 | 프런트엔드 35개·생성 코드 최신. 임시 QA 서버 정상 종료·브라우저 정리 |
| 2026-09-28 | DB-3 | `.venv/bin/python -m unittest discover -s tests -v` | 통과 | 322개, skip 0, 16.635초 |
| 2026-09-28 | DB-3 | 실제 브라우저 목록·상세·URL·오류 상태 확인 | 통과 | 26개 격리 fixture, 20→6 페이지, 필터·reload·back, KPI·threshold·endpoint 수치, missing run 복구, 콘솔 오류·경고 없음 |
| 2026-09-28 | DB-3 | 390px 화면·표 키보드 스크롤 | 통과 | 페이지 375px, series ArrowRight 0→40px, 초점 테두리·endpoint·목록 region 초점 |
| 2026-09-28 | DB-3 | IAB 날짜 팝업 후 새 탭 native 날짜 입력·reload | 복구 검증 통과 | 호스트 탭 종료는 도구 환경 문제. native 입력·필터 URL 보존 통과 |
| 2026-09-28 | DB-3 | `cd web && npm test`, `npm run build`, `git diff --check` | 통과 | 표 스크롤 초점 접근성 테스트 포함 35개, production build 및 공백 검사 |
| 2026-09-27 | DB-3 | `cd web && npm test` (추가 테스트 첫 실행) | 실패 | 34개 중 1개: datalist 내부 프로젝트 label 연계 실패. 명시적인 `htmlFor`/`id`로 수정 |
| 2026-09-27 | DB-3 | `cd web && npm test` (최종 재실행) | 통과 | 11개 파일, 34개 테스트 |
| 2026-09-27 | DB-3 | `cd web && npm run build` | 통과 | Vite production build |
| 2026-09-27 | DB-3 | `git diff --check` | 통과 | 1차 공백 검사 |
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

### 2026-09-29 — DB-5 운영 보강 완료

- 변경: SQL bounded series와 GET 1 MiB 본문 예산, source/workspace/hash에 묶인 retention manifest, 승인 root의 private quarantine artifact 정리, 결과 JSONL 백업·새 격리 SQLite/빈 PostgreSQL 복원, 실제 HTTP benchmark를 추가했다. 전체 결과 요약·endpoint·원본 series는 보존한다.
- 검증: Python 341개(skip 0, 46.820초), frontend 45개/build·생성·diff, 격리 CLI 및 SQLite/PostgreSQL HTTP 각 180건·오류 0 통과. 첫 전체 PG guard 2건 실패는 접두사 SQL 수정 후 재검증에서 해소했다. [측정 결과](load-test-db5-benchmark.json).
- 범위·다음: 로컬 metadata 20,000 + 상세 1건의 모델, POSIX 원본 정리·정규화 결과 전용 백업. DB-1~DB-5 완료, 실제 LT-1~LT-5 대기. 다음은 LT-1 fixture/k6 실행 구조다. `feature/load-test-operations` 미커밋·미푸시·미병합.

### 2026-09-28 — DB-3 — 결과 목록·상세 대시보드 완료

- 변경: 새 라우트와 상단 메뉴, URL 필터·cursor·run, KPI·threshold·endpoint·환경·경고, SVG 추이와 동등한 표, 상태 화면과 표 키보드 초점을 구현했다.
- 검증: Python 322개(skip 0), 프런트엔드 35개와 build, 실제 브라우저 필터·페이지·수치·URL·오류 복구·390px·키보드 확인 통과.
- Git·제한: DB-2 선행 미커밋 변경을 보존한 `feature/load-test-dashboard` 미커밋 작업 트리. 비교 UI·회귀 판정·보존 운영 및 실제 LT 실행은 이번 완료 범위 밖이다.
- 다음: DB-4 실행 비교와 regression 판정.

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
