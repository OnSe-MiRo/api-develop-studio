# API 부하테스트 및 대시보드 개발 진행 기록

## 예상 오류 경로 보완 후 사전 35 VU 진단 (2026-11-09)

- 두 번째 120초 진단은 부하·정리·무결성을 통과했고 스레드 평균 2.3846→2.6154로 회복 120% 기준을 통과했다. p95·오류율·CPU·RSS·핸들·자식 수 회복도 통과했다. 각 phase 종료 census는 MainThread만 기록했다.
- 축소 시험의 장시간 안정성 판정은 unknown이며, 이 결과로 2시간 검증을 대체하지 않는다. 정규 시험은 동일한 worker·payload·HTTP timeout·중단·회복 조건으로 수행한다.

## 예상 충돌 오류 응답의 별도 AnyIO 스레드 회수 (2026-11-09)

- 요청 풀만 바꾼 첫 120초 진단에서는 스레드가 2.23→3.69로 여전히 기준을 넘었다. 정상 HTTP burst 뒤 예상 409를 한 번 발생시키는 회귀에서 별도 AnyIO worker 1개가 남는 것을 재현했다.
- I/O 없이 JSON만 만드는 공통 오류 응답 handler를 async로 등록했다. 정상·오류 요청 모두 앱의 요청 worker 수명주기를 따르며, 실제 HTTP에서 409 payload·Workspace 문맥과 유휴 회수를 확인했다.
- 종료 시 mock 정리 실패가 있어도 job과 요청 풀을 닫는 순서를 적용했다. 진단 전용 loopback 공급자에는 Python 스레드 이름·native ID 관측을 추가했다. P1의 과거 v1/v2 지문과 새 v3 지문을 구분한다.

## 유휴 요청 스레드 회수 재현과 수정 (2026-11-09)

- 실제 HTTP 요청 6개를 동시 처리한 뒤 작업이 끝나도 AnyIO 요청 스레드 6개가 남는 회귀를 재현했다. 별도 기본 호출 재현에서도 11초 유휴 뒤 6개가 살아 있었다. 요청 도착 시에만 수행되는 AnyIO 유휴 정리 경로를 확인했다.
- 앱별 요청 풀은 최대 40개 worker·대기 작업 40개와 기존 AnyIO 호출 admission을 사용하고, 작업이 없는 worker를 1초 뒤 종료한다. 요청마다 인증 ContextVar를 복사하고, 취소된 호출도 실행이 종료될 때까지 admission을 유지한다. 앱 종료는 요청 풀을 닫고 작업 완료를 기다린다.
- 실제 HTTP Workspace 문맥·유휴 회수 회귀, 최대 실행 수·예외·취소·재시작·종료·시작 실패 롤백 회귀 4개가 통과했다. 실행 작업용 슬롯과 과부하 기준은 기존 설정을 사용한다.

## 스레드 회복 실패 수정 착수 (2026-11-09)

- `develop 654515d`의 이전 결과에서 사후 5분 읽기 p95·CPU·메모리는 통과했고 평균 스레드 2.58→4.00만 120% 기준을 넘었다. 원래 자원 표본과 Python 스레드 이름·수명으로 실제 미회수 자원을 재현한다.
- 수정한 같은 커밋에서 기본 35 VU·7,200초와 같은 서버 전후 300초를 재측정하고 모든 실패·정리·무결성을 기록한다. 검증 후 커밋·develop 병합·원격 푸시한다.

## 전체 목록 최적화·35 VU와 사후 5분 결과 확인 (2026-11-07)

- 고정 후보 `8f28e9a`의 정규 Target과 35 VU·2시간 부하를 완주했다. 동기 실행은 각각 1,166건·7,073건 모두 200·고유 성공 Run ID였고 429는 0건이었다. 모든 phase의 원본·리비전·투영 무결성 및 자식·임시 파일 정리가 통과했다.
- 사후 5분 읽기 p95 17.90525→16.08575ms, CPU 0.179216→0.160518%, RSS 43.31→45.23 MiB는 120% 기준을 통과했다. 평균 스레드 2.58→4.00은 실패해 캠페인 종합 판정은 `failed`, 장기 안정성은 `unknown`으로 기록한다.
- 같은 초기/성장 데이터의 실제 HTTP 응답 60쌍씩이 byte 단위로 일치했다. 프로젝트별 반복 조회 중앙값은 초기 16.77→2.67ms, 성장 후 48.19→6.71ms였다. 최초 전체 조회 단일 샘플은 초기 334.57→353.44ms, 성장 후 882.66→884.33ms였다. [검증 보고서](case-list-recovery.md) · [측정 수치](case-list-recovery.json)

## 정규 Target 통과·35 VU Soak 시작 (2026-11-07)

- 같은 `8f28e9a`에서 20 VU 600초→50 VU 600초를 완주했다. 전체 HTTP 23,750건 중 동기 실행 1,166건 전부 200, 고유 성공 Run ID 1,166개, 예상 충돌 992건, 예기치 않은 오류·실행 실패 0건, 사후 무결성 통과다.
- 새 Medium 스냅샷의 사전 5분 읽기 기준선이 통과했다. p95 17.90525ms, CPU 0.179216%를 같은 서버의 사후 값과 비교한다. 장시간 profile은 기본 35명·7,200초를 사용한다.

## 고정 커밋의 HTTP 응답 및 P1 읽기 실측 (2026-11-07)

- `8f28e9a`와 `ef0764c`를 같은 Medium 데이터로 비교했다. 20개 프로젝트 60쌍의 실 HTTP 응답이 byte 단위로 동일했다. 기준→후보 반복 조회 중앙값 16.77→2.67ms, p95 19.28→3.68ms였다. 필터 없는 2,000건 최초 조회 단일 관측은 334.57→353.44ms, 캐시가 채워진 뒤 두 차례는 295.07→14.62ms와 271.50→10.30ms였다.
- 25초 P1 진단 3회와 예열에서 `/api/cases` 40건·참조 4,000개를 계측했다. 실제 JSON 읽기는 1,000개였고 30개 요청의 파일 내용 읽기는 0회였다. 이 결과는 진단용 축소 실행이며 정규 부하 수치는 별도로 기록한다.

## 최종 후보 고정·백엔드 전체 회귀 (2026-11-07)

- `8f28e9a`에서 실제 전용 PostgreSQL·Redis와 loopback을 포함한 Python 730개가 103.443초에 통과했다. 기존 28개 소스 지문의 기준선 보고서와 회복 보고서도 현재 코드에서 재현됐다.
- 동일 Medium 스냅샷의 기존/수정 HTTP 응답과 성능, P1 계측, 기본 20→50 VU 및 35 VU·2시간·사후 5분 회복을 별도 순서로 측정한다. 실제 측정은 고정 checkout, 온전한 workload와 기존 중단 기준을 사용한다.

## 기존 P1 기준선 보고서 재현 보완 (2026-11-07)

- URL 요약을 계산하는 새 소스를 P1 지문에 포함한 첫 후보에서, 기존 28개 파일로 측정한 보존 보고서의 `render --check`가 실패했다. 새 측정은 source manifest v2 전체를 요구하고, 버전 필드가 없는 과거 결과는 원래 v1 지문 집합으로 검증하도록 분리했다.
- 기존 기준선·회복 보고서의 재생성 검사와 P1 회귀 10개가 통과했고, v2에서 새 파일 지문을 누락하면 비교를 거절하는 것을 확인했다.

## 전체 케이스 조회의 반복 파일 읽기 개선·사전 점검 (2026-11-07)

- 원래 경로에서 같은 목록을 다시 조회해도 JSON 2개를 모두 여는 회귀를 재현했다. POSIX SQLite에서는 검증된 일반 파일의 공개 URL을 파일 버전에 묶어 재사용하며, 각 요청의 DB 권한·Workspace·프로젝트 조회와 파일 변경 감지를 유지한다. 긴 URL·민감 URL·별칭·최근 변경은 직접 읽는다.
- 진행 중인 후보의 실제 Medium HTTP 사전 비교에서 20개 프로젝트 60쌍의 응답이 바이트 단위로 일치했다. 반복 프로젝트 목록 중앙값은 16.20→2.73ms였다. 전체 2,000개 두 번째 조회는 약 307→12ms였다. 커밋 고정 후 동일 기준 및 성장한 데이터로 다시 측정한다.
- 수정된 P1 계측은 실제 요약 처리 경로의 파일 열기·읽기만 기록한다. Workspace 격리·파일 교체·삭제·형식 오류·외부 직접 수정·경로 이탈·동시 교체를 회귀 범위에 포함했다.

## 전체 케이스 목록 조회와 부하 후 회복 개선 착수 (2026-11-07)

- 원격과 일치하는 `develop ef0764c`에서 분기했다. 전체 `GET /api/cases`의 `items` 순서와 `details.url`, 프로젝트 필터·Workspace 격리·기존 문서 호환성을 검증하면서 반복 조회 비용을 줄인다.
- 비교 기준은 이전 35 VU 2시간 완료 후 읽기 p95 46.89→95.94ms, CPU 0.232→0.384%, 케이스 목록 p95 62.83→138.83ms다. 합성 데이터의 전후 응답·실제 처리 비용을 대조하고 같은 기본 Soak 모델과 5분 회복 조건으로 확인한다.

## 접수 회귀 fixture 격리 확인 (2026-11-07)

- 병합 worktree에서의 사후 점검과 빈 임시 DB 재현을 통해 일부 접수 테스트가 암묵적인 기본 파이프라인에 의존한 것을 확인했다. 해당 테스트는 매번 임시 SQLite·프로젝트 경로를 사용하고 명시적 inline 케이스를 제출한다.
- 격리한 접수 회귀 8개와 전체 Python 724개(101.135초)가 통과했다. 부하 검증 제품 커밋은 `b83e3f5`이며, 20→50 VU 3회·35 VU 2시간의 측정/회복 판정은 [검증 보고서](sync-run-admission-validation.md)에 있다.

## 동기 실행 429 수정·최종 부하 재검증 완료 (2026-11-07)

- 후보 `b83e3f5`의 20→50 VU 정규 Target 3회(총 HTTP 71,057건·동기 3,491건)와 35 VU 2시간 부하 구간(HTTP 142,344건·동기 7,047건)을 완주했다. 최종 동기 요청 10,538건 모두 200·서로 다른 성공 Run ID·exit 0이며 429는 0건이었다. 원본 fixture와 모든 완료 실행의 DB/투영 무결성을 확인했다.
- Soak 사후 회복은 읽기 p95 46.89→95.94ms, CPU 0.232→0.384%로 120% 기준을 넘었다. 오류·RSS·스레드·핸들·자식 정리는 통과했다. 부하 구간 통과와 별도로 캠페인 종합 판정은 실패로 남긴다. 케이스 목록 p95는 62.83→138.83ms였다. 같은 사후 파일에서 참조 수만 바꾼 60쌍의 목록 요약 처리 시간 중앙값이 16.06→45.97ms였다.
- 전체 Python 724개·프런트엔드 169개·build·생성 및 k6 모델 회귀 통과. Windows는 요청대로 보류했다. [측정·실패 기록 및 재현](sync-run-admission-validation.md) · [수치와 원본 식별자](sync-run-admission-validation.json).

## 최종 후보 35 VU 2시간 profile 완주 (2026-11-07)

- 기본 35 VU·7,200초를 중단 없이 실행했다. 전체 142,344건(200 136,640건, 예상 409 5,704건) 중 동기 run은 7,047건, run 429·실행 종료 실패는 0건이었다. 부하 구간 전체 p95 112.53ms, 수집된 1,425개 서버 표본의 자식 프로세스 최댓값 2였다. 종료 후 고아 자식·임시 파일 0건 및 부하 구간 무결성을 확인했다. 사후 5분의 회복 조건은 별도로 판정한다.

## 최종 후보 20→50 VU 정규 3회 통과 (2026-11-07)

- `b83e3f5`에서 20명 10분과 50명 10분을 3회 모두 완주했다. 총 HTTP 71,057건 중 동기 실행 3,491건은 전부 200·동기 429 및 예기치 않은 오류 0건이다. 각 실행에서 고유 성공 Run ID 수와 동기 응답 수, 원본·리비전 무결성이 일치했다.
- Studio 읽기 p95 38.05·39.67·40.05ms, p99 62.69·65.94·69.70ms였다. 같은 후보에서 독립 35 VU·7,200초 profile과 전후 5분 회복을 검증한다.

## 최종 후보 자동 회귀 통과 (2026-11-07)

- `b83e3f5`의 PostgreSQL·Redis 포함 전체 Python 724개(139.210초), 프런트엔드 169개/38파일, production build 및 생성 코드·보고서 최신성·k6 모델 5개가 통과했다. 이전 후보와 동일한 k6 스크립트·fixture·시간 제한을 사용한다.
- 중간 실패와 성공을 함께 보존했다. 첫 후보 자료의 원본 56개를 압축 기록과 바이트 단위로 대조했다. 마지막 후보의 정규 부하는 각 실행 직전 별도 호스트 표본으로 안정 구간을 확인한다.

## 35 VU 재현 후 runner 시작 비용 분리 (2026-11-07)

- 첫 수정 후보 `f250a28`의 35 VU Soak는 profile 843초에 429 두 건으로 중단됐다. 거절 응답은 4.02초·4.04초, 같은 시각 완료된 요청은 최대 6.19초였다. 실행 이력상 자식 실행 시간도 1.9~3.6초에 이르렀다. 기준선 p95 46.67→178.88ms 및 CPU 회복 기준도 실패했다. 부하의 실패와 사후 무결성 통과를 따로 기록한다.
- 별도 새 Python 프로세스 회귀에서 SQLite 평문 CLI도 PostgreSQL 드라이버·Fernet을 불러오던 것을 재현했다. 사용 시점에만 로드하도록 수정했다. 같은 loopback 실제 GET을 두 버전으로 교차 실행한 12쌍의 프로세스 전체 중앙값은 3,467.28→1,595.78ms였다. 이 시점에는 8코어 호스트 부하가 매우 높았다.
- 측정된 약 5초의 슬롯 점유를 흡수하도록 동기 대기 기본값을 6초로 조정했다. 실행 슬롯 2개, 대기 인원 16개, 원래 HTTP·runner timeout과 k6 중단 조건은 유지한다. 동일하게 두 슬롯을 5.1초 점유한 재현에서 기존 후보는 4.01초에 429, 조정 후보는 5.10초에 같은 요청을 접수했다. 두 번째 후보에서 동일한 정규 Target과 35 VU Soak를 다시 평가한다. 호스트 과부하 시에는 새 측정의 시작만 미루고 진행 중인 시험 결과는 모두 보존한다.

## 독립 Target의 목록 조회 중단 (2026-11-06)

- 다음 정규 Target은 50 VU까지 도달했다. 동기 실행 626건은 모두 HTTP 200이었다. 13분대에 `GET /api/cases` 3건이 5초 안에 완료되지 않아 중단했다. 전체 HTTP 12,554건, 원본·저장 무결성 통과, 서버 종료를 확인했다.
- 같은 시각 외부 표본에서 호스트 1분 load average가 4.63→23.43으로 상승했고 약 11초 사이 swapout 페이지가 27,500개 늘었다. 실측 지연과 동시 관측한 수치로 원인 단정에는 사용하지 않는다. 독립 35 VU·2시간 Soak를 같은 후보·기본 timeout으로 시작했다.

## 정규 20→50 VU 첫 완주 (2026-11-06)

- 동기 429와 별개인 첫 timeout 기록을 보존한 뒤, 같은 후보·같은 설정의 다음 Target은 20 VU 10분·50 VU 10분을 완주했다. 총 HTTP 23,610건(예상 409 980건) 중 동기 1,160건은 전부 200, 성공 실행 이력의 고유 Run ID 1,160개, 읽기 p95 39.28ms·p99 66.68ms, 무결성 통과다. 같은 호스트에서 다른 반복 및 장시간 검증을 이어간다.

## 첫 정규 Target 중단 기록 (2026-11-06)

- 수정 후보의 첫 정규 Target이 약 5분 28초에 중단됐다. 동기 `/api/run` 184건은 모두 200이었다. 별도의 읽기·쓰기 10건이 같은 초에 5초 타임아웃을 넘겨 correctness check가 실패했다. 중단된 고유 저장 1건은 revision 1이었다. 독립 사후 검사에서 허용한 부분 저장 외의 원본 지문·리비전·투영은 일치했다.
- 이때 HTTP 완료 사이에 6.97초, 부하 발생기 1초 표본 사이에도 최대 2.85초의 공백이 있었다. 당시 원인을 단정할 동시 자원 표본은 없다. 실패 자료를 보존하고 다음 기본 시험에는 애플리케이션 호출을 추가하지 않는 외부 시계·호스트·서버 표본을 붙였다.

## 동일 후보 회귀 완료·정규 부하 시작 (2026-11-06)

- 수정 후보 `f250a28`에서 PostgreSQL·Redis를 포함한 Python 723개가 통과했다. 서버 생성·LT-5 보고서 최신성과 k6 모델 5개가 통과했다. 프런트엔드는 최초 Python과 병행한 실행에서 7건이 실패했다(6건 timeout). 백엔드 suite 종료 후 시간 제한을 유지한 채 worker 2개로 전부 다시 실행해 169개 및 production build가 통과했다. 테스트 서비스는 기존 상태로 복원했다.
- 깨끗한 후보 checkout에서 Medium 원본 SHA-256 `a83c873f2f2961b7a7e20eb7a04a8aa7c4ae5cf781385270d6dcfb49181702a9`와 이전 k6 실행 파일 지문을 고정했다. 정규 Target은 회당 20·50 VU 각 600초, 35 VU Soak는 7,200초와 같은 서버의 사전·사후 300초 기준선이다. 모든 실행은 독립 스냅샷에서 직렬 수행한다.

## 동기 실행 재현·회귀와 사전 부하 점검 (2026-11-06)

- 깨끗한 `a767652`의 정규 Target은 20 VU에서 HTTP 123건 후 종료했다. 동기 실행 9건 중 2건이 429였고 무결성은 통과했다. 단위 HTTP 회귀에서도 슬롯 두 개를 잠깐 점유하면 세 번째 요청이 즉시 끝나 실패했다.
- 동기 `/api/run`은 동일 HTTP 요청으로 기본 4초·최대 대기 16건 안에서 기존 슬롯 2개를 기다린다. 실행·응답은 한 번이며 대기 인원 또는 시간 초과는 기존 429, 종료 중 대기는 503이다. 서버 재전송이나 비동기 전환은 없다.
- 동시 실행 상한·순서·대기 만료·오류 뒤 해제·비동기와 공유·shutdown 회귀 확인. 자식 확인용 ps를 샌드박스가 막은 검사는 실제 로컬 환경에서 재실행했다. 90초 사전 검사에서 20→50 VU, HTTP 2,003건·동기 run 117건 전부 200·예기치 않은 오류 0건·원본 무결성 통과. 정규 시간의 검증은 별도로 수행한다.

## 동기 실행 429 수정 및 목표 부하 재검증 착수 (2026-11-06)

- 로컬 `develop`의 `a767652`에서 분기했다. 후보 `858f0e9`의 원시 k6 기록을 대조하고, 동기 `POST /api/run`의 짧은 동시 요청을 정상 진입점으로 재현한다.
- 실행 슬롯·Workspace 격리 및 중복 실행 방지를 유지하며 수정한 같은 커밋에서 Medium 기본 20→50 VU Target과 35 VU·2시간 Soak를 재검증한다. Windows 실기기는 이번 범위에서 보류한다.

## 4·5단계 최종 로컬 판정 (2026-11-06)

- 후보 `858f0e9`의 기본 Target·Stress·Spike·35 VU Soak에서 동기 run 429를 확인해 **출시 보류**로 판정했다. 세 고부하 profile 모두 중단 뒤 같은 서버의 5분 회복·무결성·정리는 통과했다. 50 VU 목표 용량과 35 VU 장시간 안정성은 미충족이다.
- 독립 2 VU 혼합 부하를 실제 2시간 실행해 HTTP 7,978건, 예기치 않은 오류 0건, p95 65.99ms를 확인했다. 사후 회복·원본 지문·리비전 검증을 통과했다. cold 반복 실행은 스레드 120% 기준에 실패했고, 별도의 worker 예열 진단은 10건 전부 성공 및 스레드 4.75→5.00으로 회복 기준에 통과했다.
- 같은 커밋의 전체 Python 718개, 프런트엔드 169개, build와 실제 브라우저 핵심 흐름을 통과했다. Windows PC는 꺼져 있어 네이티브 경로 검증을 대기로 남기고, 동일 커밋 소스 ZIP과 PowerShell 검사기를 준비했다. [전체 측정·재현 및 Windows 절차](local-release-validation.md) · [기계 판독 결과](local-release-validation.json).

## 기본 Stress·Spike·Soak 결과 (2026-11-06)

- Medium 기본 설정으로 세 profile을 모두 시작했다. 동기 run 429가 관측되어 Stress는 50 VU·10건, Spike는 관측 최대 51 VU·5건, Soak는 35 VU·6건에서 중단했다. 각 시험 뒤 같은 서버의 5 VU·5분 회복, 저장 무결성, 자식·임시 파일 정리는 모두 통과했다. 200·100 VU 도달이나 35 VU·2시간 안정성은 입증되지 않았다.
- 반복 시험에서 접수가 통과한 2 VU로 별도의 7,200초 혼합 부하 관측을 시작했다. 제품·worker 수·중단 기준은 고정하고 동시 사용자 수만 낮춘 진단이며, 기본 35 VU 출시 기준은 실패로 보존한다.

## 기준선 완료와 혼합 목표 중단 (2026-11-06)

- Medium의 5 VU·300초 읽기 3회가 모두 통과했다. 같은 서버에서 756·756·755건, 실행별 중앙값 p95 40.23225ms, 2.437861 RPS였다. Small·Large의 별도 300초 기준선도 각각 756·754건, 예상 밖 오류 0건이었다.
- 기본 Medium Target 세 번은 첫 20 VU에서 동기 run 용량 429가 2·1·2건 발생해 종료됐다. 응답은 각각 129·138·130건이었고 50 VU에 도달한 실행은 0건이다. 세 번 모두 데이터 무결성을 통과했다. 이후 시험은 독립 스냅샷에서 실행하며 중단한 단계를 통과로 집계하지 않는다.

## 수정된 후보의 Mac 회귀와 브라우저 완료 (2026-11-06)

- 후보 `858f0e9`에서 Python 718개·프런트엔드 169개·production build·생성 코드·LT-5 보고서 최신성·k6 모델 5개가 통과했다. 테스트 PostgreSQL과 Redis를 중지 상태로 복원했다.
- 같은 후보의 실제 브라우저에서 로그인 → cURL 미리보기·저장 → GET /health 200·같은 Run ID 복원 → 릴리스 원본·발행 → 포털 SDK ZIP 다운로드·CRC/지문 대조 → 뒤로 가기·팀 간 격리·로그아웃을 확인했다. [검증 조건과 Windows 재개 명령](local-release-validation.md)
- 이 후보의 기본 Small Smoke는 HTTP 216건, 오류 0건이었다. 고정 경로 수정 후 Medium worker 준비와 실제 읽기 예열도 통과해 5 VU·5분 3회의 동일 조건 측정을 시작했다. Windows PC는 꺼져 있어 실기기 판정은 대기다.

## 부하 준비용 runner의 Workspace 경로 수정 (2026-11-06)

- `0ebf75d`에서 Python 717개, 프런트엔드 169개, build, 생성 코드·보고서 검사와 k6 모델 5개가 통과했다. Small Smoke 205건의 오류는 0건이었다. Medium 사전 준비는 비동기 접수 후 실제 health 호출 전에 실패했다.
- Studio가 전달한 case·project·file root 세 인자를 격리 runner가 거부한 것을 실제 명령 생성기로 재현했다. 원래 준비한 fixture의 세 경로가 정확히 일치할 때만 받도록 수정했다. 회귀 8개와 실제 동기·비동기 저장 케이스가 각각 HTTP 200·exit 0으로 통과했고 임시 파일은 0개였다. 수정 후 고정 후보에서 전체 검증을 다시 진행한다.

## 4·5단계 로컬 출시 후보 검증 착수 (2026-11-06)

- 후보 커밋 `0ebf75d`를 별도 checkout에 고정했다. 저장소의 Medium 모델과 잠정 기준으로 실제 k6 Smoke·Baseline·Target·저장 경합·실행 용량·Stress·Spike·Soak를 검사한다. 중단·오류·회복 판정은 원시 자료대로 분리한다.
- 같은 후보에서 전체 Python, 프런트엔드, build, 생성 코드, 실제 브라우저 핵심 흐름을 검증한다. 사용자의 Windows 테스트 PC는 현재 꺼져 있어 Windows 실기기 실행을 대기로 기록한다.

## 3단계 Large 선택기 측정·개선 완료 (2026-11-06)

- 기준 48459f7의 production UI에서 프로젝트 100개·케이스 20,000개로 측정했다. 대시보드와 파이프라인 편집기는 진입 시 각각 목록 3회, 총 300개 참조를 받았다. 기존 cursor API를 사용하는 20개 단위 선택기를 적용했고 현재 프로젝트 문서는 reference로 직접 조회한다.
- 동일 브라우저·동일 fixture에서 빌드 순서를 교차해 재측정했다. 두 화면 모두 목록 1회·20행이다. 선택 가능 시점 중앙값은 대시보드 133.0→79.8ms, 파이프라인 편집기 128.0→80.7ms였다. [측정 방법과 원시 자료](reference-picker-performance.md)
- 최초 UI 회귀에서 기존 전체조회 mock과 호출 횟수 가정이 깨져 28개가 실패했다. 페이지 응답 처리와 route별 fixture를 보완한 뒤 167개 기존 테스트가 통과했다. 신규 선택기 테스트의 cleanup callback 실수를 수정하고 최종 프런트엔드 169개(38파일) 및 production build 통과. 기존 500kB chunk 경고가 있다.
- 실제 Large 브라우저에서 다음 페이지·검색·새로고침 복원 및 200번째 케이스로 단계 추가 확인. 최종 빌드에서도 로컬 HTTPS 로그인·팀 전환·권한/격리·로그아웃 재검증 성공. 전체 Python 717개(skip 0,133.775초), 생성 코드 최신성 및 diff 검사 통과.

## 2단계 로컬 인증 검증 (2026-11-06)

- 사용자 지정 로컬 범위에서 실제 HTTPS 및 OIDC S256·RS256 로그인, 팀 A/B 전환, 소유 문서 200·타 팀 문서 거부, viewer 쓰기 403, 로그아웃 후 401을 Chrome에서 확인했다. [환경과 결과](oidc-login.md).

## 1단계 튜플 union 로컬 검증 (2026-11-06)

- 공통 튜플을 재사용한 oneOf에서 ready,2,true가 실패하던 사례를 재현해 수정했다. 실제 위치별 디코더가 일치하는 분기에서 전체 튜플을 원래 schema로 검사한다. 최종 계약 151개 통과(52.233초). 실제 HTTP runner에서 직접/allOf/oneOf/anyOf의 정상·실패를 확인했다.

## 1~3단계 착수 (2026-11-06)

- 튜플 헤더 union, 로컬 HTTPS/OIDC 검증, Large 100프로젝트·2만 케이스 선택기 측정을 진행한다. 사용자 요청에 따라 로컬에서 반영한다.

## OpenAPI 3.1 튜플 헤더 allOf 검증 완료 (2026-11-06)

- 공통 튜플을 참조하고 minItems를 추가한 기존 재현 사례에서 ready,2,true가 통과했다. 유효 범위를 벗어난 두 번째 값은 위치 1에서 실패했다. 실제 HTTP runner에서도 직접 선언과 조합 선언의 결과가 일치했다.
- 길이가 다른 분기마다 해당 위치의 prefixItems/items를 골라 타입을 결정한다. 닫힌 tail, 중복 금지, 수치 범위, 필수 길이는 원래 명세로 검증했다. 내부 참조, 참조에 붙은 타입 제약, nullable, 두 explode 표현, 모호한 타입도 회귀에 포함했다.
- 최초 전체 712개 통과 후 설명용 title이 붙은 기존 참조의 호환 문제를 별도 재현했다. 이를 보완한 최종 전체 Python 713개가 135.635초에 모두 통과했다. 생성 최신성과 diff 검사도 통과했고 테스트용 PostgreSQL·Redis는 중지 상태로 복원했다.
- feature/openapi-allof-header-tuples의 기능 커밋과 검증 기록을 원격에 게시하고 develop에 병합한다. [현재 지원 범위](openapi-support-status.md).

## OpenAPI 3.1 튜플 응답 헤더의 allOf 지원 시작 (2026-11-06)

- develop 48459f7에서 기존 X-Tuple fixture로 재현했다. ready,2,true는 직접 선언에서 통과하고, 같은 schema를 참조하는 allOf에 minItems 3을 더하면 schema_type으로 실패한다.
- 각 allOf 분기에서 해당 위치의 prefixItems 또는 items를 선택해 공통 디코더를 정하고, 최종 판정은 원래 명세로 수행한다.

## 전체 검증 기록 커밋·푸시·병합 (2026-11-04)

- 프로젝트 승인으로1ee70a2를 커밋·기능 브랜치 푸시하고 develop에 충돌 없이 병합했다. 제품 코드 변경 없음. 전체 Python707·frontend167·build·생성·k6모델5 통과 기록을 보존한다. 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 확인한다. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OpenAPI 누적 통합 검증 완료 (2026-11-04)

- developb5c6e9d의 누적 계약 변경을 현재 상태로 검증했다. 전체 Python707개(skip0,167.496초), frontend167개/37파일, production build, 생성 최신성, k6모델5개 및 diff 통과. 회귀 결함 및 제품 코드 수정 없음.
- [지원 현황](openapi-support-status.md)에 구현 범위/제한/잔여 후보를 정리했다. 이번 검증은 실제 PostgreSQL/Redis를 포함하며 사용자 DB는 사용하지 않았다. 테스트 서비스를 기존 중지 상태로 복원한다.
- 실제 브라우저/운영 공급자/배포/전체 부하 캠페인/Windows 실행은 이번에 수행하지 않았다. 기존500kB 번들 경고는 유지한다.
- 프로젝트 승인대로 검증 기록을 커밋·기능push·develop병합/push한다. 로그 /tmp/oas-final-{python,web,build,generated,k6}.log.

## OpenAPI 누적 통합 검증 시작 (2026-11-04)

- developb5c6e9d 기준 전체 Python/프런트엔드/build·생성/k6 모델을 재검증한다. 제품 코드 변경 없이 지원 범위와 잔여 항목을 정리하며, 회귀 발견 시 수정한다. 사용자 데이터와 분리된 tmpfs 테스트 DB만 사용한다.

## boolean 배열 items 커밋·푸시·병합 (2026-11-04)

- 프로젝트 한정 사용자 승인으로 기능989dab4를 커밋하고 origin/feature/openapi-boolean-array-items에 일반 푸시했다. 로컬 develop에 충돌 없이 병합하며 검증한 제품 코드와 동일하다.
- 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 관련209개·생성 최신성/diff 통과. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OAS-2 boolean 일반 배열 items 검증 완료 (2026-11-04)

- 직접 배열의 items true/false/빈 schema 및3.1 생략을 지원했다. 항목 문자열 유지, 원래 schema로 금지/개수/중복/enum 판정. 선택 헤더 부재와 빈 항목을 구분하고 기존 typed 배열 경로 유지.
- 검증: 계약141개(신규4개 포함,19.036초), 저장 케이스/결과9개(4.484초), runner49개(0.081초), 이력10개(0.306초), 합계209개 통과. 실HTTP 정상/중복실패·원문 비노출·참조/버전·명시적 array union의 문자열 보존 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 전체 Python/프런트엔드/브라우저 재실행 없음. UI/API/DB 변경 없음. fetch 후 원격/로컬 develop21794a0 일치, 프로젝트 승인대로 커밋/기능push/develop병합/push한다. 로그 /tmp/bool-items-{contracts,saved,runner,history,generated}.log.

## OAS-2 boolean 일반 배열 items 시작 (2026-11-04)

- develop21794a0에서 feature/openapi-boolean-array-items 분기. 직접 array의 items true/false/빈 schema와3.1 items 생략을 지원한다. 항목은 문자열 유지, 원래 schema로 개수/중복/금지 판정.
- 참조된 boolean/빈 schema 포함. 혼합/중첩 타입의 임의 변환은 추가하지 않는다. 관련회귀/실HTTP·생성 검증 후 프로젝트 승인대로 커밋·푸시·병합한다.

## patternProperties 헤더 커밋·푸시·병합 (2026-11-04)

- 프로젝트 한정 사용자 승인으로 기능7365b96을 커밋하고 origin/feature/openapi-pattern-header-fields에 일반 푸시했다. 로컬 develop에 충돌 없이 병합하며 검증한 제품 코드와 동일하다.
- 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 관련205개·생성 최신성/diff 통과. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OAS-2 patternProperties 헤더 검증 완료 (2026-11-04)

- 직접 simple 객체에서 properties와 모든 매칭 패턴을 함께 타입 결정에 사용한다. additionalProperties는 모두 미일치한 필드에만 적용하며 원래 schema로 최종 검증한다. 내부참조·겹치는 패턴·boolean/빈 schema·타입충돌 처리 지원.
- 검증: 계약137개(신규5개 포함,19.285초), 저장 케이스/결과9개(4.785초), runner49개(0.149초), 이력10개(0.354초), 합계205개 통과. 실HTTP 정상/범위실패·원문 비노출·비anchor 패턴·추가속성·3.0/잘못된 regex 거부 및 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 전체 Python/프런트엔드/브라우저 재실행 없음. UI/API/DB 변경 없음. fetch 후 원격/로컬 develop3432832 일치, 프로젝트 승인대로 커밋·기능push·develop병합/push한다. 로그 /tmp/pattern-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 patternProperties 헤더 필드 시작 (2026-11-04)

- develop3432832에서 feature/openapi-pattern-header-fields 분기. 직접 simple 객체의 patternProperties를 필드명에 search 매칭하고 properties/여러 패턴의 제약을 함께 타입 결정에 사용한다.
- 추가속성 schema는 properties/패턴 모두에 미일치할 때만 적용한다. 최종 원래 schema로 모든 제약 검사, boolean/빈 패턴 schema 문자열 유지·거부도 지원한다. 충돌/중첩 타입은 미지원.
-3.1 경계/중첩 매칭·폐쇄 schema·실HTTP 및 기존 회귀/생성 검증 후 프로젝트 승인대로 커밋/푸시/병합한다. UI/API/DB 변경 없음.

## boolean 객체 필드 커밋·푸시·병합 (2026-11-04)

- 프로젝트 한정 사용자 승인으로 기능aaf642c를 커밋하고 origin/feature/openapi-boolean-object-fields에 일반 푸시했다. 로컬 develop에 충돌 없이 병합하며 검증한 제품 코드와 동일하다.
- 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 관련200개·생성 최신성/diff 통과. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OAS-2 boolean 객체 필드 검증 완료 (2026-11-04)

- properties의 true/false/빈 schema 및 참조를 지원했다. 자유 필드는 문자열 유지, 금지 필드의 실제 존재와 required/추가속성 금지는 원래 schema로 검사한다. typed 필드와 두 explode 표현 유지.
- 검증: 계약132개(신규4개 포함,18.851초), 저장 케이스/결과9개(3.544초), runner49개(0.087초), 이력10개(0.226초), 합계200개 통과. 실HTTP 자유/금지필드 정상/실패 및 원문 비노출, 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. UI/API/DB 변경 없음. fetch 후 원격/로컬 developcb5fd0f 일치, 프로젝트 승인대로 커밋/기능push/develop병합/push한다. 로그 /tmp/bool-field-{contracts,saved,runner,history,generated}.log.

## OAS-2 boolean 객체 필드 시작 (2026-11-04)

- developcb5fd0f에서 feature/openapi-boolean-object-fields 분기. 직접 simple 객체의 properties true/false/빈 schema{} 및 빈 additionalProperties schema를 지원한다. 참조된 boolean 필드도 포함한다.
- 자유 필드는 문자열을 유지하고 false 필드는 실제 존재 시 원래 schema로 거부한다. required/추가속성 금지·typed 필드 제약 유지. 조합 container의 boolean 필드 추론 확장은 비범위다.
- 관련 회귀/실HTTP·생성 검증 후 프로젝트 승인대로 커밋/푸시/develop병합한다. UI/API/DB 변경 없음.

## boolean prefixItems 커밋·푸시·병합 (2026-11-04)

- 프로젝트 한정 사용자 승인으로 기능5f59f65를 커밋하고 origin/feature/openapi-boolean-prefix-headers에 일반 푸시했다. 로컬 develop에 충돌 없이 병합하며 검증한 제품 코드와 동일하다.
- 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 관련196개·생성 최신성/diff 통과. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OAS-2 boolean prefixItems 검증 완료 (2026-11-04)

- prefix 위치의 true/false/빈 schema 및 내부참조를 지원했다. 허용 위치는 문자열 보존, false 위치의 존재 여부와 minItems/추가항목 정책은 원래 schema로 검사한다. typed 위치/기존 tail 규칙 유지.
- 검증: 최종 계약128개(신규4개,19.804초), 저장 케이스/결과9개(3.360초), runner49개(0.078초), 이력10개(0.260초), 합계196개 통과. 실제 HTTP false 위치 생략/존재의 정상/실패·원문 비노출 및 생성 최신성/diff 통과. 최초 계약133개는 imported fixture 클래스의5개 중복 수집을 포함해 통과했고 모듈 참조로 바꾼 후 최종128개 재통과. 제품 테스트 실패 없음.
- 전체 Python/프런트엔드/브라우저 재실행 없음. UI/API/DB 변경 없음. 프로젝트 승인대로 커밋·기능push·develop병합/push한다. fetch 후 원격/로컬 develop6adef2e 일치.
- 로그 /tmp/bool-prefix-{contracts,contracts-final,saved,runner,history,generated}.log.

## OAS-2 boolean prefixItems 시작 (2026-11-04)

- develop6adef2e에서 feature/openapi-boolean-prefix-headers 분기. prefixItems 위치의 true/false 및 빈 schema{}를 지원한다. 타입을 추정하지 않고 문자열을 유지하며 최종 원래 schema로 허용/거부한다. 참조된 boolean schema도 포함한다.
- false 위치가 생략됐다고 실패시키지 않고 minItems/실제 위치 존재에 따라 검증한다. 기존 typed prefix/tail·추가항목 정책 유지. 관련 회귀/실HTTP·생성 검증 후 프로젝트 승인대로 커밋/푸시/병합한다.

## enum/const 헤더 커밋·푸시·병합 (2026-11-04)

- 프로젝트 한정 사용자 승인으로 기능fa1c6bd를 커밋하고 origin/feature/openapi-literal-header-types에 일반 푸시했다. 로컬 develop에 충돌 없이 병합하며 제품 코드는 검증한 기능 커밋과 동일하다.
- 이 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 계약/공통 회귀192개 및 생성 최신성/diff 통과. 원본 worktree·운영 배포·브랜치 삭제·강제 푸시 없음.

## OAS-2 enum/const 헤더 타입 검증 완료 (2026-11-04)

- type 없는 동종 enum/const primitive 값에서 디코딩 타입을 결정한다. 원래 enum/const·조합 제약은 보존하며 bool/number 구분과 정수 형태 헤더의 큰 정수 정밀도를 유지한다. 혼합/구조화/null-only literal은 자동 추론하지 않는다.
- 검증: 계약124개(신규5개 포함,22.709초), 저장 케이스/결과9개(4.292초), runner49개(0.108초), 이력10개(0.300초), 합계192개 통과. 실제 HTTP enum-only 정상/실패, 배열/객체/prefixItems/참조·조합·숫자정밀도·값 비노출 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- UI/API/DB 변경 없음. 이번 전체 Python/프런트엔드/브라우저 재실행 없음. 기존 전체669개 결과와 구분한다.
- Git: feature/openapi-literal-header-types는developc1a00a7 기준. 사용자 지정 프로젝트 한정 절차에 따라 커밋·기능push·develop병합/push 진행. fetch 후 원격/로컬 develop 일치 확인, 강제 푸시 없음. 로그 /tmp/literal-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 enum/const 헤더 타입 시작 (2026-11-04)

- developc1a00a7에서 feature/openapi-literal-header-types 분기. 명시적 type이 없을 때 enum/const의 non-null primitive 값들이 같은 타입이면 헤더 디코딩 타입을 결정한다. 숫자 혼합(integer/number)은 number, bool은 integer와 구분한다.
- 최종 enum/const 판정은 원래 schema를 사용한다. 혼합 primitive/객체/배열/null-only 값은 자동 타입 추론하지 않는다. 기존 명시 type·참조·조합·prefixItems 경로 유지. UI/API/DB 변경 없음.
- 관련 계약/runner/이력·실HTTP·생성 검증 후 프로젝트에 승인된 커밋→기능push→develop병합/push를 수행한다. 강제 푸시 없음.

## prefixItems 로컬 병합·원격 반영 (2026-11-04)

- 사용자 승인으로 기능b62f12a를 커밋하고 origin/feature/openapi-prefix-header-arrays에 일반 푸시했다. 로컬 develop 병합은 충돌 없으며 검증한 제품 코드와 동일하다. 커밋 전 계약119개(16.256초)/diff 통과, 이전 관련187개/집중5개 증거 유지. 전체 Python/브라우저 재실행은 아니다.
- 사용자가 완료 후 커밋→푸시→develop 병합/푸시 절차를 명시 승인했으며 적용 범위를 API Develop Studio 프로젝트로 한정했다. 다른 프로젝트에는 적용하지 않는다. 기존 원격 푸시 보류 지시를 이 프로젝트에 한해 변경한다.
- 최초 원격 push 자동 검토는 목적지 소유권/승인 구체성 미확인으로 거절했다. 미실행을 확인한 뒤 origin=OnSe-MiRo/api-develop-studio 및 연결 GitHub 계정OnSe-MiRo의 소유권 일치를 검증했다. 같은 목적지로 근거를 보완한 재검토 후 기능 push 성공. 우회·강제 푸시 없음.
- 이 병합 커밋을 origin/develop에 일반 푸시하고 원격 SHA를 최종 확인한다. 앞서 로컬에 보관했던35개 이력도 포함된다. 원본 worktree/운영 배포/브랜치 삭제는 변경하지 않는다.

## 완료 작업 원격 반영 절차 적용 (2026-11-04)

- 사용자 지시: 앞으로 작업 검증 완료 후 커밋→기능 브랜치 푸시→develop 병합→develop 푸시까지 수행한다. 기존 원격 푸시 보류 지시를 이번 명시적 지시로 변경한다. 강제 푸시/브랜치 삭제/운영 배포는 포함하지 않는다.
- 현재 완료된 prefixItems 변경부터 적용한다. fetch 후 origin/develop99bbdf9는 로컬 develop0a7b36c의 조상이며 로컬이35커밋 앞선 상태다. 새 기능과 앞서 로컬에 보관한 통합 이력도 일반 fast-forward 푸시로 게시한다.
- 직전 관련187개와 집중5개·실HTTP·생성 최신성 검증 기록을 유지하고 커밋 전 계약 전체를 재검증한다. 제품 코드 추가 수정 없음.

## OAS-2 prefixItems 헤더 배열 완료 (2026-11-04)

- 직접 array schema의 prefixItems 위치별 primitive 타입을 해석한다. 참조/nullable/지원 조합 포함, minItems·items=false/typed/true 정책과 원래 schema 제약을 보존한다. 빈 문자열 항목·기존 simple 분리 규칙 유지.
- 검증: 계약119개(신규5개 포함,16.270초), 저장 케이스/결과9개(3.241초), runner49개(0.100초), 이력10개(0.225초), 합계187개 통과. 최종 fixture에서 nullable array 및3.0의 prefixItems 자체 거부를 분리해 집중5개(0.851초) 재통과. 실HTTP 위치타입 정상/실패 및 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. UI/API/DB 구조 변경 없음. container composition 간 tuple 합성·중첩 simple 직렬화·고급 참조 등은 별도다.
- Git: 로컬 경로 수정afbe9d8·develop병합0a7b36c 완료. 새 feature/openapi-prefix-header-arrays는0a7b36c 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/prefix-header-{contracts,saved,runner,history,generated,final-focus}.log.

## OAS-2 prefixItems 헤더 배열 시작 (2026-11-04)

- develop0a7b36c에서 feature/openapi-prefix-header-arrays 분기. 직접 array schema의 prefixItems 위치별 primitive 타입을 디코딩하고 원래 schema로 최종 검증한다. 내부참조·기존 primitive 조합/nullable 타입 지원.
- items=false는 추가항목 거부, items schema는 tail 항목 변환/검증, items 생략/true는 tail 문자열 보존. prefixItems 길이만으로 필수를 추정하지 않고 minItems에 따른다. 중첩/모호한 위치 타입 및 container composition 간 tuple 병합은 비범위다.
- OpenAPI3.1 위치/길이/추가항목·참조·실HTTP 및 기존 회귀/생성 최신성 검증. UI/API/DB 변경 없음. 새 변경 미커밋, 원격 푸시 없음.

## 로컬 참조 파일 경로 수정 병합 완료 (2026-11-04)

- 사용자 승인으로afbe9d8을 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약114개(17.199초)/diff 통과. 직전 관련191개·생성 최신성 근거 유지. 제품 코드는 기능 커밋과 동일하며 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은3.1 prefixItems 헤더 배열 지원이다.

## OAS-2 로컬 참조 파일 경로 보완 완료 (2026-11-04)

- 잘못된 percent/UTF-8·encoded backslash·drive colon·NUL이 허용되는5경로를 재현 후 엄격한 단일 디코딩/경로 검사로 수정했다. raw 제어문자 제거에 따른 다른 경로 선택도 차단한다. 정상 한글/공백/percent 파일명과 루트 내부 상대참조는 유지한다.
- 검증: 계약114개(신규5개 포함,16.094초), release/portal30개(8.214초), 편집20개(0.604초), SDK18개(0.583초), 저장 케이스/결과9개(3.644초), 합계191개 통과. 두 버전 bundle/local loader 동일성, root/external 경계·오류 원문 비노출·잘못된 참조의 대상 파일 read 전 차단 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- UI/API/DB 구조 변경 없음. 이번 전체 Python/프런트엔드/브라우저/Windows native 실행 재검증 없음. 직전 전체669개는 이번 수정 전 결과다.
- Git: fix/openapi-local-reference-paths·HEADb02e6d8 기준 미커밋. 커밋·병합·푸시·원본 worktree 변경 없음. 로그 /tmp/local-path-{contracts,release,editor,sdk,saved,generated}.log.

## OAS-2 로컬 참조 파일 경로 보완 시작 (2026-11-04)

- developb02e6d8에서 fix/openapi-local-reference-paths 분기. 기존 local_path가 잘못된%/UTF-8·encoded backslash·drive colon·NUL을 허용하는5경로를 재현했다.
- URI 파일 경로를 엄격한 UTF-8로1회 디코딩하고 raw/decoded 제어문자·역슬래시·colon을 거부한다. 루트탈출/절대경로·외부 URL/쿼리 제한 유지. 정상 한글/공백/percent 파일명과 루트 내부 상대참조는 보존한다.
- 경로/unit·bundle/로컬 CLI 파일·편집기/SDK/릴리스 및 기존 계약 회귀 검증. 사용자 파일 수정·외부 파일 읽기 없이 격리 fixture 사용. 새 변경 미커밋·미병합·미푸시.

## JSON Pointer 수정 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 기능276bbb0을 로컬 develop에 충돌 없이 병합했다. 커밋 직전 계약109개(15.703초)/diff 통과. 기존 관련186개 및 생성 최신성 검증은 해당 단계 기록대로 유지한다.
- 검증한 기능 커밋과 제품 코드가 동일하며 이 완료 기록만 추가한다. 이번 전체 Python/프런트엔드/브라우저 재실행 없음. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## OAS-2 JSON Pointer 해석 보완 완료 (2026-11-04)

- 배열 -1/01/+1이 마지막 항목을 선택하는 기존 동작을 재현 후 ASCII 표준 인덱스만 허용하도록 수정했다. 로컬 fragment percent/UTF-8·tilde escape 검증과 루트# 지원, dict key 보존, scalar traversal 거부. bundle 파일명/fragment 재인코딩과 편집기 소비 경로도1회 디코딩으로 유지한다.
- 최종 검증: 계약109개(신규6개 포함,16.543초), release/portal30개(7.632초), OpenAPI편집20개(0.451초), SDK18개(0.513초), 저장 케이스/결과9개(3.922초), 합계186개 통과. 원문 비노출·두 버전 잘못된 참조의 HTTP 전 차단, recursive root/percent 파일·필드명 및 편집기 호환 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 최초 회귀 통과 후 공통 local_path의 편집기 소비 코드에서 재디코딩 가능성을 발견해 canonical URI fragment 반환을 유지하도록 보완하고 관련186개를 최종 재실행했다.
- UI/API/DB 구조 변경 없음. 이번 전체 Python/프런트엔드/브라우저 재실행 없음. 직전 전체669개는 이 수정 전 통합 검증 결과다. 외부 URL/루트탈출/anchor/dynamic reference 허용은 추가하지 않는다.
- Git: fix/openapi-json-pointer·HEAD939f00f 기준 미커밋. 커밋·병합·푸시·원본 worktree 변경 없음. 로그 /tmp/pointer-{contracts,contracts-final,release-final,openapi-final,sdk-final,saved-final,generated-final}.log.

## OAS-2 JSON Pointer 해석 보완 시작 (2026-11-04)

- develop939f00f에서 fix/openapi-json-pointer 분기. 기존 pointer가 배열 -1/01/+1을 모두 마지막 항목으로 읽는 문제를 재현했다.
- 로컬 fragment를 UTF-8 percent decode1회 후 JSON Pointer escape/ASCII 배열 인덱스 규칙으로 검사한다. 루트# 지원, 잘못된 percent/tilde/음수/선행0/append 인덱스 거부. dict의 숫자 모양 key는 그대로 유지한다.
- bundle fragment도 같은 검사기를 사용하고 파일명/fragment를 다시 인코딩해 literal percent를 중복 디코딩하지 않는다. 외부 URL·루트탈출·anchor/dynamic ref 제한은 유지한다.
- pointer/RFC fixture·bundle/CLI·lint/실행 전 거부 및 기존 계약 회귀/생성 최신성을 검증한다. UI/API/DB 변경 없음. 미커밋·미병합·미푸시.

## 미병합 브랜치 로컬 develop 통합 완료 (2026-11-04)

- 사용자 요청에 따라 검증한 feature/legacy-branch-integration의ccf22b3를 로컬 develop에 충돌 없이 병합했다. 기능6개와 main의 기존 이력이 모두 develop에 포함된다. main 포인터와 원본 미커밋3파일은 그대로 유지했다.
- 검증한 통합 코드/테스트와 동일하고 이 완료 기록만 추가한다. 제품 코드 신규 반영은 없으며 추가분은 영문 개요/작업 기록/감사 문서다. 전체 Python669·frontend167·build·생성·k6모델5 통과 근거는 직전 기록 참조. 원격 푸시·브랜치 삭제 없음.

## 미병합 브랜치 감사·통합 검증 완료 (2026-11-04)

- 기능 브랜치6개 및 main의 미병합 이력을 대조했다. 미반영 제품 코드는 없었다. quick/dashboard/P0의 기존 이식과 후속 권한·실행·저장 보완을 유지했다. baseline 추가 기록22줄은 보존, 영문 README 개요는 최신 구성에 맞춰 README.en.md로 반영하고 한국어 README는 유지했다.
- 검증: 전체 Python669개(skip0,160.951초), frontend167개/37파일, production build, 생성 최신성, Node k6 모델5개 및 diff 통과. 기존500kB 번들 경고는 유지된다. 제품 코드/테스트는 기준 develop95c8518과 byte 동일하며 변경은 README·문서뿐이다. 브라우저를 새로 실행한 것으로 표기하지 않는다.
- 이력: baseline은 일반 병합, 이미 이식된 quick/dashboard 및 최신 문서로 대체한 README/main 이력은 명시적 ours 병합으로 연결했다. main 포인터는bab7dad 유지한다. [감사 근거](legacy-branch-integration-audit.md).
- 보존: 원본 worktree HEAD/status/미커밋3파일 SHA 불변을 재확인했다. stash/reset/파일 삭제/브랜치 삭제/원격 푸시 없음. 테스트용 PostgreSQL·Redis는 검증 후 원래 중지 상태로 복원한다. 검증한 통합 브랜치를 로컬 develop으로 병합한다.
- 로그: /tmp/legacy-integration-{python,web,build,generated,k6}.log.

## 미병합 브랜치 실제 변경 감사·통합 시작 (2026-11-04)

- 로컬 미병합 기능6개를 commit/range-diff·현재 구현과 비교했다. quick/dashboard/P0는 이미 이식됐고 baseline의 제품 코드는ebf7672와 동일하다. 추가 진행 기록22줄은 일반 병합으로 보존하고 중복 제품 구현은 최신 상태를 유지한 이력 병합으로 연결한다.
- 실제 미반영 영문 README 개요는 main 전용 설명을 최신 FastAPI/저장소/인증 구성에 맞춰 README.en.md로 반영하고 기존 한국어 README는 링크만 추가한다. 원본 worktree의 미커밋3파일은 별도 SHA 기록 후 보존한다.
- [브랜치별 근거](legacy-branch-integration-audit.md). main/원격 브랜치는 변경하지 않고 별도 feature/legacy-branch-integration에서 검증 후 develop에 병합한다. 전체 Python/프런트엔드·build·생성/k6모델 및 제품 tree 동일성을 확인한다.

## 객체 oneOf·anyOf 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 기능8e0a277을 로컬 develop에 충돌 없이 병합했다. 커밋 직전 계약103개(15.399초)/diff 검사 통과. 기존 관련171개·실HTTP·생성 최신성 증거는 해당 단계 기록대로 유지한다.
- 검증한 기능 커밋과 제품 코드가 동일하며 이 완료 기록만 추가한다. 전체 Python/프런트엔드/브라우저를 이번에 재실행한 것은 아니다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## OAS-2 객체 container oneOf/anyOf 완료 (2026-11-04)

- 모든 분기의 필드 집합/primitive 타입과 추가속성 디코딩 타입이 같은 경우 공통 객체 디코더를 구성했다. 원래 schema로 enum/required/추가속성 금지 및 전체 분기 일치를 검사한다. 내부참조·중첩 union·지원 allOf·nullable·두 explode 경로 유지.
- 검증: 계약103개(신규5개 포함,17.717초), 저장 케이스/결과9개(3.632초), runner49개(0.070초), 이력10개(0.169초), 합계171개 통과. 두 버전·교차분기 거부·oneOf 중복일치/anyOf 허용·폐쇄 schema·타입/구조 차이·순환/한도·실HTTP 정상/실패 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. API/UI/DB 구조 변경 없음. 과거 전체659개 및 이관 기대값 보완 결과는 당시 범위대로 유지한다.
- Git: 배열 union 기능df64b38·로컬 develop병합ef30a21 완료. 새 feature/openapi-union-header-objects는ef30a21 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/union-object-{contracts,saved,runner,history,generated}.log.

## OAS-2 객체 container oneOf/anyOf 시작 (2026-11-04)

- developef30a21에서 feature/openapi-union-header-objects 분기. 모든 객체 분기의 필드 집합/primitive 타입 및 미선언 필드의 디코딩 타입이 같을 때만 공통 디코더를 만든다. 참조/중첩 union/지원 object allOf 분기 포함.
- enum/required/추가속성 허용·금지/개수 및 정확한 분기 일치는 원래 schema로 검증한다. 다른 필드구조/혼합타입/조건부/패턴/순환·32단계128방문 초과는 추론하지 않는다.
- 두 버전·분기 의미·폐쇄 schema·실HTTP와 공통 회귀/생성 최신성 검증. UI/API/DB 변경 없음. 새 변경 미커밋, 원격 푸시 없음.

## 배열 oneOf·anyOf 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로df64b38을 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약98개(15.900초)/diff 통과. 직전 관련166개·실HTTP·생성 최신성 근거 유지. 제품 코드는 기능 커밋과 동일하고 완료 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 동일 필드 타입 객체 container oneOf/anyOf다.

## OAS-2 배열 container oneOf/anyOf 완료 (2026-11-04)

- 동종 primitive 항목 배열의 최상위 oneOf/anyOf를 디코딩한다. 내부참조·중첩 union/지원 allOf 분기·nullable·explode 지원. 원래 schema로 전체 배열의 분기 일치/개수/enum 등을 검사해 교차 분기 항목 혼합과 oneOf 중복일치를 올바르게 거부한다.
- 검증: 계약98개(신규5개 포함,13.144초), 저장 케이스/결과9개(3.157초), runner49개(0.094초), 이력10개(0.165초), 합계166개 통과. 실HTTP 정상/교차분기 실패·모호한 타입/비배열/순환/한도 및 기존 회귀 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. API/UI/DB 구조 변경 없음. 직전 전체659개 및 이관 테스트 재검증은 당시 기록대로 유지한다.
- Git: 객체 allOf 기능5a432e5·로컬 develop병합ebf7672 완료. 새 feature/openapi-union-header-arrays는ebf7672 기준 미커밋, 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/union-array-{contracts,saved,runner,history,generated}.log.

## OAS-2 배열 container oneOf/anyOf 시작 (2026-11-04)

- developebf7672에서 feature/openapi-union-header-arrays 분기. 모든 분기가 명시적 array 또는 지원하는 array allOf이고 primitive 항목 타입이 같을 때만 배열 디코딩한다. nested union/내부참조 및 기존 nullable 타입 포함.
- 분기별 items 제약을 합쳐 느슨하게 만들지 않는다. 최종 원래 schema로 전체 배열의 oneOf/anyOf·개수·enum·중복을 판정한다. 혼합 항목 타입/비배열/조건부/튜플/순환/한도 초과는 추론하지 않는다.
- 두 버전·분기 의미·교차 분기 항목 거부·실HTTP와 기존 계약/runner/이력 회귀·생성 최신성 검증. UI/API/DB 변경 없음. 새 변경 미커밋, 원격 푸시 없음.

## 객체 allOf 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로5a432e5를 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약93개(21.778초)/diff 통과. 기존 집중161개 및 전체659개 실행/이관 기대값 보완 후1개 재검증 기록은 정확한 범위대로 유지한다. 제품 코드는 기능 커밋과 동일하고 완료 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 배열 container oneOf/anyOf다.

## OAS-2 객체 container allOf 완료 (2026-11-04)

- allOf/내부참조로 분산된 object/primitive 필드의 디코딩 정보를 수집했다. 각 분기에서 미선언 필드에 적용되는 additionalProperties schema도 타입 결정에 반영한다. 최종 원래 schema 검사로 required/개수/범위/분기별 additionalProperties=false 보존.
- 집중 검증: 계약93개(신규6개 포함,14.335초), 저장 케이스/결과9개(4.327초), runner49개(0.092초), 이력10개(0.215초), 합계161개 통과. 두 버전·참조·폐쇄 schema 우회 방지·추가속성 교집합·순환/한도·실HTTP 정상/범위실패 및 생성 최신성/diff 통과.
- 전체 Python659개(276.548초,skip0) 실행:658개 통과·기존 결합 PostgreSQL 이관 테스트1개 실패. 저장 결과 기능으로 schema version7이 되었는데 기존 기대값은6이었다. 현재 migration 및 test_migrations의7 기준을 확인해 기대값을7로 수정하고 saved_run_results 빈 테이블 확인을 추가했다. 수정 후 해당 실제 PostgreSQL 이관1개(1.256초) 재검증 통과. 테스트 기대값만 보완했으며 제품 migration은 변경하지 않았다. 전체659개를 이 수정 후 다시 실행한 것으로 표기하지 않는다.
- UI/API/DB 구조 변경 없음. 프런트엔드/브라우저 재실행 없음. 운영 배포·전체 부하 및 나머지 고급 계약 범위는 별도다. 테스트용 tmpfs PostgreSQL/Redis는 실행 전 중지 상태였으며 검증 후 중지로 복원한다.
- Git: 배열 allOf 기능da3acb7·로컬 develop병합7dbaf91 완료. 새 feature/openapi-allof-header-objects는7dbaf91 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/composed-object-{contracts,saved,runner,history,generated,python-all,migration-recheck}.log.

## OAS-2 객체 container allOf 시작 (2026-11-04)

- develop7dbaf91에서 feature/openapi-allof-header-objects 분기. allOf/내부참조의 명시적 object 타입과 primitive property 제약을 디코딩용으로 수집한다. 각 분기에서 미선언 필드에 적용되는 additionalProperties schema도 고려한다.
- 최종 검증은 원래 schema로 수행해 분기별 additionalProperties=false, required, min/maxProperties 등을 보존한다. container union/조건부/patternProperties/unevaluatedProperties·순환·32단계/128방문 초과는 추론하지 않는다.
- 두 버전·참조·폐쇄 schema 유지·타입 교집합·두 explode·실HTTP 및 관련 회귀/생성 최신성 검증. API/UI/DB 변경 없음. 새 변경 미커밋·원격 푸시 없음.

## 배열 allOf 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로da3acb7을 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약87개(12.007초)/diff 통과. 직전 관련155개·실HTTP·생성 최신성 증거 유지. 제품 코드는 기능 커밋과 동일하고 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 객체 container allOf 지원이다.

## OAS-2 배열 container allOf 완료 (2026-11-04)

- allOf/내부참조로 분산된 명시적 array 타입과 items 제약을 디코딩용으로 결합했다. 최종 원래 schema 검사로 minItems/maxItems/uniqueItems와 모든 항목 제약 보존. 두 버전·중첩·nullable·explode 및 기존 직접 array 경로 유지.
- 검증: 계약87개(신규5개 포함,11.500초), 저장 케이스/결과9개(3.312초), runner49개(0.093초), 이력10개(0.355초), 합계155개 통과. 실HTTP 정상/중복항목 실패, 참조/제약 교집합·충돌/순환/방문한도 확인. 생성 최신성/diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. API/UI/DB 구조 변경 없음. 객체 container 조합·배열 union/prefixItems·고급참조 등은 별도다.
- Git: oneOf/anyOf 기능057de52·로컬 develop병합c1d0610 완료. 새 feature/openapi-allof-header-arrays는c1d0610 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/composed-array-{contracts,saved,runner,history,generated}.log.

## OAS-2 배열 container allOf 시작 (2026-11-04)

- developc1d0610에서 feature/openapi-allof-header-arrays 분기. 최상위 allOf·내부참조에 분산된 명시적 array 타입과 items 제약을 읽어 디코딩용 items allOf를 만든다. 최종 검증은 원래 schema로 수행한다.
- minItems/maxItems/uniqueItems/enum 등 제약 보존. 직접 array 경로는 기존 동작 유지. container oneOf/anyOf/prefixItems/모호한 타입·순환·32단계/128방문 초과는 조합 추론하지 않는다.
- 두 버전·참조·제약·충돌·실HTTP 및 관련 회귀/생성 최신성 검증. API/UI/DB 변경 없음. 새 변경 미커밋, 원격 푸시 없음.

## oneOf·anyOf 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로057de52를 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약82개(10.330초)/diff 통과. 직전 관련150개·실HTTP·생성 최신성 증거 유지. 제품 코드는 기능 커밋과 동일하며 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 배열 container allOf 지원이다.

## OAS-2 동종 oneOf/anyOf 헤더 완료 (2026-11-04)

- 같은 primitive 타입을 결정할 수 있는 oneOf/anyOf 분기를 해석해 scalar·배열항목·객체필드/추가속성에 적용했다. 원래 schema로 일치 판정하므로 oneOf 중복일치는 거부하고 anyOf는 허용한다. 내부 참조·allOf 조합·nullable type 배열 및 기존 직접 type 동작 유지.
- 검증: 계약82개(신규5개 포함,10.255초), 저장 케이스/결과9개(3.386초), runner49개(0.094초), 이력10개(0.183초), 합계150개 통과. 두 버전·분기 제약·중복일치·혼합/미지정 타입·순환/탐색한도·실제 HTTP runner 정상/분기실패 확인. 생성 최신성·diff 통과. 구현 테스트 실패 없음.
- 전체 Python/프런트엔드/브라우저는 이번에 재실행하지 않았다. API/UI/DB 변경 없음. container-level 조합 병합·고급 참조/dialect 등은 별도이며 전체 로드맵 완료가 아니다.
- Git: feature/openapi-union-header-types·HEADe21ba24 기준 미커밋. 커밋·병합·푸시·원본 worktree 변경 없음. 로그 /tmp/union-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 동종 oneOf/anyOf 헤더 시작 (2026-11-04)

- develope21ba24에서 feature/openapi-union-header-types 분기. 모든 oneOf/anyOf 분기가 같은 primitive 타입을 명시/참조/allOf로 결정할 때만 그 타입으로 변환한다. scalar·배열 items·객체 필드/추가속성에 적용한다.
- 최종 oneOf/anyOf 일치 판정은 원래 schema validator에 맡긴다. 타입 없는/혼합 타입/순환/한도 초과 분기는 자동 변환하지 않는다. null-only 분기 추론은 이번 비범위이며 기존 nullable type 배열은 유지한다. 32단계/128방문 한도 공유.
- 두 버전·중첩/참조·oneOf 중복일치 거부·anyOf 허용·배열/객체·실HTTP 및 기존 회귀/생성 최신성 검증. UI/API/DB 변경 없음. 새 변경 미커밋, 커밋·병합·푸시 없음.

## allOf 헤더 타입 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 기능 커밋fd84c4a를 로컬 develop에 충돌 없이 병합했다. 커밋 직전 계약77개(9.946초) 및 diff 검사 통과. 기존 관련145개·실HTTP·생성 최신성 증거는 해당 단계 기록대로 유지한다.
- 검증한 기능 커밋과 제품 코드가 동일하며 이 완료 기록만 추가한다. 이번 전체 Python/프런트엔드/브라우저 재실행 없음. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## OAS-2 allOf primitive 헤더 타입 완료 (2026-11-04)

- 직접 type 없는 allOf의 단일 primitive/정수·숫자 교집합을 해석하고 scalar/배열항목/객체필드·추가속성에 적용했다. 내부 참조/중첩/nullable 지원 및 원래 schema 제약 보존, 모호함/순환/탐색 한도 처리. container 구조 병합은 제외한다.
- 검증: 계약77개(신규5개 포함,11.302초), 저장 케이스/결과9개(3.858초), runner49개(0.105초), 이력10개(0.276초), 합계145개 통과. 실제 HTTP runner 정상/범위실패, 두 버전·참조·제약·타입 교집합·순환/방문한도 및 기존 JSON/simple/nullable 회귀 확인. 생성 최신성·diff 통과. 구현 테스트 실패 없음.
- 이번 전체 Python/프런트엔드/브라우저 재실행 없음. API/UI/DB 구조 변경 없음. 과거 전체603개와 구분한다.
- Git: JSON 본문 수정0310871·로컬 develop병합ef8fcd4 완료. 새 feature/openapi-allof-header-types는ef8fcd4 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/allof-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 allOf primitive 헤더 타입 시작 (2026-11-04)

- developef8fcd4에서 feature/openapi-allof-header-types 분기. 직접 type이 없는 allOf에서 단일 primitive 타입을 추론해 scalar/배열 items/객체 properties 및 additionalProperties를 변환한다. 내부 참조와 중첩 allOf 포함, integer∩number는 integer다.
- 원래 schema로 최종 검증하므로 enum/범위 등 제약을 병합·삭제하지 않는다. 충돌/분기/순환·32단계 또는128방문 초과는 추론하지 않는다. 직접 type의 기존 동작 유지, 객체/배열 container allOf 병합은 비범위다.
- 두 버전·참조·제약·경계·실HTTP 및 공통 회귀/생성 최신성 검증. API/UI/DB 변경 없음. 새 변경은 미커밋, 원격 푸시 없음.

## JSON 응답 본문 수정 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로0310871을 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약72개(8.681초)/diff 통과. 직전 관련140개 결과 유지. 제품 코드는 기능 커밋과 동일하고 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 allOf primitive 헤더 타입 해석이다.

## OAS-2 JSON 응답 본문 검증 보완 완료 (2026-11-04)

- schema 없는 JSON 응답 문법 오류와 NaN/중복 key가 valid=true로 잘못 통과하는3경로를 재현 후 수정했다. JSON 헤더/본문에 동일 strict parser 적용, schema 유무와 무관한 원문 검증 및 값 비노출 invalid_json을 제공한다. 비JSON·본문 금지 status·계약 opt-out은 유지한다.
- 검증: 계약72개(신규6개 포함,10.147초), 저장 케이스/결과9개(4.375초), runner49개(0.159초), 이력10개(0.229초), 합계140개 통과. 실제 HTTP opt-in 정상/중복키 실패·opt-out 기존 통과와 보고서 비노출, 빠른 호출 연결 확인. 생성 최신성/diff 통과.
- 최초 계약 테스트4개 subtest 실패는2,000중첩 유효 JSON이 항상 RecursionError를 낸다는 잘못된 fixture 가정이었다. 해당 가정을 제거하고 관련 전체를 재실행했다. 제품에 임의 depth 차단은 추가하지 않았고 실제 파서 RecursionError는 invalid_json으로 처리한다.
- 전체 Python/프런트엔드/브라우저 재실행 없음. API/UI/DB 구조 변경 없음. 과거 전체603개 결과와 구분한다.
- Git: text/plain·nullable 기능50dd28a·로컬 병합875f5f1 완료. fix/openapi-json-response-validation에 다음 수정만 미커밋, 원격 푸시·원본 worktree 변경 없음. 로그 /tmp/strict-body-{contracts,contracts-final,saved,runner,history,generated}.log.

## OAS-2 JSON 응답 본문 검증 보완 시작 (2026-11-04)

- develop875f5f1에서 fix/openapi-json-response-validation 분기. 현재 코드에서 schema 없는 application/json의 not-json, 빈 schema의 NaN, 중복 JSON key가 모두 valid=true로 통과함을 재현했다.
- schema 유무와 무관하게 raw JSON 본문을 검사하고 JSON 헤더와 동일한 strict parser를 사용한다. 중복 key·비유한 숫자·overflow·문법/과도한 중첩 오류는 원문 비노출 invalid_json으로 판정한다. 중복 key 거부는 제품 정책이다.
- 비JSON 본문·HEAD/204/304 및 원문 없이 이미 파싱된 객체를 전달하는 기존 함수 호출은 유지한다. 실제 빠른 호출/runner는 raw body를 전달한다. API/UI/DB 변경 없음. 새 변경은 미커밋, 원격 푸시 없음.

## text/plain·nullable 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 기능50dd28a를 로컬 develop에 충돌 없이 병합했다. 커밋 전 계약66개(8.290초)/diff 통과, 직전 관련134개 증거 유지. 제품 코드는 기능 커밋과 동일하며 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음. 다음은 JSON 응답 본문 파싱 계약 보완이다.

## OAS-2 nullable 헤더 타입 완료 (2026-11-04)

- OpenAPI3.1 type 배열에서 non-null 타입이 하나인 scalar/container/items/property/additionalProperties를 해석한다. 내부 참조·원래 schema 제약 유지,3.0 nullable 호환, required 누락 및 빈값/문자 null과 JSON null을 구분한다. 모호한 다중 타입 변환은 추가하지 않았다.
- 검증: 계약66개(신규5개 포함,8.327초), 저장 케이스/결과9개(4.374초), runner49개(0.129초), 이력10개(0.300초), 합계134개 통과. 실제 HTTP nullable 배열 정상/실패 및 생성 최신성·diff 통과. 첫 계약66개 중1실패는 신규 fixture가 본문의 Item schema를 덮어쓴 문제였고 HeaderItem으로 분리한 후 관련 전체 재실행 통과.
- UI/API/DB 구조 변경 없음. 이번 전체 Python·프런트엔드·브라우저는 재실행하지 않았다. 과거 전체603개는 이번 변경 전 결과다.
- Git: 기존 text/plain 변경과 함께 feature/openapi-text-response-headers·HEAD99bbdf9 기준 미커밋 유지. 커밋·병합·푸시·원본 worktree 변경 없음. 로그 /tmp/nullable-header-{contracts,contracts-final,saved,runner,history,generated}.log.

## OAS-2 nullable 헤더 타입 시작 (2026-11-04)

- 기존 text/plain 미커밋 변경을 보존하고 같은 feature/openapi-text-response-headers에서 OpenAPI3.1 type 배열의 단일 non-null 타입을 해석한다. scalar·배열/container/items·객체/container/properties/additionalProperties에 공통 적용한다.
- 빈 문자열·문자열 null을 None으로 추정하지 않는다. 원래 schema로 최종 판정하며 required 누락은 nullable과 독립이다. 복수 non-null 타입은 scalar에서 자동 변환하지 않고, 배열 항목/객체 필드는 기존 미지원 판정을 유지한다.
- 두 버전 호환·참조·nullable/누락/빈값·JSON null과 구분·실HTTP 및 관련 회귀를 검증한다. UI/API/DB 변경 없음, 커밋·병합·푸시 없음.

## OAS-2 text/plain 응답 헤더 완료 (2026-11-04)

- text/plain content 헤더를 HTTP client 문자열 그대로 검사한다. 공백/쉼표/JSON 모양 보존, 숫자 자동변환 없음. 두 OpenAPI 버전·Header/schema 참조·문자열 제약·필수 누락/빈 값·원문 비노출을 검증했다. JSON/simple 헤더 경로 유지.
- 검증: 계약61개(신규4개 포함,6.904초), 저장 케이스/결과9개(3.177초), runner49개(0.069초), 이력10개(0.168초), 합계129개 통과. 실제 HTTP runner 정상/enum 실패·contract_failed·보고서 값 비노출 확인. 생성 최신성·diff 통과. 구현 테스트 실패 없음.
- 최신 develop의 호출 전용/저장 결과 기능과 결합 후 앞선 JSON·객체 계약57개와 호출5개도 통과했다. API/UI/DB 구조 변경 없음. 이번 전체 Python/프런트엔드/브라우저 재실행 없음. 과거 전체603개와 구분한다.
- Git: JSON·객체 기능dcd272b, develop 동기화1b83065, 로컬 병합99bbdf9 완료. 새 feature/openapi-text-response-headers는99bbdf9 기준 미커밋. 다른 worktree의 기존 스테이징 변경을 보존했고 정리 완료를 확인한 후 병합했다. 원격 푸시 없음.
- 잔여: XML/HTML/binary content, 모호한/중첩 simple 직렬화, 고급 참조/dialect. 로그 /tmp/text-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 text/plain 응답 헤더 시작 (2026-11-04)

- develop99bbdf9에서 feature/openapi-text-response-headers 분기. 단일 content의 text/plain을 HTTP client가 전달한 문자열 그대로 schema 검증한다. 공백/쉼표/등호/JSON 모양을 보존하고 숫자/불리언 coercion 및 JSON parsing은 하지 않는다.
- 미디어 타입 대소문자/parameter 처리는 기존 JSON 경로와 동일하다. charset 재디코딩을 하지 않는다. XML/HTML/binary/wildcard는 미지원. 기존 JSON/simple 및 저장/호출 판정 유지.
- 두 버전/참조/문자열 제약/누락·빈값·비노출·실HTTP와 공통 경로 회귀/생성 최신성 검증. 새 변경은 미커밋, 원격 푸시 없음.

## JSON·simple 객체 헤더 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 기능dcd272b 및 최신 develop 동기화1b83065를 로컬 develop에 병합했다. 최초 develop checkout은 다른 worktree 사용으로 거부됐으나 해당 작업 완료/깨끗한 상태 확인 후 그 worktree에서 병합했다. 기존 변경을 stash/삭제하지 않았다. 문서 충돌은 양쪽 기록을 보존했다.
- 최신 develop 결합 후 계약57개·케이스 호출5개 통과. 기존 관련122개 증거 유지. 원격 푸시 없음. 다음은 text/plain content 헤더 검증이며 별도 feature 브랜치에서 진행한다.

## OAS-2 simple 객체 응답 헤더 완료 (2026-11-04)

- simple 객체의 기본/명시 explode=false key,value와 explode=true key=value를 지원했다. primitive 필드/추가속성 변환과 기존 schema 제약 검사, 빈 객체·빈 value 보존, 중복/빈 key·깨진 쌍의 값 비노출 진단을 추가했다. JSON content 헤더 미커밋 변경은 보존했다.
- 검증: 계약57개(신규6개 포함,5.875초), 저장 케이스6개(2.796초), runner49개(0.074초), 이력10개(0.176초), 합계122개 통과. 실제 HTTP runner 정상/타입실패·contract_failed·보고서 원문 비노출, OpenAPI3.0/3.1·참조·두 explode 표현·오류 및 기존 JSON/배열 회귀 확인. 생성 최신성·diff 통과. 구현 테스트 실패 없음.
- 범위: API/UI/DB 구조 변경 없음. 이번 전체 Python·프런트엔드 build·브라우저는 재실행하지 않았으며 과거 전체603개와 구분한다. 중첩/모호한 simple 직렬화·비JSON content·고급 reference 지원은 남아 있다.
- Git: feature/openapi-json-response-headers·HEAD/develop06215a9 유지. JSON content와 이번 객체 헤더 변경 모두 미커밋, 커밋·병합·푸시·원본 worktree 변경 없음. 로그 /tmp/object-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 simple 객체 응답 헤더 시작 (2026-11-04)

- 기존 JSON content 헤더 미커밋 변경을 보존하고 feature/openapi-json-response-headers에서 공통 헤더 검사 범위를 확장한다. 커밋·병합·푸시 없음.
- simple 객체의 explode=false(기본) key,value 쌍과 explode=true key=value 쌍을 지원한다. 명시된 primitive properties 및 primitive additionalProperties를 변환하고 required/추가속성/개수/필드 제약은 기존 validator로 검사한다.
- 중복/빈 key·깨진 쌍은 값 비노출 invalid_header_serialization. 중첩/union/타입 모호 필드·객체 composition/patternProperties는 unsupported_header_serialization으로 유지한다. URI decoding/CSV quoting은 추가하지 않는다.
- 두 버전·두 표현·참조·오류/비노출·실HTTP runner 및 관련 회귀/생성 최신성을 검증한다. API/UI/DB 구조 변경 없음.

## OAS-2 JSON content 응답 헤더 완료 (2026-11-04)

- application/json 및 구체적인 application/*+json 단일 content 헤더를 파싱해 객체/배열/스칼라와 내부 참조 schema를 검증한다. 잘못된 JSON·중복 key·비유한 숫자는 invalid_header_json으로 값 비노출 거부한다. 기존 scalar/simple 배열·필수 헤더·본문 검증은 유지한다.
- 검증: 계약51개(신규6개 포함,4.647초)·저장 케이스6개(2.581초)·runner49개(0.083초)·이력10개(0.214초), 합계116개 통과. 생성 최신성·diff 통과. 실제 loopback HTTP runner의 정상/잘못된 JSON 타입 및 contract_failed·보고서 원문 비노출, 빠른 호출 계약 연결을 확인했다. 구현 테스트 실패 없음.
- 이번 단계는 backend 공통 검사기만 변경했다. 전체 Python/React build/실제 브라우저를 새로 실행한 것으로 표기하지 않는다. 이전 전체603개는 배열 단계 결과이며 JSON content 변경 전 결과다. UI/API schema/DB 구조 변경 없음.
- 남은 범위: 비JSON content, simple 객체/중첩 직렬화, 고급 reference/dialect. 로컬 기능 확장을 전체 로드맵 완료로 보지 않는다.
- Git: 배열 기능f763896·로컬 develop병합06215a9 완료. 새 feature/openapi-json-response-headers에 JSON 헤더 변경만 미커밋, 원격 푸시·원본 worktree 변경 없음.
- 자료: [계약 범위](openapi-contract-validation.md), tests/test_contract_json_headers.py. 로그 /tmp/json-header-{contracts,saved,runner,history,generated}.log.

## OAS-2 JSON content 응답 헤더 시작 (2026-11-04)

- develop06215a9에서 feature/openapi-json-response-headers 분기. Header Object의 단일 content 미디어 타입 application/json 및 구체적인 application/*+json을 JSON으로 해석하고 기존 schema validator를 적용한다. 비JSON/wildcard 타입은 미지원으로 유지한다.
- JSON 객체/배열/스칼라·내부 참조·필수 헤더 및 schema 제약을 검사한다. 잘못된 JSON, 중복 객체 key, NaN/Infinity·부동소수점 overflow는 값 비노출 invalid_header_json으로 거부한다. 기존 simple 배열과 본문 검증은 유지한다.
- 검증 계획: 두 버전·미디어 타입·참조·잘못된 JSON·누락·값 비노출, 실제 HTTP runner, 관련 계약/runner/이력 회귀 및 생성 최신성. API schema/UI/저장 변경은 없다. 원격 푸시 없음, 새 단계는 미커밋.

## 응답 헤더 배열 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 f763896을 로컬 develop에 충돌 없이 병합했다. 관련 계약45개(4.570초)·diff 재검증 통과. 직전 전체603개 결과는 해당 단계 기록대로 유지한다. 제품 코드는 기능 커밋과 동일하고 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음.

## OAS-2 응답 헤더 배열 지원 완료 (2026-11-04)

- OpenAPI3.0/3.1 simple 응답 헤더의 primitive 배열을 공통 검사기에 연결했다. 문자열/정수/유한숫자/불리언 변환과 items/배열 제약, 내부 Header/schema/items 참조, explode true/false를 지원한다. 빈 항목은 보존하고 %2C는 디코딩하지 않는다.
- 최종 검증: 전체 Python603개(skip0,217.717초) 통과, 신규 집중5개 및 생성 코드 최신성·diff 검사 통과. 실제 loopback HTTP runner에서 정수배열 통과/잘못된 항목 contract_failed 및 보고서 값 비노출 확인. 최초 fixture1오류·서비스 중지55오류는 이전 기록대로 보존하며 환경 보완 후 전체를 재실행했다.
- 경계: UI 변경이 없어 이번 헤더 단계에서 frontend/브라우저를 재실행하지 않았다. 직전 검색 커밋 전 관련28개/build를 확인했다. content 기반 헤더·객체/중첩/모호한 항목 타입·prefixItems 및 고급 참조 지원은 여전히 남아 있다. 전체 로드맵 완료가 아니다.
- 반영: 검색 커밋ef79d2c·로컬 develop병합1603e68 완료. 새 feature/openapi-response-header-arrays는1603e68 기준 미커밋. 원격 푸시·원본 worktree 변경 없음. 전용 테스트 서비스는 검증 후 기존 중지 상태로 복원한다.
- 자료: [지원 범위](openapi-contract-validation.md), tests/test_contract_header_arrays.py. 로그 /tmp/header-arrays-{focus,all,all-final,generated}.log.

## OAS-2 응답 헤더 배열 검증 환경 보완 (2026-11-04)

- 신규 집중5개(두 버전/타입/참조/제약/비노출 및 실제 HTTP runner) 통과. 최초 HTTP fixture는 필수 project 누락으로 configuration_error가 나서 fixture에 demo.json을 지정했다. 제품 설정 검증은 유지했다. 생성 최신성 통과.
- 최초 전체603개는55오류: 전용 PostgreSQL/Redis 서비스가 중지된 상태였고 connection refused가 발생했다. 격리 docker-compose.test.yml의 tmpfs 서비스들을 healthy까지 기동하여 전체 회귀 재실행 중이다. 사용자 DB/운영 서비스는 사용하지 않는다.

## OAS-2 응답 헤더 배열 지원 시작 (2026-11-04)

- develop1603e68에서 feature/openapi-response-header-arrays 분기. OpenAPI3.0/3.1 simple 헤더의 쉼표 구분 단일 primitive 타입 배열을 지원한다. explode true/false 배열 표현은 동일하며 기본 simple을 적용한다.
- 항목 타입/format/enum 및 배열 minItems/maxItems/uniqueItems 제약은 기존 schema validator로 검사한다. 중첩/객체/타입 모호 배열·prefixItems·content 기반 헤더는 미지원으로 남긴다. 진단에 실제 헤더 값은 포함하지 않는다.
- 검증: 두 버전/참조/직렬화·값 비노출 회귀, 실제 HTTP 저장 케이스 runner, 전체 Python 및 생성 최신성. UI/API schema 변경은 없다. 새 변경은 미커밋이며 원격 푸시 없음.

## 실행 상세 검색 로컬 병합 완료 (2026-11-04)

- 사용자 승인으로 ef79d2c를 로컬 develop에 충돌 없이 병합했다. 관련28개/build/diff 재검증 통과, 이전 전체158개 및 브라우저 근거 유지. 제품 코드는 기능 커밋과 동일하고 이 기록만 추가한다. 원격 푸시·원본 worktree 변경 없음.

## 실행 상세 케이스 검색 완료 (2026-11-04)

- 수집된 caseReference/caseId의 대소문자 무시 부분검색을 상태 필터와 결합했다. Enter/버튼 적용·검색만 초기화, 최대200자 정규화, caseSearch URL로 reload/back/forward 복원을 지원한다. 다른 Run/상세 닫기/목록 조건 변경은 검색을 초기화한다. 원문 응답을 검색하거나 재실행 대상을 바꾸지 않는다.
- 검증: frontend158개(34파일,worker2), production build, diff 검사 통과. 신규3개 회귀에서 한글/특수문자/대소문자·caseId·빈 결과·식별자 없는 과거항목 보존·초기화·URL 복원·추가 API 호출 없음/POST0회를 확인했다. backend 변경·전체 Python 재실행 없음.
- 실제 브라우저: 격리 DB의 합성 이력으로 대문자 CONTRACT 검색1개 직접진입/reload, timeout Enter검색1개, back/forward 결과 복원, 계약필터와 결합한 빈 결과, 검색만 초기화 후 계약필터 보존을 확인했다. 콘솔 오류/경고0. 실제 대상 호출/운영 인증/부하 측정이 아니다. [화면](execution-detail-search.png).
- Git: 이전 URL복원407ac2c·로컬 develop병합7e25788 완료. 새 feature/execution-detail-search에 검색 변경만 미커밋으로 남긴다. 원격 푸시·원본 worktree 변경 없음. 브라우저 검증 탭 종료.

## 실행 상세 케이스 검색 시작 (2026-11-04)

- develop7e25788에서 feature/execution-detail-search 분기. caseReference/caseId 부분 문자열 검색(대소문자 무시)을 상세 상태 필터와 AND 결합한다. Enter/검색 버튼 적용 및 검색만 초기화 제공. 원문 응답·secret 검색은 하지 않는다.
- caseSearch query는 최대200자/앞뒤 공백 제거, 선택 Run에 연결한다. 필터 변경 시 검색 유지, 다른 Run/닫기/목록 조건 변경 시 초기화, reload/back/forward 복원. 표시만 바꾸며 기존 재실행 대상/API/DB 계약 유지.
- 검증은 혼합 조건·한글/특수문자·빈 결과·초기화·URL 복원·추가 호출/자동 실행 없음 회귀, 전체 frontend/build 및 실제 브라우저로 수행한다. 새 변경은 미커밋이며 원격 푸시 없음.

## 상세 필터 URL 복원 로컬 병합 완료 (2026-11-04)

- 기능 커밋407ac2c를 로컬 develop에 충돌 없이 병합했다. 제품 코드는 검증한 기능 커밋과 동일하고 이 완료 기록만 추가한다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## 상세 필터 URL 복원 커밋 준비 (2026-11-04)

- 사용자 승인으로 상세 필터 URL 복원 변경을 커밋·로컬 develop 병합한다. 관련25개/3파일 및 build 재검증, diff 검사 통과. 직전 전체155개와 실제 브라우저 검증은 이전 완료 기록을 유지한다. 원격 푸시 없음.
- 다음 단계는 실행 상세 케이스 이름·경로 검색과 URL 복원이며 새 브랜치에 미커밋으로 남긴다.

## 실행 상세 필터 URL 복원 완료 (2026-11-04)

- outcomes=failures|contract를 선택 Run URL에 연결했다. 기본/잘못된 값과 Run 없는 값은 전체로 처리한다. 상세 필터 변경은 목록 조건과 Run 유지, 다른 Run 열기/닫기/목록 조건 변경은 초기화한다.
- 검증: frontend155개(34파일,worker2), production build, diff 검사 통과. 신규 라우터1개·통합화면1개가 직접진입/재마운트/popstate·잘못된 값·필터 변경 시 API 추가 호출 없음·POST0회·닫기/Run 전환 초기화를 확인했다. 백엔드 변경 및 전체 Python 재실행 없음.
- 실제 브라우저: 격리 임시 DB의 합성 이력2개로 계약실패 직접 URL→reload 유지, 실패5개로 전환→back 계약1개→forward 실패5개, 다른 Run 전체 초기화, 상세 닫기 시 outcomes/run 제거와 days30 보존을 확인했다. 콘솔 오류/경고0. 사용자 데이터·운영 인증·실제 대상 호출은 사용하지 않았다. [화면](execution-detail-filter-url.png).
- 기존 변경 addb634 및 로컬 develop 병합 d43fc42 완료 후 새 feature/execution-detail-filter-url에 이 단계만 미커밋으로 남긴다. 원격 푸시 없음.

## 실행 상세 필터 URL 복원 시작 (2026-11-04)

- develop 병합 d43fc42에서 feature/execution-detail-filter-url 분기. outcomes=failures|contract를 선택 run에 연결한다. 기본 all/잘못된 값은 전체, run이 없으면 필터를 무시한다.
- 상세 필터 변경은 목록 조건과 Run ID 유지, 다른 Run 열기·상세 닫기·목록 조건/페이지 변경은 초기화한다. reload/back/forward에서 복원하고 GET/POST 추가 실행을 유발하지 않는다.
- 관련 라우터/통합 화면 회귀·전체 frontend/build 및 격리 DB 실제 브라우저 검증을 진행한다. 새 변경은 미커밋, 원격 푸시 없음.

## 실행 상세 필터 로컬 develop 병합 완료 (2026-11-04)

- 기능 커밋 addb634(계약 요약·대시보드 URL 복원·실행 상세 필터)을 로컬 develop에 충돌 없이 병합했다. 검증한 제품 코드와 동일하며 이 완료 기록만 추가한다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.
- 커밋 전 frontend153개, 관련 Python 이력10개, production build 및 diff 검사 통과. 전체 Python 재실행은 아니며 실제 브라우저 근거는 기존 단계별 기록을 유지한다.

## 실행 상세 필터·계약 요약·URL 복원 커밋 준비 (2026-11-04)

- 사용자 승인으로 feature/contract-result-summary의 연결된 미커밋 변경을 커밋하고 로컬 develop에 병합한다. 계약 요약과 대시보드 URL 복원은 상세 필터의 기존 기반으로 함께 반영한다. 원격 푸시·원본 worktree 변경 없음.
- 관련 Python 이력10개 재검증 통과. frontend 전체/build와 diff를 확인한 후 커밋한다. 기존 실제 브라우저 검증 기록은 각 단계의 실행 날짜와 범위를 유지한다.
- 다음 단계는 상세 항목 필터의 URL 복원이며 새 feature 브랜치에서 미커밋으로 진행한다.

## 실행 상세 실패 항목 필터 완료 (2026-11-04)

- 전체/실패·오류·중단(failed,error,timeout,cancelled)/유효한 계약 실패 필터와 수집·표시 건수를 추가했다. 계약 요약 없음/확인 불가는 전체에서 확인하며 실패로 추정하지 않는다. Run 전환은 전체로 초기화, 필터는 URL에 저장하지 않는 화면 내 임시 상태다. 재실행 대상은 기존 서버 판정을 유지한다.
- 검증: frontend 전체153개(34파일,worker2), production build, git diff --check 통과. 신규2개 회귀가 혼합 상태·잘못된 요약·빈 결과·Run 전환·필터 변경 시 POST 없음·명시 재실행 body 불변을 확인한다. backend 변경 및 전체 Python 재실행은 없다.
- 실제 브라우저: 임시 DB의 합성 이력으로 전체6→실패/오류/중단5→계약실패1, 빈 상세0, Run 전환 전체 초기화를 확인했다. 콘솔 오류/경고0. 실HTTP 실행·운영 OIDC·부하 측정 증거가 아니다. [화면](execution-detail-filter-browser.png).
- 작업 중 최초 테스트 추가 명령은 web/ 기준 경로를 중복해 파일을 찾지 못했다. 경로를 바로잡아 추가했고 최종153개가 통과했다.
- 기존 계약 요약/URL 복원 미커밋 변경과 원본 worktree를 보존했다. feature/contract-result-summary 유지, 커밋·병합·푸시 없음.

## 실행 상세 실패 항목 필터 시작 (2026-11-04)

- OBS-1 후속: 수집된 상세에서 전체/실패·오류·중단/유효한 OpenAPI 계약 실패를 선택하고 건수를 표시한다. 요약 없음·확인 불가는 계약 실패로 추정하지 않는다.
- Run 전환은 전체로 초기화하고 필터는 화면 내 임시 상태로 둔다. 서버 재실행 대상·API·저장 계약은 유지한다. 기존 미커밋 계약 요약/URL 복원과 원본 worktree를 보존하며 커밋·병합·푸시는 하지 않는다.
- 검증 계획: 상태 혼합·빈 결과·과거 이력·Run 전환·재실행 불변 회귀, frontend 전체와 production build.

## 실행 대시보드 URL 상태 복원 완료 (2026-10-28)

- 프로젝트·기간·결과·검색·페이지·선택 Run ID를 URL에 보존한다. 상세 열기/닫기는 목록 조건 유지, 조건 변경은 첫 페이지/상세 닫힘, back/forward/reload는 URL 상태로 조회한다. 직접 복원에서 POST/자동 재실행은 없다.
- 검증: frontend151개(34파일,worker2)·build·diff 통과, 관련 Python 이력10개 통과. 독립 작성5개 및 read-only diff 점검으로 direct URL·상세·필터·페이지·지연 응답·404복귀/POST0회와 API 입력한도를 확인했다. 별도 Workspace 전환 회귀도 포함한다.
- 실제 브라우저: 합성 이력28개+실제 child runner1개로 URL직접진입·page2 목록7개·상세/reload·닫기/back/forward·기간/검색·없는 run404 후 필터보존을 확인했다. 총 이력29개 유지, 콘솔 오류/경고0. 합성 이력을 실제 부하/성공률 측정으로 해석하지 않는다.
- 범위: KPI/추이 집계·서버 권한·계약 판정·실패 재실행 정책 변경 없음. 이번 backend runtime 변경 및 전체 Python 재실행 없음. Workspace 전환은 UI/서버 테스트로 확인했으며 운영 OIDC 브라우저 검증은 별도다.
- 자료: [계약/검증](dashboard-url-state.md), [화면](dashboard-url-restoration.jpg). 기존 계약 요약 미커밋 변경을 보존했고 feature/contract-result-summary·HEAD/develop8debdee 유지. 커밋·병합·푸시 없음. 브라우저 탭 및 임시 서버 정상 종료(exit0) 완료.

## 실행 대시보드 URL 상태 복원 시작 (2026-10-28)

- 다음 범위: 기능 실행 대시보드의 프로젝트·기간·결과·검색·페이지 및 선택한 Run ID를 URL에 저장하고 reload/back/forward로 복원한다. 기존 계약 요약 미커밋 변경을 보존하며 동일 feature/contract-result-summary에서 이어간다. 커밋·병합·푸시 없음.
- 조건 변경은 페이지1·상세 닫힘, 상세 열기/닫기는 기존 조건 유지. API의 days7/30/90·status열거·page1~1000000·search200자 제한에 맞춘다. 다른 화면 URL에 이 조건을 섞지 않는다.
- 기존 KPI/추이 집계 범위와 서버의 Workspace 권한·실패 재실행 경로는 유지한다. URL은 접근 권한이 아니며 없는/타 Workspace Run ID는 기존 상세 오류로 처리한다.
- 검증: 독립 read-only 점검과 라우터/화면 회귀, 입력경계·직접 URL·지연 응답·상세 복원·Workspace 전환, build 및 실제 브라우저를 확인한다.

## 계약 결과·이력 요약 표시 완료 (2026-10-24)

- RunResult와 ExecutionDetail에 공통 계약 통과/실패·문제 개수·명세 SHA-256 표시를 추가했다. 과거/비활성/미수집은 요약 없음, 잘못되거나 모순된 metadata는 확인 불가로 구분하며 raw 값은 렌더링하지 않는다. 전체 실행/assertion 판정과 계약 판정은 별개로 유지한다.
- 검증: 전체 Python598개(skip0,110.074초), 이력 집중10개, 전체 frontend143개(33파일,worker2), production build 통과. 최종 focus 간격 보완 후 관련8개·build 통과. DB 재오픈/API 요약 보존·원문 배제·기존 재실행·지연 응답·legacy/malformed 표시를 확인했다.
- 브라우저: 실제 저장 pipeline3개의 실패1개/통과0개/요약 없음, digest 펼침·새로고침 재조회, 기존 실패 대상 재실행과 동일한 실시간 요약 확인. 최종 Enter 펼침·콘솔 오류/경고0 확인. [계약/검증](contract-result-summary.md), [화면](contract-result-summary-browser.jpg).
- 처음 커밋 전 자동권한 검토3건 시간초과는 미실행 확인 후 같은 명령을 한 번 재요청해 통과했다. 제품 테스트 실패 없음. 기존 부하 실패/unknown·운영 배포·전체캠페인은 변경하지 않는다.
- Git: 저장 케이스 계약검증 커밋529e466·develop 병합8debdee 완료. 새 feature/contract-result-summary는8debdee 기준 미커밋/미병합이며 원격 푸시·원본 worktree 변경 없음. 브라우저 탭 및 임시 서버 정상 종료(exit0) 완료.

## 계약 결과·이력 요약 표시 시작 (2026-10-24)

- 저장 케이스 계약검증 커밋529e466·로컬 develop 병합8debdee 후 feature/contract-result-summary 생성. 새 변경은 미커밋/미푸시다.
- 범위: RunResult와 실행 이력 상세의 계약 통과/실패·문제 개수·검사 명세 SHA-256 공통 표시. 결과 없는 과거/비활성/중단 실행은 요약 없음, 잘못된 metadata는 확인 불가로 구분한다. 기존 실행 전체 판정·assertion·실패 대상 재실행은 유지한다.
- 데이터 경계: 이미 저장된 valid/issueCount/documentDigest만 사용한다. 실제/기대 응답·secret·원문 진단 및 현재 명세를 새로 읽지 않는다. 검증 계획은 UI 상태 조합/레거시/불완전 metadata/갱신·재실행, 이력 API·DB 보존·격리, 전체 frontend/build 및 실제 브라우저다.

## 저장 케이스 계약검증 로컬 병합 완료 (2026-10-24)

- 커밋 `529e4663f1f333b43a98137b246139c19c4ad81a`를 충돌 없이 로컬 develop에 병합했다. 완료 기록만 추가하며 검증한 제품 코드와 동일하다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## 저장 케이스 계약검증 커밋·병합 준비 (2026-10-24)

- 사용자 승인으로 저장 케이스 계약검증을 커밋하고 로컬 develop에 병합한다. 원격 푸시 없음.
- 현재 diff와 기존 전체 Python597개/build/생성 기록 확인. 집중6개·전체 UI138개(worker2) 재검증 통과. 자동 권한 검토가 처음 시간초과되어 미실행을 확인하고 같은 명령을 한 번 재요청해 성공했다.
- 다음은 OBS-1/OAS-2 실행 결과·이력의 계약 요약 표시다. 새 브랜치에 미커밋으로 남긴다.

## 저장 케이스 OpenAPI 계약검증 완료 (2026-10-24)

- 구현: contract_validation opt-in 설정·편집 UI·API 저장/복원, Workspace별 프로젝트 명세의 케이스 단위 snapshot, 웹/CLI 공통 runner와 pipeline의 추가 응답 계약 판정을 연결했다. 기존 status/body/assertion/시간 제한은 보존했다.
- 경계: malformed 설정·명세/operation은 대상 호출 전 configuration_error, 응답 불일치는 contract_failed. JSON/JUnit·이력에는 valid/issueCount/documentDigest만 추가하며 원문·token은 추가 저장하지 않는다. 재시도는 동일 명세snapshot이고 pipeline 전체 원자snapshot은 비범위다.
- 검증: 최종 전체 Python597개(skip0,194.581초), 집중6개(실HTTP·CLI·pipeline·Workspace/API), frontend138개(worker2), production build·생성 최신성·diff 검사 통과. 이전596개 및597개 실행 기록도 보존하고 마지막 malformed docs_file guard 보완 후 전체597개를 다시 통과했다.
- 실제 브라우저: opt-out HTTP200은 기존 통과, opt-in 저장/reload 후 같은 body는 schema_type/contract_failed, 저장 케이스를 쓰는 pipeline도 실패. 정상 fixture URL로 저장 후 pipeline 성공. 두 job result의 같은 명세digest·valid false/true·issueCount1/0 및 원문 비노출 확인. 콘솔 오류/경고0.
- 실패/조치: 최초 테스트 fixture의 중괄호 오류를 검증된 helper 사용으로 해결했다. 저장 완료 안내가 기존 명세 재조회 안내로 바뀌어 browser wait가 실패했으나 reload/실행으로 저장을 확인했다. 커밋 전 기존 CaseList 테스트1개의 기본 병렬 실패는 단독5개/worker2 전체135개 통과로 구분했고 단언은 변경하지 않았다.
- 자료: [설정/판정/검증](saved-case-contract-validation.md), [실행 화면](saved-case-contract-result.jpg). 로그 /tmp/saved-contract-*.log. 임시 브라우저와 검증 서버 정상 종료.
- Git: server 변수·상대URL 커밋0de1fca 및 develop 병합a51c176 완료. 새 feature/saved-case-contract-validation은 a51c176 기준 미커밋/미병합이며 원격 푸시·원본 worktree 변경 없음. 배포·운영 공급자·전체 LT 및 기존 부하 실패/unknown은 별도다.

## 저장 케이스 OpenAPI 계약검증 시작 (2026-10-24)

- server 설정 커밋0de1fca·develop 병합a51c176 완료 후 feature/saved-case-contract-validation 생성. 이번 새 변경은 미커밋/미푸시다.
- 범위: 케이스 contract_validation opt-in 설정과 편집 UI, 저장된 프로젝트 명세의 실행당 snapshot, CLI/웹 공통 runner 응답 계약 판정. 같은 케이스를 실행하는 파이프라인에도 적용한다. 기존 status/body/assertion은 계속 검사한다.
- 실패 경계: 잘못된 명세/설정/operation은 호출 전에 configuration_error, 실제 응답 계약 불일치는 failed. 보고서는 valid·issueCount·명세digest만 남기며 body·token·변수값을 추가 저장하지 않는다.
- 검증: 단위/실HTTP·CLI·pipeline·재시도 snapshot·설정API/Workspace 경계·보고서 비노출·UI 저장/복원·전체 회귀/build/생성 및 브라우저.

## Server 설정 로컬 develop 병합 완료 (2026-10-24)

- 커밋 `0de1fcabc10a0f46324efd8bd2668313806ce1b0`를 충돌 없이 develop에 병합했다. 이 기록만 병합 커밋에 추가했으며 제품 코드가 기능 커밋과 동일하다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## Server 설정 커밋·병합 준비 (2026-10-24)

- serverVariables와 contractDocumentUrl 변경을 사용자 승인으로 커밋·로컬 develop 병합한다. 원격 develop fb75a46 확인, 푸시 없음.
- 계약/실HTTP 집중40개 재실행 및 diff 검사 통과. frontend 기본 병렬 실행은 기존 CaseList 삭제 후 첫 페이지 테스트1개 실패(134통과)였고 단독5개 및 worker2 전체135개는 통과했다. 단언/대기제한을 바꾸지 않았고 첫 실패 이력을 보존한다. 기존 전체 Python591개·build·생성검사 통과 기록도 확인했다.
- 다음 단계는 저장 케이스의 opt-in OpenAPI 응답 계약검증이며 공통 runner를 통해 파이프라인에도 적용한다. 새 단계는 미커밋으로 유지한다.

## OAS-2 상대 server 경로 해석 완료 (2026-10-24)

- 빠른 호출의 선택적 contractDocumentUrl UI/API를 추가했다. 변수 치환 뒤 문서 위치 기준 상대/상위 경로를 해석하며 metadata URL 다운로드와 실제 요청 URL 변경은 하지 않는다. 기준이 없으면 기존 상대 경로 거부를 유지한다.
- 검증: 계약/API 집중40개·실HTTP, 전체 Python591개(skip0,188.541초), frontend135개(31파일), production build·생성 최신성·diff 통과. 기준 입력경계·scope·끝 슬래시·변수 결합·alias 우회 금지·값 비노출·기준 URL 미접속을 포함한다.
- 실제 브라우저: 기준 없는 상대 server는 실패, 기준+default v1 및 명시값v2 통과. 잘못된 기준/file URL 거부 후에도 대상 카운터3회 그대로이고 문서 경로 조회0건. 프로젝트 변경 초기화·콘솔 오류/경고0 확인. [상세 계약](openapi-contract-validation.md), [화면](openapi-relative-server-browser.jpg).
- 첫 공식 명세 조회 연결 실패는 재조회로 해결했다. 구현 테스트 실패 없음. 다중 외부 문서별 기준 추적/저장 케이스 자동 계약검증·운영 배포·전체 부하는 별도이며 과거 실패/unknown은 유지한다.
- 기존 serverVariables 미커밋 작업을 보존하고 feature/openapi-server-variables에서 이어갔다. HEAD/develop d5dd592 유지, 이번 커밋·병합·푸시 없음. 원본 worktree 변경 없음. 브라우저 탭은 종료했고 임시 서버도 정리한다.

## OAS-2 상대 server 경로 해석 시작 (2026-10-24)

- 다음 단계: 빠른 호출의 선택적 contractDocumentUrl로 문서 위치에 상대적인 server URL을 해석한다. 기준 URL은 다운로드하지 않고 실제 호출 URL도 바꾸지 않는다. 원격 참조/명세 가져오기·저장 케이스 자동 검증은 비범위다.
- 기존 feature/openapi-server-variables의 미커밋 명시값 변경을 보존하고 같은 OAS server 설정 작업으로 이어간다. 커밋·병합·푸시 없음.
- 기준: OpenAPI Server Object의 문서 위치 기준 상대 URL 규칙(https://spec.openapis.org/oas/v3.1.0.html#server-object). 변수 치환 후 RFC3986 URL 해석, 명시적 기준이 있으면 project base alias로 우회하지 않는다. 기준 URL이 없으면 이전의 상대 경로 거부 정책을 유지한다.
- 검증 계획: 3.0/3.1·상대/상위/루트/절대 경로·server 우선순위·변수·기준 입력 제한·비노출·실HTTP·UI·전체 회귀/build 및 실제 브라우저.

## OAS-2 server 변수 명시값 완료 (2026-10-24)

- server 매칭 커밋b47709b·로컬 develop 병합d5dd592 완료. 새 feature/openapi-server-variables에서 빠른 호출 serverVariables map 및 JSON 입력 UI를 구현했다. 실제 URL은 변경하지 않고 응답 경로 매칭에만 적용한다.
- validateContract=true에서만 지정한다. 최대32개 문자열, 이름1~128자·값512자 이하이며 제어문자는 거부한다. 미지정 변수는 default, 빈 map도 기존 동작이다. 사용되지 않는 변수·enum 위반·매칭 실패·형식 오류는 입력값 없는400으로 대상 호출 전에 차단한다. 명시값 사용 시 project base alias로 우회하지 않는다.
- UI에서 검증 해제 시 전송하지 않고 프로젝트/환경 변경 시 초기화한다. 프로젝트/케이스/이력에 값을 추가 저장하지 않는다. 소유권·인증 정책은 기존대로 적용하며 일반 상대 server 해석과 저장 케이스 자동 계약검증은 후속이다.
- 검증: 계약/API 집중34개(실제 loopback HTTP 포함), 전체 Python585개(skip0,104.414초), frontend133개(31파일), production build·생성 최신성·diff 검사 통과. 부분 치환·변수 scope·모호함·값 비노출·입력경계·UI 초기화를 포함한다.
- 실제 브라우저: 격리 로컬 fixture에서 default v1 및 명시값v2의 HTTP200/계약 통과, v3/API400·잘못된JSON/UI 차단을 확인했다. 대상 카운터는 성공2회 이후 증가하지 않았다. 프로젝트 전환 초기화 및 콘솔 오류/경고0 확인. [화면](openapi-server-variables-browser.jpg).
- 실패/보완: 모호함 fixture가 실제 중복이 아닌 v1 기본값을 사용해1개 실패했고 v2로 바로잡았다. 신규 UI2개 label 조회 실패는 textarea의 명시적 접근성 이름으로 수정했다. npm root 실행은 web/에서 재실행했다. 모두 수정 후 위 검증을 통과했다. 문서 쓰기 자동검토 시간초과는 같은 작업을 재요청했다.
- 로그: /tmp/server-vars-focused-python.log, /tmp/server-vars-python-all.log, /tmp/server-vars-web-all.log, /tmp/server-vars-build.log, /tmp/server-vars-generated-check.log.
- 반영: 새 기능은 d5dd592 기준 미커밋/미병합, 원격 푸시 및 원본 worktree 변경 없음. 운영 배포·전체 부하 캠페인·기존 실패/unknown은 변경하지 않는다.

## OAS-2 server 변수 명시값 시작 (2026-10-24)

- server 매칭 커밋b47709b·develop 병합d5dd592 완료. 새 feature/openapi-server-variables에서 명시값 UI/API를 개발하며 새 변경은 미커밋/미푸시로 남긴다.
- 범위: 빠른 호출 validateContract의 선택적 serverVariables 문자열 map, 실제 URL 자동 변경 없이 effective server 매칭에만 사용. 미지정 변수는 default, enum 위반/사용되지 않는 변수/형식 오류는 값 비노출 오류로 거부한다. 기본값 기존 호출은 호환 유지한다.
- 검증: 분리된 operation/server의 변수 scope, 입력경계·원문 비노출·실HTTP 및 API 호출 전 차단, UI 전송·프로젝트/환경 변경 초기화, 전체 회귀/build/생성 및 브라우저 검증.

## OAS-2 server 매칭 로컬 병합 완료 (2026-10-24)

- 커밋 `b47709b420713ab99d60269b7ec767fb92d82f2b`를 충돌 없이 로컬 develop에 병합했다. 완료 문서만 추가했으며 제품 코드는 검증한 기능 커밋과 같다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## OAS-2 server 매칭 커밋·병합 준비 (2026-10-24)

- 사용자 승인으로 server 매칭 변경을 커밋하고 로컬 develop에 병합한다. 중단된 요청에서 추가 Git 반영은 없었다. 계약/실HTTP 집중28개 재검증·diff 검사 통과, 기존 전체579개 기록 확인. 원격 develop fb75a46 확인, 푸시 없음.
- 다음은 빠른 호출의 server 변수 명시값 UI/API이며 호출 URL 자동 변경 없이 매칭에 적용한다. 새 단계 변경은 별도 기능 브랜치에 미커밋으로 유지한다.

## OAS-2 server 경로 매칭 보완 완료 (2026-10-23)

- 변경: operation→path→root 서버 우선순위, 변수 default 치환, operation별 prefix·경계 처리, 빈 override·모호함·해석 불가 서버의 명시적 실패를 구현했다. project base alias는 명시적 하위 override가 없을 때만 적용한다.
- 검증: 집중28개, 실제 loopback HTTP 호출, 전체 Python579개(skip0,83.573초), 생성 최신성·diff 통과. React 변경 없음; 복구 시 frontend131개/build 통과. 실제 브라우저에서 JSON HTTP200의 올바른 경로 통과/상위 경로 실패와 콘솔 오류0을 확인했다.
- 환경 이력: tmp 원본 소실을 Git 기준 및 기록에서 복구·지속 경로로 이전한 뒤 파이프라인 재검증570개/131개와 브라우저 확인을 완료했다. 기록 스크립트 직접 replay는 자동 검토에 거절돼 scratch 결과와 SHA를 확인한 patch 적용으로 해결했다. 임시 OAS fixture의 구문 및 route 순서는 제품 코드와 별개로 수정하고 재검증했다.
- 범위: 변수 default 외 사용자 선택, 문서 위치 기반 상대 server, 저장 케이스 자동 계약검증, 전체 부하/배포는 남아 있다. 과거 부하 실패/unknown을 바꾸지 않는다. [상세 계약/검증](openapi-contract-validation.md).
- Git: 파이프라인 커밋9d63751·develop 병합f6b890f 완료. 현재 feature/openapi-server-matching은 f6b890f 기준 미커밋이다. 원격 푸시·원본 저장소 변경 없음. 작업 경로는 `/Users/kwondaehoon/Desktop/Project/api-develop-studio-worktrees/pipeline-list`이다.

## OAS-2 server 경로 매칭 보완 시작 (2026-10-23)

- 기준: 파이프라인 커밋9d63751·로컬 develop 병합f6b890f에서 feature/openapi-server-matching 생성. 새 변경은 미커밋, 원격 푸시 없음.
- 범위: 빠른 호출 응답 계약 검사에서 operation→path→root server 우선순위 및 선언된 변수 기본값 치환, prefix 경계·모호함 차단. project base URL alias는 명시적 operation/path override가 없는 경우에만 사용한다.
- 비범위: 사용자 지정 server 변수 선택 UI/API, 문서 위치 기준 상대 URL 해석, 원격 명세 호출, 저장 케이스/파이프라인 자동 계약검증. 현재 함수에 문서 위치가 없으므로 `/`로 시작하지 않는 상대 server는 안전하게 실패한다. host/origin 검증과 실제 호출 소유권 정책은 별도다.
- 계획: OpenAPI3.0/3.1·각 override/default/모호함/민감값 비노출 fixture와 실제 HTTP 빠른 호출 계약 검사, 전체 Python 회귀를 수행한다. [명세](https://spec.openapis.org/oas/v3.1.0#operation-object)를 기준으로 한다.

## 파이프라인 로컬 develop 병합 완료 (2026-10-23)

- 통합 커밋 `9d63751afa29c64da13d6839a31d4218ccedc256`를 충돌 없이 로컬 develop에 병합했다. 이 기록은 병합 커밋에 포함한다. 제품 코드는 검증한 통합 커밋과 동일하다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## 파이프라인 복구·커밋 전 재검증 (2026-10-23)

- 이전 /tmp worktree의 연결 파일과 소스가 없어져 Git index의 기준508개 파일을 누락 위치에만 복구하고 지속 경로 `/Users/kwondaehoon/Desktop/Project/api-develop-studio-worktrees/pipeline-list`로 이동했다. 원본 저장소의 미커밋 P1 변경은 건드리지 않았다.
- 자동 승인 검토가 기록 스크립트 직접 재실행을 거절했다. 별도 scratch에서 이전 편집 결과를 재구성하고 대상 SHA/깨끗한 기준/diff를 확인한17개 파일 patch만 적용했다. 생성 코드는 원본 OpenAPI로 재생성했다. 이전 PNG는 소실되어 새 로컬모드/임시 DB 화면 증거로 교체했다.
- 새 검증: Python570개(skip0,90.170초), frontend131개·production build 통과. 브라우저에서45개 중 첫20개·다음 페이지·reload 및 검색7개 확인. 과거 OIDC/두 Workspace 검증은10월16일 기록이며 오늘 다시 실행한 것으로 표시하지 않는다.
- 사용자 승인에 따라 파이프라인을 커밋하고 develop에 병합한다. 원격 푸시 없음. 다음 OAS-2 server 경로 매칭 보완은 새 브랜치에 미커밋으로 남긴다.

## 파이프라인 목록 개발·검증 완료 (2026-10-16)

- 구현: 프로젝트/Workspace 내 bounded keyset 페이지, 이름/파일명 검색, 파일명 양방향·최신 생성순·페이지 크기·URL reload/back 복원. 단계/secret은 목록에 반환하지 않고 기존 편집·실행/전체 케이스 선택을 보존했다.
- 보완: 프로젝트 로딩 중 빠른 섹션 이동에서 아직 갱신되지 않은 선택 상태를 사용할 수 있어 URL project를 우선하도록 수정하고 App 회귀를 추가했다.
- 검증: 최종 Python570개(skip0,148.693초, PostgreSQL 포함), frontend131개(31파일), production build, 생성 최신성·diff 검사 통과. 집중 목록12개·화면16개 통과.
- 실제 브라우저: 팀A45개20→20→5·이전/reload·검색7개·정렬/크기/Enter/back, 기존 편집기 케이스 선택·단계 저장, 다른 프로젝트1개와 삭제 후0개, 팀B3개/검색1개 격리 확인. 초기11개 요청은 모두 bounded 목록이며 콘솔 오류/경고0개. 단계 이름 없는 저장은 정상 거부 후 이름을 입력해 저장했고 삭제 CDP 지연은 재클릭 없이 완료 화면으로 확인했다.
- 자료: [계약·검증](pipeline-list-pagination.md), [화면](pipeline-list-pagination-browser.jpg). 실제 파이프라인 실행 성공·부하 캠페인·운영 배포를 이번 검증으로 주장하지 않는다. 기존 부하 실패/unknown은 보존한다.
- 반영: 케이스 커밋49a842f·develop 병합e83778e 완료. 새 feature/pipeline-list-pagination은 e83778e 기준 미커밋이며 커밋/병합·원격 푸시 없음. 원본 worktree 보존. 검증용 인증 로그아웃·탭 종료 후 임시 서버를 정리한다.

## 파이프라인 목록 페이지네이션·검색·정렬 시작 (2026-10-16)

- 케이스 목록 커밋49a842f·로컬 develop 병합e83778e 완료. 새 feature/pipeline-list-pagination은 이 develop 기준이며 새 변경은 미커밋으로 유지한다. 원격 푸시 없음.
- 범위: 프로젝트 내 파이프라인 DB keyset 페이지, 이름/파일명 검색, 파일명 양방향·최신 생성순, URL 페이지 크기/커서 및 reload/back. 기존 편집·실행·케이스 선택·예제 읽기전용은 유지한다.
- 계획: 공통 조회에 pipelines scope 추가, 목록 초기 전체 case/pipeline 요청 제거, 선택 화면으로 이동할 때 기존 목록 유지. SQLite/PostgreSQL/API·화면 회귀, 전체 테스트/build/생성, 실제 브라우저 검증을 수행한다.

## 케이스 목록 로컬 develop 병합 완료 (2026-10-16)

- 케이스 목록 커밋 `49a842faabf160ce1df69b9f19c4b3912ff69299`를 로컬 develop에 충돌 없이 병합했다. 완료 기록은 병합 커밋에 포함한다. 검증 코드와 동일하며 문서만 추가했다.
- 원격 푸시·원본 worktree 변경·브랜치 삭제 없음. 다음 파이프라인 목록은 이 기준에서 새 기능 브랜치로 진행한다.

## 케이스 목록 커밋·병합 준비 (2026-10-16)

- 사용자 승인으로 케이스 목록 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시 없음.
- 현재 변경과 기존 전체 Python566개/build/생성 검증 기록을 확인하고 목록 집중9개·frontend전체124개·diff 검사를 다시 통과했다. 원격 develop은 fb75a46이다.
- 다음은 프로젝트 내 파이프라인 목록 페이지네이션·검색·정렬이며 새 브랜치에 미커밋으로 유지한다.

## API 케이스 목록 검증 완료 (2026-10-15)

- 구현: 선택 프로젝트/Workspace 내 DB keyset 페이지, 이름/API 검색, 정확한 태그 필터, 파일명 양방향·최신생성순, 페이지 크기, URL reload/back 복원을 구현했다. 프로젝트와 공통인 조회만 공유하고 기존 project cursor 형식은 보존했다.
- 기존 흐름 보존: 케이스 목록 초기 전체 조회 제거, import/export 패널을 열 때 전체 export 후보 지연 조회, 저장/삭제 후 페이지와 후보 갱신, 파이프라인 편집기 전체 케이스 선택 유지. 예제 읽기 전용·기존 케이스 경로/실행 계약 유지.
- 최종 검증: Python566개(skip0,85.568초), frontend124개(30파일), production build, 생성 최신성·diff 검사 통과. 집중 SQLite/API9개·PostgreSQL2개·화면19개·P1호환9개 통과.
- 실패/보완: 첫 전체 Python565개 중 P1 테스트1개는 대역 요청의 query_params 누락으로 오류였다. 대역 구조를 맞추고 진단 래퍼의 새 페이지 handler 위임을 추가한 뒤 전체566개 통과. 기존 부하 계측 결과는 바꾸지 않는다.
- 실제 브라우저: 케이스45개20→20→5·이전/reload·한글+auth4개·정렬/크기/Enter/back, 전체45개 export/cURL, preview/apply 후 최신순 추가와 삭제 갱신, 편집기 진입/back, pipeline45개 선택, 타 프로젝트1개/팀B3개·auth2개 격리 확인. 페이지조작10회 동안 전체 케이스 조회0회. 삭제 클릭 CDP timeout 후 재클릭 없이 완료 상태를 확인했고 콘솔 오류/경고0개였다.
- 자료: [계약·검증 기록](case-list-pagination.md), [화면 증거](case-list-pagination-browser.jpg). 로그 `/tmp/case-pagination-*.log`. 임시 인증 로그아웃·탭 종료·검증 서버 정리 완료.
- Git: 프로젝트 목록 커밋8939e2e 및 develop 병합ff6f18c 완료. 새 `feature/case-list-pagination`은 develop ff6f18c 기준 미커밋 변경이다. 새 변경 커밋/병합·전체 원격 푸시·원본 브랜치 삭제는 수행하지 않았다.

## API 케이스 목록 페이지네이션·검색·정렬 시작 (2026-10-15)

- 기준: 프로젝트 목록 병합 `ff6f18c`의 로컬 develop에서 `feature/case-list-pagination` 생성. 프로젝트 목록 커밋8939e2e·병합ff6f18c 완료, 원격 푸시 없음. 새 단계는 미커밋으로 유지한다.
- 범위: 선택 프로젝트 내 케이스 DB keyset 페이지, 케이스/API 이름 검색, 정확한 태그 필터, 케이스 파일명 양방향/최신생성순 정렬, URL 새로고침/뒤로가기 복원. 기존 실행·pipeline 선택·import/export 계약을 보존한다.
- 구현 계획: 프로젝트와 공통인 bounded 조회를 공유하되 case cursor는 Workspace·project·조건에 묶는다. 케이스 화면의 초기 전체 조회를 제거하고 import/export를 열 때에만 기존 전체 export 선택 목록을 읽는다. 파이프라인 편집기 전체 선택 목록은 유지한다.
- 검증 계획: SQLite/PostgreSQL 순회·동률·변경·격리·입력경계, React 조건/응답경합/삭제/import/export, 전체 회귀/build/생성 최신성 및 실제 브라우저를 확인한다.

## 프로젝트 목록 로컬 develop 병합 완료 (2026-10-15)

- 프로젝트 목록 커밋 `8939e2ef580913116fad4cc8ff385872f3b77bde`를 로컬 develop에 충돌 없이 병합했다. 이 기록은 병합 커밋에 포함한다. 검증한 제품 코드와 병합 결과는 동일하며 완료 문서만 추가했다.
- 원격 푸시·기존 원본 worktree 수정·브랜치 삭제 없음. 다음 API 케이스 목록 개발은 이 병합 이후 새 기능 브랜치에서 진행한다.

## 프로젝트 목록 커밋·develop 병합 준비 (2026-10-15)

- 사용자 승인으로 프로젝트 목록 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 제외한다.
- 현재 HEAD/develop `407983a`, 원격 develop `fb75a46` 확인. 변경 내용·diff 검사·기존 전체 Python560개/build/생성 검사 로그를 확인했으며 커밋 직전 프로젝트 집중5개와 frontend 전체117개를 재실행해 통과했다.
- 이어서 API 케이스 목록의 페이지·검색·태그·정렬을 새 feature 브랜치에서 개발한다. 새 단계 변경은 미커밋 상태로 남긴다.

## 프로젝트 목록 조회 개선 관련 기록 (2026-10-15)

- 프로젝트 화면의 DB keyset 페이지·이름/파일명 검색·정렬을 `feature/project-list-pagination`에서 구현·검증했다. [개발 기록](api-development-progress.md)과 [상세 계약](project-list-pagination.md)을 참조한다. 기존 부하 수치·실패/unknown은 변경하지 않았으며 이번 작업에서 부하 캠페인은 실행하지 않았다. 커밋·푸시 없음.

## 통합 커밋·로컬 develop 병합 완료 (2026-10-15)

- 사용자 승인으로 통합 커밋 `2c54a41b406bf90c6a9da039011ca3cc79148a3d`를 만들고 로컬 `develop`에 `--no-ff` 병합했다. 이 완료 기록은 병합 커밋에 포함한다. 원격 푸시는 수행하지 않았다.
- 검증: 커밋 전 Python 554개(skip 0, 137.740초), OAuth 집중5개·frontend111개·production build·생성 최신성·diff 검사 통과. 병합은 충돌 없고 검증한 통합 커밋과 제품 코드/테스트가 동일하며 완료 기록 문서만 추가했다.
- 보존: 작업 시작 당시 원본521개 파일 SHA와 대조해 변경0개를 확인했다. 통합 기능 브랜치와 원본 worktree는 모두 보존했다.
- checkout: 통합은 기존 roadmap-integration 경로, 로컬 develop은 `/tmp/api-studio-develop-20261015`이다. 기존 원본 저장소의 미커밋 변경은 그대로 유지했다.
- 범위: 이 기록은 로컬 Git 반영이다. 운영 인증/배포·전체 LT 캠페인·공통 pagination 등 잔여 개발 및 2026-10-13 브라우저 검증 범위를 변경하지 않는다.

## 통합 커밋 전 검증 완료 (2026-10-15)

- 전체 Python 554개(skip 0, 137.74초), OAuth 집중 5개, frontend 전체 111개, production build, OpenAPI 생성 최신성 및 diff 검사 통과.
- 실패/보완: 최초 frontend 110개 통과·1개 실패는 OAuth 초기 조회 중 비활성 연결 버튼을 클릭한 테스트 경합이었다. `OAuthProfileStatus.test.jsx`에서 버튼 활성화를 기다린 뒤 클릭하도록 보완했다. 관련 및 전체 재검증 통과, runtime 코드 변경 없음.
- 사용자 승인 범위는 통합 커밋과 로컬 develop 병합이며 원격 푸시 및 원본 브랜치 삭제는 제외한다. 실제 브라우저 증거는 2026-10-13 기록을 유지한다.

## 통합 커밋·로컬 develop 병합 시작 (2026-10-15)

- 승인: 사용자 요청으로 통합 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 수행하지 않는다.
- 기준 확인: 통합 HEAD·로컬 develop·읽기 전용 조회한 원격 develop이 모두 `fb75a467fba8c430f6da4a8e215d1c0f3b995470`이다. 기존 통합 변경 307개 파일과 원본 521개 파일의 현재 SHA를 확인했다.
- 검증: 현재 통합 소스의 전체 Python, frontend test/build, 생성 코드 최신성을 재실행 중이다. 기존 브라우저 증거는 2026-10-13 실행 기록이며 이번에 재실행한 것으로 표기하지 않는다.
- 병합 방식: 원본 worktree를 전환하거나 초기화하지 않고 별도 develop checkout에서 병합한다. 모든 원본 변경과 기능 브랜치를 보존한다.

## 실제 브라우저 통합 검증 및 최종 회귀 완료 (2026-10-13)

- 브라우저: 같은 5182 주소의 정상 in-app browser에서 임시 OIDC 로그인·로그아웃·재로그인 및 팀 A/B 전환을 확인했다. 과거 도구 차단은 재현되지 않았으며 사용자 설정 오류로 단정하지 않는다. 우회 없음.
- 가져오기: 팀 A에서 로컬 테스트 공급자의 공개 metadata GET을 cURL preview→항목 저장→새로고침 후 케이스 1개 유지로 확인했다. 팀 B에는 케이스 0개였다.
- 릴리스: `1.0.0-browser` 초안→발행(release revision 2)→고정 원본 조회를 수행했다. 포털 명세 revision 1과 source digest가 같고 뒤로 가기·새로고침·재로그인 후 보존됐다. 팀 B에는 발행 릴리스 및 팀 A SDK job이 없었다.
- 실제 다운로드: 포털 Python 릴리스 ZIP 32,707 bytes(SHA `602bcee3e7a59bfa78e6d58c93150dd021935c7cc24f8239c5703bb002e56bfc`), 일반 TypeScript ZIP 9,619 bytes(SHA `3feb07d9304a4356925049d345b7a1a4268da356b9dd2cc147978767e8952ba8`)를 브라우저 download 완료 이벤트와 Downloads 파일로 확인했다. 두 ZIP CRC 통과, 릴리스 manifest의 revision/source digest/릴리스 ID 일치. 일반 SDK 동일 job ID의 새로고침 복원도 통과.
- 실행 복원 경계: 가져온 케이스의 Run ID `cdfeef4b-b047-4294-9da4-0ce09b9d0a66`과 terminal 오류가 새로고침 후 복원됐다. fixture는 대상 소유권 증명이 없어 `configuration_error`로 정상 차단됐다. 이를 성공 API 실행으로 표시하지 않으며 앞선 실제 HTTP 성공 증거와 구분한다.
- 최종 검증: shutdown 수정 후 현재 통합 상태에서 **Python 554개(skip 0, 142.777초)**, 프런트엔드 **111개/27파일**, production build, OpenAPI 생성 최신성, `git diff --check` 통과. 과거 552개 결과는 수정 전 이력으로 보존했다. 로그는 `/tmp/roadmap-integration-final-{python,web,build,generated}.log`.
- 원본 확인: 이전 manifest 521개 중 P1 진행 문서 2개만 앞선 사용자 요청의 재검증 기록으로 달랐다. 이번 통합 계속 작업에서는 원본 worktree를 수정하지 않았다. 기존 통합 코드는 보존했고 발견된 제품 결함 및 제품 코드 수정 없음.
- 정리/반영: 임시 계정 로그아웃·브라우저 탭 종료·검증 서버 정상 종료(exit 0). 증거/계획/두 진행 문서와 스크린샷만 갱신했다. 브랜치 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 유지, 커밋·병합·푸시 없음.
- 남은 범위: 운영 공급자·배포·전체 LT 캠페인/SLO·공통 pagination 등은 여전히 별도다. 이번 결과는 지정된 로컬 통합 브라우저 흐름 검증이며 전체 로드맵 완료가 아니다.

## 새 채팅 브라우저 통합 검증 시작 (2026-10-13)

- 시작: 지정 통합 worktree의 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 및 미커밋 통합 변경을 확인했다. 기존 변경과 원본 worktree를 보존한다.
- 환경: 기존 임시 스크립트와 Python 환경을 확인하고, 사용자 데이터와 분리된 새 임시 DB/두 Workspace/OIDC 공급자를 같은 5182·5183 포트로 실행했다.
- 접근: 정상 `cua_repl` in-app browser로 5182 로그인 화면과 SSO 로그인 후 팀 A 프로젝트 목록을 확인했다. 이전 저장 권한 정책 거절은 이번 세션에서 재현되지 않았다. 다른 포트/브라우저/직접 명령 우회 없음.
- 기록 정정: 과거 기록의 사용자 설정 변경 필요 단정은 확인된 원인이 아니다. 사용자는 이미 항상 허용을 확인했으며 이번 정상 도구 접근은 성공했다.
- 진행: Workspace·import·release·portal·SDK 다운로드 및 새로고침/뒤로 가기/실행 복원을 실제 브라우저로 검증한다. 기존 552개 전체 Python은 마지막 shutdown 수정 전 결과임을 유지한다.

## 브라우저 차단 사유 재확인

- 사용자 재개 요청 후 기존 검증 주소 `http://127.0.0.1:5182`를 확인했으며, 브라우저 도구가 저장된 사용자 권한 설정에 의한 차단이라고 명시했다. 일반 채팅 승인이 부족한 상태가 아니라 저장된 사이트 차단 설정의 변경이 필요하다.
- 차단 해제 여부를 사용자에게 요청했다. 해제 답변 전 재접속·다른 브라우저·주소 변경·직접 브라우저 명령으로 우회하지 않는다. 제품 코드 변경·테스트 재실행·Git 게시 없음.

## 통합 SDK 실제 Java 취소·시간 초과 확인 (2026-10-13)

- 시작: 통합 계획의 실제 generator lifecycle 근거를 현재 feature/roadmap-integration에서 확인했다. 제품 코드는 변경하지 않았다.
- 검증: 임시3500 operation 명세의 Java 프로세스 실행을 관측한 뒤 취소(0.497초), 별도2초 deadline으로 timeout(2.062초)을 확인했다. 각 작업의 준비/Java 프로세스2개 모두 종료, 작업 임시 디렉터리0개, 게시 ZIP 없음.
- 관측 이력: 최초5초 제한은 생성이 제한 전에 정상 완료돼 timeout fixture 조건을 만족하지 않았다. 제한을2초로 명시해 별도 실행했으며 제품 timeout 실패로 해석하지 않는다.
- 결과/남은 게이트: [통합 검증 JSON](roadmap-integration-validation.json)에 기록했다. 실제 브라우저 검증은 도구 접근 거절로 대기, 운영 issuer/client 정보도 미제공 상태다. Git 게시 없음.

## 7개 작업 로컬 통합·검증 (2026-10-13)

- 승인/기준: 사용자 `승인`에 따라 원격 develop `fb75a46`과 같은 기준으로 `feature/roadmap-integration`을 생성했다. 7개 원본 worktree의521개 파일 항목을 snapshot/hash로 보존했고 완료 시 원본 변경0개를 확인했다. commit/develop merge/push는 하지 않았다.
- 변경: P0/P1·OAS-1·API-3·RUN-2·IOP-1·COL-1/2·GOV-1/DOC-1을 결합했다. OpenAPI route/model102개를 재생성하고 인증 gate·import·release·portal·SDK 화면과 스타일을 함께 연결했다.
- 통합 수정: OAuth 실행 Vault를 현재 사용자/Workspace에 연결, Runner의 OAuth 발급 허용, SDK queue 시작 전 membership 재확인, portal ZIP에도 authenticatedFetch 적용, API OAuth callback query 로그 제거, P1 계측의 Workspace case root 사용, shutdown 시 영구 commit을 끝낸 release job의 성공 상태 보존을 반영했다.
- 저장소: identity/release 독립 migration과 OAuth v6를 결합했다. 계정·감사·release·SDK ZIP은 이관하고 session/pending 및 OAuth token은 제외한다. 하나의 SQLite source에 모든 기능을 넣어 PostgreSQL parity·ZIP bytes·migration version·원본 DB 불변을 확인했다.
- 자동 검증: 전체 Python552개(skip0,78.093초), frontend111개·production build, 생성 최신성·diff 검사 통과. 이후 shutdown commit 경계 수정은 job/SDK/portal/교차 기능45개(8.685초), 결합 PostgreSQL 이관 신규1개(0.299초)로 검증했다. 전체552개를 최종 shutdown 수정 후 재실행한 것으로 표기하지 않는다.
- 실제 HTTP: 테스트 인증 어댑터와 독립 loopback 서버에서 두 Workspace의 OAuth 발급→빠른 호출→실제 Python 자식 runner→파이프라인→이력 및 import/export 격리 확인. 실제 Java 생성기로 Python SDK·release Go SDK를 생성해 ZIP CRC/SHA·원본 revision/digest·타 Workspace404·작업 관리자 재시작 후 동일 파일을 확인했다.
- 실제 HTTPS: 임시 CA 검증을 켠 OIDC 공급자와 Uvicorn에서 로그인·PKCE·CSRF·Workspace 전환·logout·replay 거부·token 미저장 fixture를 통합 코드로 다시 실행해 통과했다. 운영 공급자를 사용한 결과는 아니다.
- 실패 이력: 첫 Python 통합 실행547개는 기존 TestClient host/identity fixture 불일치13실패·3오류였다. loopback Host·임시 identity DB·trusted adapter로 fixture를 수정했다. 추가 실제 runner 검증의 첫 실행은 임시 fixture ROOT에 CLI entrypoint가 없어 실패했으며 repo 실행 root와 임시 data root를 구분해 해소했다.
- 완료 경계: 로컬 코드 통합과 위 검증까지. 실제 브라우저 접근은 사용자 허용 후에도 도구 정책 거절 상태로 남아 있다. 운영 issuer 등록·외부 배포·전체 LT campaign·공통 pagination 등은 미완료이며 이전 실패/unknown을 변경하지 않는다.
- 자료: [통합 검증 JSON](roadmap-integration-validation.json), [원본 파일 해시](roadmap-integration-source-manifest.json), [통합 계획](roadmap-integration-plan.md).

## 통합 시작 (2026-10-13)

사용자 승인으로 `feature/roadmap-integration`에서 7개 작업을 통합한다. 원본 worktree는 보존하고 commit/develop merge/push는 하지 않는다. 인증·저장소·job·화면 계약을 결합하고 전체 회귀 및 교차 Workspace 통합 검증을 수행한다. 브라우저 접근 제한은 별도다.

### 원본 단계별 기록

- [COL 기존 기록](archive/integration-sources/COL/api-load-test-progress.md)
- [P1 기존 기록](archive/integration-sources/P1/api-load-test-progress.md)
- [OAS 기존 기록](archive/integration-sources/OAS/api-load-test-progress.md)

## 2026-11-04 — 로컬 develop 병합 및 기존 작업 보존

- 시작: `feature/load-test-baseline-recovery`의 기존 미커밋 변경 17개 파일을 압축 백업과 stash `82391be`로 보존하고, 로컬 `develop`의 `ebf7672`를 병합한다.
- 변경: 제품 코드는 자동 병합됐다. 진행 문서와 하네스 문서의 충돌 3개는 develop의 최신 구조를 유지하며 해결했다. P0/P1 과거 이력은 `docs/archive/integration-sources/P1/`에 보존된 내용을 확인했다. 기존 P1 코드·증거 대부분은 develop에 이미 통합되어 있으며 Workspace·pagination 호환 보완을 유지한다.
- 검증 계획: Python 전체 테스트, 프런트엔드 테스트·빌드, OpenAPI 생성 일치 검사, P1/LT-5 보고서 재현, diff 및 기존 변경 보존 확인.
- 검증 완료: 전체 Python 659개(125.821초, skip 0), 프런트엔드 37개 파일/167개 테스트, production build, OpenAPI 생성 최신성, Node k6 모델 5개 파일, LT-5 및 P1 보고서 2개 재현 검사, staged/unstaged diff 검사 통과. 빌드의 500 kB 초과 chunk 경고는 남아 있다.
- 보존 확인: 원본 17개 파일을 대조했다. 11개는 byte 단위로 동일하다. 진단 코드·테스트는 develop의 Workspace·pagination 호환 수정과 함께 보존했고, 문서 안내의 원래 링크도 유지됐다. 기존 진행 기록의 모든 비어 있지 않은 줄은 현재 문서 또는 P1 보관 문서에 남아 있다. 기존 영문 README와 별도 2026-10-13 검증 기록은 미커밋으로 복원했다. README에는 develop의 인증 모드 안내를 추가했다.
- 환경: sandbox의 Docker 접근 제한은 허용된 권한 확장 실행으로 해소했다. 테스트 전용 PostgreSQL·Redis를 시작해 전체 회귀를 실행한 후 원래 중지 상태로 복원했다. 현재 차단 없음.
- 완료: 로컬 develop `ebf7672`를 현재 `feature/load-test-baseline-recovery`에 병합한다. 제품 코드는 병합 기준 develop과 동일하다. 기존 변경의 압축 백업과 stash `82391be`를 유지하며, 원격 푸시·운영 배포·새 부하 캠페인은 수행하지 않았다.
- 검증 로그: `/tmp/api-develop-merge-python.log`, `/tmp/api-develop-merge-web-test.log`, `/tmp/api-develop-merge-web-build.log`, `/tmp/api-develop-merge-generated.log`, `/tmp/api-develop-merge-k6-models.log`.
