# MOCK-1 개발 인계 프롬프트

아래 내용을 개발할 AI 모델에 전달한다. 구현 완료 후 현재 Codex 작업에서 별도로 코드 리뷰와 검증을 수행한다.

---

API Develop Studio의 **MOCK-1: OpenAPI 기반 Mock Server**를 구현하라. 계획만 제시하지 말고 API·사용자 화면·테스트·사용 설명까지 구현하고 검증하라.

## 작업 기준

- 저장소: `/Users/kwondaehoon/Desktop/Project/api-develop-studio`
- 준비된 브랜치: `feature/mock-server`
- 분기 기준: 로컬 `develop`의 `f033c44` (`feat: add test coverage and data lifecycle`). 원격 최신성은 확인하지 않았다.
- 먼저 `AGENTS.md`, `docs/api-development-plan.md`의 MOCK-1 및 의존성, 두 진행 문서를 읽고 실제 코드와 상태를 확인하라.
- 이미 준비된 브랜치에서 작업한다. 사용자 변경과 이 인계 문서를 보존한다. 임의 커밋·병합·푸시·브랜치 삭제·배포를 하지 않는다.
- `docs/api-development-progress.md`에 시작·주요 변경·검증·차단·완료를 기록한다. Mock 부하 smoke 관련 기록은 `docs/api-load-test-progress.md`에도 동기화하되 LT/DB 전체 단계를 완료 처리하지 않는다.

## 먼저 확인할 기존 구현

- 앱 조립: `api_test/main.py`, `api_test/dependencies.py`
- OpenAPI 경로: `api_test/services/openapi.py`, `api_test/implementations/openapi.py`, `api_test/openapi_editing.py`, `api_test/contracts/`
- 관리 API 계약: `openapi/studio.yaml`, `openapi/paths/`, `openapi/components/schemas/`, `scripts/generate_server.py`
- 실행·수명주기: `api_test/runner.py`, `api_test/job_runner.py`, `api_test/jobs.py`, `api_test/test_coverage.py`, `docs/test-coverage-lifecycle.md`
- 화면: `web/src/App.jsx`, `web/src/pages/apis/`, 프로젝트 설정 및 파이프라인 편집기
- 테스트: `tests/test_asgi_contract.py`, `tests/test_contract_api.py`, `tests/test_test_lifecycle.py` 및 frontend 테스트

기존 문서 해석·저장소·실행 정책·환경 선택을 재사용한다. 생성 파일은 직접 고치지 말고 원본 명세와 필요한 binding을 수정한 뒤 재생성한다. 먼저 짧게 설계와 변경 파일, 검증 방법을 설명한 후 구현한다.

## 기능 요구사항

1. 프로젝트 OpenAPI의 path와 method를 실제 HTTP로 제공한다. 명세의 `servers` 주소로 실제 요청을 전달하지 않는다. 정적 경로와 path parameter 충돌의 우선순위, 미등록 path/method 동작을 정의하고 테스트한다.
2. 선택한 status·media type의 OpenAPI example을 우선 사용하고, 없으면 schema로 결정적인 응답을 생성한다. `examples` 선택과 `example`/schema example/default의 우선순위를 문서화한다. 객체·배열·기본 타입·enum·nullable·로컬 `$ref`를 다루고 지원하는 조합 및 제약 범위를 명시한다. 지원하지 않는 schema는 조용히 잘못된 성공 응답을 생성하지 않는다. 순환 참조·과도한 깊이/배열/응답 크기를 제한하며 임의 외부 reference를 fetch하거나 로컬 파일을 읽지 않는다.
3. operation/scenario별 status, latency, 오류 응답을 선택할 수 있게 한다. 명세에 없는 status와 범위/default 응답의 처리 규칙, 잘못된 입력의 오류 계약을 명시한다. 204와 HEAD 등 본문 금지 응답을 처리한다. 지연은 유한한 상한을 두고 다른 요청과 관리 API를 불필요하게 막지 않는다.
4. 고정 seed와 scenario별 state를 제공한다. 같은 명세 snapshot·seed·scenario·요청 순서·초기 상태에서 같은 결과를 재현한다. 단순 endpoint마다 독립된 랜덤 응답을 반환하는 수준으로 끝내지 않는다. 최소한 생성→ID를 이용한 조회→선택된 오류 응답을 재현할 선언형 state 동작 및 reset을 구현한다. 임의 Python/shell/eval은 허용하지 않는다. 프로젝트·Mock 인스턴스·scenario 상태를 격리하고 동시 접근, state 크기 상한, 중지 시 정리, 재시작 시 보존 여부를 정의한다.
5. Mock 시작·상태 조회·중지·reset과 접속 주소를 제공한다. 실행 중 명세 변경의 반영 정책(snapshot/restart 등)을 명시한다. bind host 기본값은 loopback으로 하고 이번 범위에서는 비-loopback/wildcard를 거부하는 보수적인 정책을 기본으로 구현한다. 기존 Studio 서버가 공개 bind될 때 Mock 실행 경로도 공개되는 설계를 피한다. 포트 충돌·중복 시작·실패·앱 종료 정리를 처리한다. 단일 프로세스 제약이 있으면 UI/문서에 정확히 적는다.
6. 사용자가 접근할 수 있는 한국어 화면을 기존 프로젝트/OpenAPI 흐름에 연결한다. 상태·주소·seed·scenario·status·latency·오류 선택·시작/중지/reset을 사용할 수 있어야 한다. 새로고침 후 서버 상태를 다시 조회하고 중지/오류 상태를 잘못 실행 중으로 표시하지 않는다. 화면에서 만든 설정이 실제 응답에 반영되어야 한다.
7. 실제 외부 API 없이 기존 케이스·파이프라인에서 Mock 주소를 사용할 수 있게 한다. 기존 환경·소유권·접근 정책의 전체 우회는 금지한다. 임시 fixture에서 setup 생성→응답 ID 추출→조회→의도한 오류 검증을 실행한다. 기존 read-only Example과 사용자 프로젝트를 수정하지 않는다.
8. Mock 대상의 짧고 제한된 동시 HTTP 부하 smoke를 제공하고 실제 실행한다. 요청 수·동시성·시간 상한·성공/오류 기대값·결과를 기록한다. 기존 부하 도구가 있으면 재사용하고, 없으면 최소 검증 harness로 작성한다. 대규모 부하 플랫폼이나 OBS 대시보드는 범위 밖이다.

## 경계와 회귀 방지

- 관리 API는 기존 생성 APIRouter/DTO → implementation/service 구조 및 오류 계약을 따른다. Mock 트래픽 경로와 Studio 관리 경로를 분리한다.
- 프로젝트 검증·서버 결정 사용자 문맥·revision 충돌·Example 쓰기 방지 정책을 유지한다. 새 설정을 영구 저장하면 기존 저장소/migration 경로를 사용한다.
- 기존 실행 이력에 request/response body, header, 인증 값 또는 state 원문을 추가하지 않는다. 예제 응답 확인 UI와 영구 실행 metadata를 구분한다.
- case 저장 경로 `case/{tag}/{api_name}/{case_file}.json` 및 `/` 구분자를 유지한다. macOS/Linux뿐 아니라 Windows에서 프로세스·주소·정리 동작을 고려한다.
- OAS-1 전체 편집, OAuth, workspace 인증, 분산 Mock, 영구 state, TST 후속을 무관하게 확장하지 않는다.

## 필수 검증

- 단위/통합: example 우선순위, 결정성, reference/제약 오류, status/본문 규칙, latency 입력 경계, state 생성·조회·reset·격리·동시성, host 제한, 포트 충돌, 중지/종료 정리.
- 실제 HTTP: 새 임시 데이터와 loopback 서버를 사용해 관리 API와 Mock 트래픽, 기존 파이프라인, 짧은 부하 smoke를 검증한다. 전송을 monkeypatch한 테스트만으로 완료하지 않는다.
- 실제 브라우저: 화면 접근→설정→시작→응답 확인→새로고침→reset→중지, 오류 상태와 콘솔 오류를 확인한다. 사용자 데이터와 기존 실행 서비스를 보존하고 임시 자원을 정리한다.
- 저장소 루트: `python3 -m unittest discover -s tests -v`
- `web/`: `npm test`, `npm run build`
- 저장소 루트: `python3 scripts/generate_server.py --check`, `git diff --check`
- 환경에 맞는 Python/의존성을 확인한다. 실패와 skip은 숫자·원인·영향을 적는다. 실행하지 못한 항목을 통과로 기록하지 않는다.

## 완료 보고와 리뷰 인계

변경 파일과 설계 결정, 실행/사용 방법, 테스트 명령과 결과, 실제 HTTP·브라우저·smoke 증거, 제한과 남은 작업, 최종 브랜치 및 `git status --short`를 보고하라. MOCK-1 완료 기준이 충족되지 않으면 진행 또는 차단으로 남긴다. 커밋·병합·푸시는 하지 않는다.

후속 Codex 리뷰는 develop 기준 diff와 미커밋 변경을 모두 확인하고, 위 요구사항의 누락·회귀·state 격리·외부 노출·정리 동작을 독립적으로 검증한다. 개발 모델의 테스트 보고를 그대로 신뢰하지 않으며 주요 테스트와 실제 HTTP/브라우저 시나리오를 재실행한다. 발견사항은 심각도와 파일/라인, 재현 조건으로 보고하고 수정 후 다시 검증한다.
