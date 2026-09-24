# MOCK-1 계획 이행 검증서

> 보관 문서: MOCK-1 개발 당시의 독립 검증 계획이다. 현재 사용법과 상태는 [`../../mock-server.md`](../../mock-server.md) 및 [`../../api-development-progress.md`](../../api-development-progress.md)를 따른다.

- 작성일: 2026-09-21
- 상태: **검증 계획 작성 완료 / 검증 실행 대기**
- 대상: `feature/mock-server`의 현재 작업 트리. 로컬 커밋 `0a6151f` 이후 미커밋 수정까지 포함한다.
- 목적: 테스트 통과 여부뿐 아니라 MOCK-1 계획의 기능·사용 흐름·격리·종료 조건이 실제로 충족되는지 독립 판정한다.
- 이번 문서 작성은 검증 실행, 기능 완료, 커밋, 원격 반영 또는 병합을 의미하지 않는다.

## 1. 기준 문서 및 완료 조건

- 원래 계획: [API 개발 기능 계획 — MOCK-1](../../api-development-plan.md#mock-1-mock-server)
- 상세 개발 범위: [개발 인계 프롬프트](development-prompt.md)
- 기존 결함과 수정 이력: [독립 리뷰](review.md)
- 상태 기록: [개발 진행](../../api-development-progress.md), [부하테스트 진행](../../api-load-test-progress.md)

원래 완료 조건은 **실제 외부 API 없이 생성·조회·오류 파이프라인과 부하테스트 smoke를 재현할 수 있음**이다. 이를 다음 요구사항으로 나누어 검증한다.

| 계획 요구사항 | 검증 ID | 필수 증거 |
| --- | --- | --- |
| OpenAPI example 우선, 없으면 schema 기반 결정적 응답 | M01–M04 | 선택 응답과 실제 HTTP body/header, 독립 schema 검증 |
| status·latency·오류 응답 선택 | M05–M07 | 설정 전후 응답, 측정 시간, 오류 시 state 보존 |
| 고정 seed·scenario별 state | M08–M11 | reset/replay 결과, 격리·동시성·ID 보존 |
| 외부 공개 방지·bind host 설정 | M12–M14 | host 차단, 포트·종료·자원 정리 |
| 외부 API 없는 생성·조회·오류 pipeline 및 smoke | M15–M17 | 실제 runner 결과, 본문 불일치 실패, bounded smoke |
| 실제 사용 가능한 화면·기존 기능 보존 | M18–M20 | 브라우저 흐름, 명세 소스 3종, 회귀 결과 |

현재 구현 정책도 별도로 검토한다. 명시적 example/media 선택은 명세 응답 재생으로 처리하고 CRUD state를 변경하지 않는다. seed/scenario 값의 실제 변경은 state를 초기화하며 동일 값·latency·override 변경은 보존한다. 순환/지원 한계 schema는 잘못된 성공 응답 대신 명시적 오류로 거부한다. 이러한 제한이 요구사항을 충족하는지 검증 보고서에 판단 근거를 남기며, 현재 코드의 동작만으로 요구사항을 낮추지 않는다.

## 2. 실행 전 준비와 검증 대상 고정

1. `AGENTS.md`와 위 문서를 읽는다. 검증은 현재 코드와 미커밋 변경을 모두 대상으로 한다. 이전 테스트 숫자를 이번 결과로 복사하지 않는다.
2. 아래 명령 결과와 검증 시작 시간을 기록한다. 검증 중 코드가 바뀌면 변경 범위와 재검증 항목을 명시한다.
3. 임시 디렉터리에 프로젝트·케이스·파이프라인·SQLite DB·로그를 분리한다. Python 테스트의 임시 저장소 패턴을 재사용한다. 운영 PostgreSQL, 사용자 프로젝트, 기존 서버와 공개 Example 파일을 수정하지 않는다.
4. Studio와 Mock은 서로 다른 사용 가능한 loopback 포트로 실행한다. 포트 번호를 가정하지 말고 실제 관리 API가 반환한 URL을 사용한다. URL 명세 테스트도 임시 loopback 서버에서 제공한다.
5. 초기화·종료 책임과 생성한 프로세스/포트를 기록한다. 테스트 실패 시에도 자신의 임시 서버와 작업만 정리한다.

```sh
# 저장소 루트
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
git ls-files --others --exclude-standard
```

환경 기록: OS, Python/Node 버전, 설치 의존성, 브랜치/SHA, staged·unstaged·untracked 범위, DB 종류, Studio/Mock URL, fixture seed. 실제 secret이나 사용자 원문 데이터는 결과 문서에 넣지 않는다.

Sandbox의 loopback bind·프로세스 조회 제한은 제품 결함과 구분한다. 필요한 권한 요청이 거절되면 해당 항목을 차단으로 남기고, ASGI/JSDOM 검증을 실제 HTTP/브라우저 검증으로 표시하지 않는다.

## 3. 공통 fixture

| Fixture | 구성 |
| --- | --- |
| 정상 응답 | GET `/health`, JSON named examples 2개, single example, schema example/default, example 없는 schema |
| CRUD·오류 | POST `/api/users`, GET/PUT/PATCH/DELETE `/api/users/{id}`, 동일한 `/api/orders` 경로, 201/200/204/404/503 응답 |
| 중첩 scope | `/teams/{teamId}/users`와 `/teams/{teamId}/users/{id}`, 서로 다른 team 두 개 |
| 라우팅 | `/api/users/me`와 `/api/users/{id}`, 같은 path의 복수 method, 미등록 path/method |
| Media | JSON 및 `text/plain` 응답, named example, body 없는 204 및 HEAD |
| Schema 경계 | minItems 5/101, maximum 0, integer minimum 1.5, maxLength 2, pattern, nullable, enum, local ref, 필수 순환 ref, 외부 ref |
| 명세 소스 | 같은 operation을 `docs_file.document`, `docs_bundle`, `docs_url`로 각각 만든 임시 프로젝트 |

케이스 파일은 `case/{tag}/{api_name}/{case_file}.json` 구조로 저장한다. fixture의 method/path/status/example 이름을 검증 결과에 남겨 재현 가능하게 한다.

## 4. 자동 검증 명령

명령은 검증 단계에서 실행한다. 아래 목록은 실행 결과가 아니다.

```sh
# 저장소 루트: 수정 관련 테스트 우선
python3 -m unittest discover -s tests -p 'test_mock*.py' -v

# 저장소 루트: 전체 회귀와 생성 코드 최신성
python3 -m unittest discover -s tests -v
python3 scripts/generate_server.py --check
git diff --check
git diff --cached --check

# web/ 디렉터리에서 실행
npm test
npm run build
```

각 명령의 exit code, 실행/통과/실패/skip 수, 실패 원인 및 로그 위치를 기록한다. 미추적 파일은 `git diff --check`만으로 검사되지 않으므로 별도 확인한다. PostgreSQL 의존 skip은 범위를 명시하고 SQLite 검증을 PostgreSQL 검증으로 간주하지 않는다. 생성 파일 공백 정리와 생성기 출력이 서로 다른지도 `--check`에서 확인한다.

## 5. 기능 검증 매트릭스

모든 항목의 초기 상태는 **미실행**이다. 각 항목을 `통과 / 실패 / 차단 / 미실행` 중 하나로 기록하고 증거를 연결한다.

| ID | 실행 절차 | 기대 결과 |
| --- | --- | --- |
| M01 | named example 두 개를 차례로 선택. example 제거 후 single/schema example/default 및 schema 생성 확인 | 선택값이 실제 응답에 반영. 존재하지 않는 선택은 명시 오류. 우선순위가 문서·코드·화면과 일치 |
| M02 | 같은 명세·seed·초기 state에서 동일 요청 순서를 reset 후 재실행 | status/body가 동일. 다른 seed의 차이는 UUID 등 seed 영향을 받는 필드에서 확인 |
| M03 | schema fixture의 응답을 구현과 별개의 OpenAPI 3.0/3.1 validator로 검사 | 지원 schema는 모든 제약 만족. integer minimum 1.5는 정수 2 이상. minItems 5 및 maxLength 2 충족 |
| M04 | minItems 101, pattern, 필수 순환·깊이 초과·외부 ref를 호출 | 지원하지 못하면 구조화된 오류. 잘못된 성공 body나 무제한 생성 없음. 외부 URL/file 접근 없음 |
| M05 | 일반/CRUD GET·POST·PUT·PATCH·DELETE에서 status 및 오류 설정 변경 | 선택 status 일관 반영. 오류 시 생성·갱신·삭제 없음. 미선언 status와 범위/default 처리 정책 확인 |
| M06 | latency 0/200/5000ms 설정. 지연 요청 중 health/관리 조회 동시 실행. 음수·5001·문자열·boolean 입력 | 지연이 관측되고 다른 요청이 전체 지연만큼 막히지 않음. 잘못된 값은 400이며 기존 설정 보존. 시간 허용 오차는 환경과 함께 기록 |
| M07 | JSON/text named example을 일반/CRUD 경로에서 선택. HEAD·204 호출 | 실제 Content-Type과 raw body 일치. 명시 응답 재생 시 state 비변경. HEAD/204의 전송 body 없음 |
| M08 | 생성→ID 추출→조회→갱신→삭제→재조회→reset | 데이터 값 일치, 삭제 후 404, reset 후 초기 상태. 1·2 생성→1 삭제→새 생성 시 2 보존 |
| M09 | users/orders, team A/B, project A/B에서 같은 ID로 작업 | resource·parent·project 간 state 혼합 없음. 명시적 중복 ID가 기존 데이터를 덮어쓰지 않음 |
| M10 | 항목 생성 후 동일 seed/scenario와 latency/override만 저장. 다음으로 seed/scenario 실제 변경 | 전자는 state 유지, 후자는 안내된 정책대로 초기화. UI 설정 적용에서도 동일 |
| M11 | bounded 병렬 생성·조회, 요청 중 reset/config 변경, item/body/state/응답 크기 한계 시험 | ID 충돌·부분 저장·교차 요청 state 오염 없음. 크기 한계는 명시 오류. 부하/메모리 폭증 없음 |
| M12 | 127.0.0.1/localhost/지원 환경의 ::1 시작. 0.0.0.0/외부 IP/wildcard 시작 요청 | loopback만 허용, IPv6 URL bracket 정상. Studio가 외부 bind되어도 Mock 트래픽이 외부 경로로 노출되지 않음 |
| M13 | port 0/70000/문자열 seed, override latencyMs 문자열·mediaType 배열·errorResponse 문자열, 사용 중 포트로 시작 | 입력 오류 400. 기존 실행 서버·state 보존. 포트 충돌·기동 실패를 running으로 보고하지 않음 |
| M14 | 요청 없는 중지, 5초 지연 요청 중 중지, Studio 종료, 동일 포트 재시작 | 실제 thread/loop/socket 정리 및 포트 재사용. state 재시작 보존 여부가 안내와 일치. 미종료 task 경고/누수 없음 |
| M15 | 실제 HTTP runner: setup 생성→ID 추출→조회 body 비교→의도한 404/503 검증 | 외부 API 없이 모든 단계 통과. 본문을 고의로 틀리면 반드시 실패. 원문 데이터가 영구 실행 metadata에 추가되지 않음 |
| M16 | Mock 대상 50요청·동시성5로 health·조회·생성·기대 오류를 섞은 smoke | 정상 fixture의 실패 0, 기대 오류는 성공으로 집계, 완료/미완료 수 합계 일치. 실제 시간·status 분포 기록 |
| M17 | deadline 0.05초, 0.2초 stub 작업 5개/동시성1 및 실제 지연 HTTP를 각각 실행 | 전체 직렬 1초까지 기다리지 않음. 기한 뒤 새 요청 없음, 대기 요청 취소, 미완료 실패 집계. 함수 반환과 진행 중 worker 종료 시각을 따로 기록 |
| M18 | 세 명세 소스 각각에서 API 목록→Mock operation 선택→status/media/example/latency 설정→시작→실제 요청 | 실제 operation 목록/선택지 표시. 설정이 서버 응답에 반영. 존재하지 않는 `project.document` fixture만으로 통과 판정 금지 |
| M19 | 실행 상태에서 새로고침, override 복원, 조회 실패, reset, 중지 및 명세 수정 후 재시작 | 상태/설정 복원, 조회 실패를 정상 stopped/running으로 오인하지 않음. 명세 snapshot과 reset 정책 안내 확인 |
| M20 | 기존 Example 읽기 전용, case 저장, 빠른 호출·pipeline·ownership·생성 계약 회귀 확인 | 기존 보호·저장 경로·계약 유지. 생성 코드 최신성·frontend build 통과 |

## 6. 최근 6개 수정의 집중 확인

| 잔여 리뷰 항목 | 확인 위치 | 검증 |
| --- | --- | --- |
| 같은 설정에서 state 삭제 | `api_test/mock_engine.py`, MockServerPanel 설정 저장 | M10 및 `test_unchanged_seed_and_scenario_preserve_state` |
| UI 명세 연결 불일치 | `api_test/services/studio.py`, `ApiList.jsx`, `MockServerPanel.jsx` | M18, 세 소스의 실제 API 응답 및 브라우저 |
| schema 위반 성공 응답 | `synthesize_schema`, schema 오류 응답 처리 | M03/M04, 단순 non-null 검사로 대체 금지 |
| override 검증/실행 타입 불일치 | `api_test/services/mock.py` | M13, 400 확인 후 기존 서버 응답도 정상인지 확인 |
| CRUD media/example 무시 | Mock 엔진 명시 응답 선택 분기 | M07, raw text·JSON·state 비변경 모두 확인 |
| smoke deadline 미준수 | `api_test/mock_smoke.py` | M17, 반환 시간뿐 아니라 기한 뒤 추가 요청 및 worker 종료 확인 |

자동 테스트가 있어도 실제 사용자 흐름 또는 모든 경계를 검증한다는 뜻은 아니다. 특히 현재 변경의 회귀 테스트는 작성만 되어 있고 아직 실행되지 않았다.

## 7. 실제 HTTP 및 브라우저 실행 순서

1. 임시 프로젝트/DB와 fixture 명세로 Studio를 시작하고 프로젝트를 조회한다.
2. 관리 경로 `GET /api/projects/{reference}/mock`에서 초기 상태 확인.
3. `POST .../mock/start`에 seed/scenario/latency 설정을 전달하고 반환된 URL로 Mock 요청 수행.
4. `POST .../mock/config`의 적용 전후 body/header/latency와 state를 비교한다.
5. `POST .../mock/reset` 후 초기 상태와 동일 seed replay를 확인한다.
6. `POST .../mock/stop` 후 실제 접속 차단과 포트 반환을 확인한다.
7. 브라우저에서 프로젝트 → API 목록 및 API 작성 → OpenAPI Mock Server로 이동하여 M18/M19를 수행한다. 실제 요청 결과를 별도로 읽어 화면의 성공 메시지와 대조한다.
8. 브라우저 콘솔, 설정 복원, 좁은 화면의 컨트롤 접근성을 기록한다. 테스트 탭·임시 프로세스·포트를 정리한다.

명세와 다르게 동작하면 코드를 자동으로 수정해서 검증 결과를 덮어쓰지 않는다. 실패한 원본 상태, 재현 조건, 수정 필요 파일을 먼저 기록하고 개발 작업과 재검증을 구분한다.

## 8. 판정 및 보고 양식

**완료:** M01–M20의 필수 흐름이 통과하고 최근 6개 수정의 실패 재현이 해소되어야 한다. 미실행 HTTP·브라우저 항목이나 unresolved P1/P2를 남긴 채 완료 처리하지 않는다. 환경 조건으로 제외한 항목은 영향과 완료 판정 근거를 명시한다.

**진행:** 기능 누락·회귀·설명되지 않은 동작 차이·검증 미실행이 남아 있다.

**차단:** 검증에 필요한 권한·의존성·실행 환경이 없어 해당 항목을 실행하지 못한다. 차단과 제품 실패를 구분한다.

검증자는 다음 양식을 채워 별도 결과 문서에 저장하고 두 진행 문서를 동기화한다. 부하 단계 LT/DB 전체를 함께 완료 처리하지 않는다.

```markdown
# MOCK-1 검증 결과
- 검증 시각 / 담당:
- 브랜치 / HEAD / 미커밋 변경 범위:
- 환경 / DB / 임시 포트 / fixture:
- 최종 판정: 완료 / 진행 / 차단

| ID | 결과 | 실제 결과와 증거 | 결함·제한 |
| --- | --- | --- | --- |
| M01 | 미실행 | | |
<!-- M02–M20을 모두 기록 -->

## 명령 실행 결과
| 명령 | exit code | 실행·통과·실패·skip | 로그 |
| --- | --- | --- | --- |

## 발견사항
- 심각도 / 파일:라인 / 재현 / 기대값 / 실제값 / 영향

## 정리 및 후속 작업
- 임시 서버·포트·데이터 정리 결과:
- 미해결·미실행 항목과 다음 작업:
- 커밋·병합·원격 반영 여부:
```

## 9. 다른 AI에 전달할 검증 요청

> 이 문서에 따라 당시 MOCK-1 작업 트리를 독립 검증한다. `AGENTS.md`, 개발 계획, 리뷰 이력을 읽고 M01–M20 및 최근 6개 수정의 해소 여부를 판정한다. 기존 테스트 보고를 재사용하지 않고 실제 명령·HTTP·브라우저 증거를 수집한다. 사용자 데이터와 기존 변경을 보존하고 임시 loopback 환경을 사용한다. 코드는 수정하지 않고 결함과 실행 제한을 구분해 보고한다. 결과를 별도 Markdown 문서로 작성하고 두 진행 문서를 갱신한다. 커밋·푸시·병합은 하지 않는다.
