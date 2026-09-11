# API 소유권 확인과 외부 Setup

Studio에서 생성한 일회용 challenge를 대상 서버에 배포하여 서버 제어권을 확인한다.
실제 업무 API의 Bearer/API Key 인증 및 조직의 부하 실행 허가는 별도다.
계정이 없는 현재 버전에서는 인증 결과를 프로젝트 전체가 공유한다.

## 실행 모드

| LOCAL_SERVER | SKIP_OWNERSHIP_VERIFICATION | 동작 |
|---|---|---|
| false | false | 소유권 확인 필수 (기본값) |
| true | false | loopback 로컬 실행, 소유권 확인 필수 |
| true | true | loopback 로컬 실행, 소유권 확인 생략 |
| false | true | 시작 오류 |

대문자 환경변수 이름을 사용한다. 값은 대소문자 무관하게 `true`만 참이다.
네이티브 Python 실행은 `.env`를 자동으로 읽지 않으므로 셸/서비스에서 환경변수를 설정한다.

```sh
LOCAL_SERVER=true SKIP_OWNERSHIP_VERIFICATION=false API_TEST_HOST=127.0.0.1 python3 react_server.py
```

Docker는 컨테이너 간 통신 때문에 `0.0.0.0`에 바인딩한다. `LOCAL_SERVER=false`로 사용한다.
인증 생략을 선택해도 외부 Setup 단계의 승인·60초 제한과 실제 API 인증은 유지된다.
인증 생략을 해제하면 이전 생략 실행이 인증 완료로 인정되지 않는다.

## 웹에서 인증

1. 프로젝트 설정에서 기본/추가 HTTPS Base URL을 저장한다.
2. 다시 설정을 열고 `API 소유권 확인`에 저장된 URL을 입력한다.
3. `검증 토큰 발급 / 재발급`을 누르고 표시된 경로에 응답을 배포한다.
4. `소유자 확인`을 누른다. 발급했던 브라우저 세션 쿠키가 필요하다.

```http
GET /.well-known/api-develop-studio-verification/{verification_id}
```

```json
{"challenge": "Studio가 발급한 값"}
```

요청에서 challenge를 받거나 반사하면 안 된다. 서버에 미리 배포된 값만 반환한다.
공개 IP와 유효한 TLS 인증서, 200 응답, 4KB 이하 JSON이 필요하다. 검증은
프록시·redirect·JavaScript 실행 없이 DNS에서 검사한 IP에 직접 연결한다.
사설망/localhost 인증 엔드포인트는 현재 지원하지 않는다. 로컬 개발 대상은 로컬 생략 설정을 사용한다.

challenge는 30분 유효하고 성공 후 재사용할 수 없다. 재발급은 10초 간격,
검증 시도는 발급당 최대 10회다. 원문은 발급 화면에서만 보여 주고 DB에는 해시만 저장한다.
새로고침해도 pending 기록을 확인할 수 있지만 원문은 다시 표시하지 않는다.
완료 후 대상 API에서 challenge를 제거해도 된다.

인증은 프로젝트와 정확한 origin(scheme, host, port)에 결속한다.
30일 미사용 또는 90일 절대기간 만료 시 재인증한다. 정상적으로 허용된 요청이 전송되기
직전에 마지막 사용 시각을 갱신하며, 테스트 assertion 실패는 사용으로 인정한다.
프로젝트 Base URL origin 집합 변경 시 인증 취소, 프로젝트 삭제 시 인증·승인 기록을 제거한다.

## 외부 API를 전체 실행에서 한 번만 호출

### 기본 example에서 로컬 동작 확인

`example-ownership-local.json` 파이프라인을 선택하면 다음 순서로 실행된다.

| 단계 | 케이스 | 기대 응답 |
|---|---|---|
| Setup 상태 확인 | `example/health/check_health.json` | 200 |
| 인증정보 누락 거부 | `example/security/reject_missing_api_key.json` | 401 |
| 예제 API Key 허용 | `example/security/accept_example_api_key.json` | 200 |

401은 의도한 기대 응답이므로 두 번째 단계도 통과해야 한다.
`example-api-key`는 내장 예제 서버의 공개 fixture 값이며 운영 인증정보가 아니다.
기존 사용자가 편집한 `get_secure_data.json` 케이스는 이 파이프라인에서 사용하지 않는다.

예제 서버와 CLI 양쪽에 아래 환경변수를 설정한다. 예제 서버 기본 주소는 `http://127.0.0.1:8765`다.

```sh
# 터미널 1: 내장 예제 서버
EXAMPLE_PROJECT=true LOCAL_SERVER=true SKIP_OWNERSHIP_VERIFICATION=true API_TEST_HOST=127.0.0.1 python3 react_server.py

# 터미널 2: 파이프라인 실행
EXAMPLE_PROJECT=true LOCAL_SERVER=true SKIP_OWNERSHIP_VERIFICATION=true python3 run_api_tests.py pipelines/example-ownership-local.json
```

웹에서는 Example API의 파이프라인 목록에서 `example-ownership-local.json`을 선택한다.
인증 생략을 끄면 이 로컬 HTTP 대상은 첫 호출 전에 차단된다. 이 예제의 Setup은 일반 로컬
Setup이며, 공개 HTTPS 대상의 `external_once` 승인 예외를 자동으로 부여하지 않는다.

### 승인된 외부 Setup 구성

1. 프로젝트 설정의 `외부 Setup 1회 호출 승인`에 정확한 HTTPS URL·메서드를 등록한다.
2. 서버 모드에서는 32자 이상의 `STUDIO_APPROVER_KEY`를 서버에 설정하고 UI에 입력한다.
   이 키는 프로젝트/브라우저 저장소에 저장하지 않는다. 로컬 모드에서는 로컬 운영자가 승인한다.
3. 외부 요청을 일반 API 케이스로 저장한다. 토큰 등은 기존 보안 변수 기능을 사용한다.
4. 파이프라인 편집에서 `Setup · 승인된 외부 API 1회 호출`을 선택해 추가한다.
5. 기존 `값 전달`로 Setup 응답의 토큰 등을 뒤의 테스트 단계에 전달한다.

```json
{
  "project": "sample.json",
  "steps": [
    {"name": "login", "case": "external/auth/login.json", "phase": "setup", "external_once": true, "retry": 0},
    {"name": "users", "case": "service/users/list.json", "input_mappings": [
      {"source_step": "login", "response_path": "body.access_token", "target": "header", "target_key": "Authorization", "template": "Bearer {{value}}"}
    ]}
  ]
}
```

Setup은 모든 테스트 단계보다 앞에 위치한다. 외부 Setup은 재시도·실패 후 계속 실행을
금지하며 실패하면 파이프라인을 중지한다. URL 변수/값 전달/Authorization 적용 후 실제
URL과 메서드를 검사한다. query가 있는 URL 및 Digest/NTLM 추가 handshake는 외부 1회 모드에서
지원하지 않는다. 필요한 토큰 요청 값은 POST body로 전달한다.

같은 프로젝트·URL·메서드는 실패를 포함하여 60초에 한 번만 호출할 수 있다. SQLite
트랜잭션으로 동시 실행에도 제한을 공유한다. 다른 단계나 단건 실행에 외부 예외가 적용되지 않는다.
정책 검사 중인 모든 테스트 요청은 redirect를 따라가지 않는다.

현재 파이프라인은 단계별 1회 실행이다. 신규 부하 생성기나 VU 반복 스케줄러는 구현하지 않는다.
향후 부하 실행기에서는 Setup을 VU 루프 바깥에서 한 번 실행하도록 연결해야 한다.

## 저장과 API

기존 `case/{tag}/{api_name}/{case_file}.json` 구조는 유지한다.
인증·외부 승인 상태는 `data/ownership.db`에 저장하고 프로젝트 JSON의 사용자 입력으로
verified 상태를 설정할 수 없다. `STUDIO_OWNERSHIP_DB_PATH`로 저장 위치를 변경할 수 있다.
웹 서버와 CLI는 동일한 경로를 사용해야 한다. 브라우저 쿠키 삭제 시 pending 작업은 재발급한다.

- `GET /api/ownership?project=...`: 상태 및 세션 쿠키
- `POST /api/ownership/issue?project=...`: `{ "url": "https://..." }`
- `POST /api/ownership/verify?project=...`: `{ "verification_id": "..." }`
- `POST /api/ownership/grant?project=...`: `{ "url": "https://.../token", "method": "POST" }`
- `POST /api/ownership/remove-grant?project=...`: 같은 URL·메서드

변경 API는 같은 origin의 UI 및 세션 쿠키를 요구한다. 서버 승인에는
`X-Studio-Approver-Key` 헤더를 추가한다. 임의 `X-Studio-Actor`는 승인 근거로 사용하지 않는다.
단건 빠른 호출도 소유권 검사 시 프로젝트를 선택해야 한다. `/api/run`의 저장/미저장 케이스,
저장/미저장 파이프라인과 CLI는 실제 HTTP 전송 직전 동일한 정책을 적용한다.
CLI에서 정책 차단은 exit code 2이고 웹 실행 결과에 해당 오류가 표시된다.

로컬 사용자는 프로그램과 DB를 수정할 수 있으므로 이 기능은 로컬 관리자에 대한 강제
통제가 아니다. 계정별 멤버십/역할 관리는 향후 별도 구현 대상이다.
