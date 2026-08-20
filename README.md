# JSON API Test Runner

JSON으로 HTTP 요청과 기대 응답을 정의하고, 응답 데이터가 정확히 같은지 검증하는 Python API 테스트 도구입니다. Python 표준 라이브러리만 사용하므로 별도 패키지 설치가 필요 없습니다.

## React 웹 화면

기존 데스크톱 GUI 대신 React 기반 웹 화면을 제공합니다. API 케이스와 파이프라인을 한 화면에서 만들고, 저장·불러오기·실행할 수 있습니다.

저장된 API 케이스는 선택 후 `삭제` 버튼으로 제거할 수 있으며, 삭제 전 확인 창이 표시됩니다.

저장된 파이프라인도 같은 방식으로 삭제할 수 있습니다.

터미널을 두 개 열어 아래처럼 실행합니다.

```bash
# 터미널 1: Python 파일 API 및 테스트 실행 서버
python3 react_server.py

# 터미널 2: React 개발 서버
cd web
npm install
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. 개발 서버가 `/api` 요청을 Python 서버(`127.0.0.1:8765`)로 전달합니다.

`localhost`가 IPv6(`::1`)로 해석돼 개발 서버가 열리지 않는 환경을 위해 Vite는 `127.0.0.1:5173`에 고정되어 있습니다.

프로덕션 정적 화면을 만들려면 `web/`에서 `npm run build`를 실행한 뒤 `http://127.0.0.1:8765`으로 접속합니다.

## 빠른 실행

### 하나의 파이프라인 실행

```bash
python3 run_api_tests.py pipelines/sample.json
```

### 기본 실행: 모든 파이프라인 실행

파이프라인 파일과 `--case`를 모두 생략하면 `pipelines/` 및 하위 디렉터리의 모든 `.json` 파이프라인을 이름순으로 실행합니다.

```bash
python3 run_api_tests.py
```

### 여러 파이프라인 한 번에 실행

파이프라인 파일을 공백으로 구분해 나열합니다. 앞 파이프라인이 실패해도 나머지 파이프라인은 계속 실행하며, 실패한 실행이 하나라도 있으면 프로세스 종료 코드는 `1`입니다.

```bash
python3 run_api_tests.py pipelines/sample.json pipelines/http-methods.json --log-dir test-logs
```

### 개별 API 케이스 실행

`--case`에 `case` 루트 기준 경로를 넣으면 파이프라인 없이 API 하나 또는 여러 개를 실행합니다. 여러 케이스는 명령 한 번으로 입력되며, 결과와 로그 순서를 보장하기 위해 입력한 순서대로 실행됩니다.

```bash
python3 run_api_tests.py --case sample/jsonplaceholder/get_post.json --log-dir test-logs
```

```bash
python3 run_api_tests.py --case \
  sample/jsonplaceholder/get_post.json \
  sample/jsonplaceholder/create_post.json \
  sample/jsonplaceholder/delete_post.json \
  --log-dir test-logs
```

### 파이프라인과 개별 API 함께 실행

파이프라인 파일을 먼저 쓰고 `--case`를 뒤에 붙이면 한 명령에서 함께 실행할 수 있습니다. 파이프라인들이 먼저 실행된 뒤 개별 API 케이스들이 실행됩니다. 두 종류 모두 실패하더라도 남은 대상은 계속 실행됩니다.

```bash
python3 run_api_tests.py \
  pipelines/sample.json \
  pipelines/http-methods.json \
  --case sample/jsonplaceholder/get_post.json sample/jsonplaceholder/delete_post.json \
  --log-dir test-logs
```

`pipelines/sample.json`은 다음 2단계 예제입니다.

1. `get_post`: 게시글 1번을 조회합니다.
2. `get_post_by_id`: 첫 단계 응답의 `id`를 `${get_post.response.body.id}`로 URL에 넣어 같은 게시글을 다시 조회합니다. 이 단계는 기본 재시도 설정 대신 최대 2회 재시도, 1초 간격을 사용합니다.

## HTTP Method별 예제

`pipelines/http-methods.json`은 JSONPlaceholder API의 CRUD 메서드를 순서대로 검증합니다. JSONPlaceholder는 테스트용 API이므로 POST, PUT, PATCH, DELETE 요청이 영구 데이터를 변경하지 않습니다.

| Method | 케이스 파일 | 검증 내용 |
| --- | --- | --- |
| GET | `sample/jsonplaceholder/get_post.json` | 게시글 조회 및 응답 body 일치 |
| POST | `sample/jsonplaceholder/create_post.json` | JSON body 생성 및 `201` 응답 |
| PUT | `sample/jsonplaceholder/replace_post.json` | 전체 리소스 교체 및 `200` 응답 |
| PATCH | `sample/jsonplaceholder/update_post_title.json` | 일부 필드 수정 및 `200` 응답 |
| DELETE | `sample/jsonplaceholder/delete_post.json` | 삭제 요청 및 빈 JSON 응답 |

```bash
python3 run_api_tests.py pipelines/http-methods.json --log-dir test-logs
```

다른 케이스 루트를 사용하거나 타임아웃을 바꾸려면 다음처럼 실행합니다.

```bash
python3 run_api_tests.py pipelines/my_pipeline.json --case-root case --timeout 15
```

테스트는 다음 명령으로 실행합니다.

```bash
python3 -m unittest discover -s tests -v
```

## 실행 로그

매 실행마다 기본 `logs/` 디렉터리에 `api-test_YYYYMMDD_HHMMSS_ffffff.log` 파일이 생성됩니다. 로그에는 파이프라인 시작 정보, 단계별 케이스 경로·재시도 설정, 실행 결과, 불일치 상세, 오류와 최종 요약이 포함됩니다.

```bash
python3 run_api_tests.py pipelines/sample.json --log-dir test-logs
```

검증 실패 시 로그에는 `request_value`, `expected_response`, `actual_response`를 각각 구분해 기록합니다. `strict`는 응답값이 아닌 `comparison_options`로 별도 기록되며 응답 데이터 비교 대상에는 포함되지 않습니다. 인증 토큰, 비밀번호, API key, cookie 등 민감한 키의 값은 `***REDACTED***`로 마스킹됩니다.

파이프라인 종료 시 케이스 경로의 첫 번째 디렉터리인 API tag별 요약도 기록합니다. 실패 때문에 실행하지 못한 후속 단계는 `SKIPPED`입니다.

```text
member: TOTAL 4 | PASS 3 | FAIL 1 | ERROR 0 | SKIPPED 0
order: TOTAL 2 | PASS 0 | FAIL 0 | ERROR 0 | SKIPPED 2
```

## 디렉터리 구조

케이스는 반드시 아래처럼 저장합니다. `{tag}`는 도메인·서비스·환경 등을 구분하는 이름이고, `{api_name}` 하나에 여러 JSON 케이스를 넣습니다.

```text
case/
  {tag}/
    {api_name}/
      get_success.json
      get_not_found.json
pipelines/
  smoke.json
```

예: `case/member/users/get_success.json`은 `member` 태그의 `users` API에 대한 성공 케이스입니다.

## 케이스 JSON

각 케이스는 `request`, `expected`를 포함하는 JSON 객체입니다.

```json
{
  "request": {
    "method": "POST",
    "url": "https://api.example.com/users",
    "headers": {
      "Authorization": "Bearer token"
    },
    "body": {
      "name": "Ada"
    }
  },
  "expected": {
    "status": 201,
    "strict": true,
    "body": {
      "id": 7,
      "name": "Ada"
    }
  }
}
```

- `request.method`: 선택 사항이며 기본값은 `GET`입니다.
- `request.url`: 필수입니다.
- `request.headers`, `request.body`: 선택 사항입니다. `body`는 JSON으로 직렬화됩니다.
- `expected.status`: 기대 HTTP 상태 코드입니다.
- `expected.body`: 기대 JSON 응답입니다.
- `expected.strict`: 기본값은 `true`입니다. `true`면 객체의 키, 배열 길이와 순서, 값과 타입이 모두 일치해야 합니다. `false`면 기대 객체에 없는 추가 키와 배열의 뒤쪽 요소는 허용하지만, 정의한 값은 모두 일치해야 합니다.

불일치 시 `$.body.user.id`처럼 정확한 JSON 경로와 기대값·실제값이 출력됩니다.

## 파이프라인 JSON

사용자는 `steps` 배열 순서대로 API 실행 파이프라인을 정의할 수 있습니다.

```json
{
  "defaults": {
    "retry": 1,
    "retry_interval_seconds": 0.5
  },
  "steps": [
    {
      "name": "create_user",
      "case": "member/users/create_success.json"
    },
    {
      "name": "get_user",
      "case": "member/users/get_success.json",
      "retry": 3,
      "retry_interval_seconds": 2
    }
  ]
}
```

- `steps[].name`: 파이프라인 안에서 고유한 단계 이름입니다.
- `steps[].case`: `case` 루트 기준 케이스 파일 경로입니다.
- `defaults.retry`: 모든 단계의 기본 재시도 횟수입니다. `0`이면 재시도하지 않습니다.
- `defaults.retry_interval_seconds`: 재시도 사이의 기본 대기 시간(초)입니다.
- 단계별 `retry`, `retry_interval_seconds`가 지정되면 기본값을 덮어씁니다.
- HTTP 상태/응답 검증 실패(`failed`)와 네트워크 오류(`error`) 모두 지정 횟수만큼 다시 시도합니다.
- 기본적으로 실패 또는 오류가 나면 이후 단계를 실행하지 않습니다. 해당 단계에 `"continue_on_failure": true`를 넣으면 다음 단계도 진행합니다.

## 이전 단계 응답 사용

후속 요청의 URL, 헤더, body 안에서 이전 단계의 응답값을 참조할 수 있습니다. 단계 이름은 이미 성공한 앞 단계여야 합니다.

```json
{
  "request": {
    "method": "GET",
    "url": "https://api.example.com/users/${create_user.response.body.id}",
    "headers": {
      "X-User-Id": "${create_user.response.body.id}"
    }
  },
  "expected": {
    "status": 200,
    "body": {"id": 7, "name": "Ada"}
  }
}
```

참조 문법은 다음과 같습니다.

- `${step_name.response.body}`: 이전 응답 전체 body
- `${step_name.response.body.id}`: body의 중첩 값
- `${step_name.response.status}`: 이전 HTTP 상태 코드

문자열 전체가 참조식이면 원래 JSON 타입(숫자, boolean, 객체 등)을 유지하고, 문자열 일부에 포함되면 문자열로 치환됩니다.

## 종료 코드

- `0`: 모든 단계 통과
- `1`: 검증 실패·네트워크 오류·중단된 파이프라인
- `2`: 잘못된 JSON, 누락된 케이스, 잘못된 재시도 설정 등 구성 오류
