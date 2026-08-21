# JSON API Test Runner

JSON으로 HTTP 요청과 기대 응답을 정의하고, 응답 데이터가 정확히 같은지 검증하는 Python API 테스트 도구입니다. Python 표준 라이브러리만 사용하므로 별도 패키지 설치가 필요 없습니다.

## React 웹 화면

기존 데스크톱 GUI 대신 React 기반 웹 화면을 제공합니다. API 케이스와 파이프라인을 한 화면에서 만들고, 저장·불러오기·실행할 수 있습니다.

API 케이스와 파이프라인의 `실행만` 버튼은 현재 화면의 값을 저장하지 않고 임시 파일로 실행합니다. 임시 파일은 실행 직후 삭제되며, 실행 결과 로그는 기존처럼 `logs/`에 남습니다. `저장 후 실행`은 현재 값을 JSON 파일로 저장한 뒤 실행합니다.

저장된 API 케이스는 선택 후 `삭제` 버튼으로 제거할 수 있으며, 삭제 전 확인 창이 표시됩니다.

API 케이스와 파이프라인 목록에서도 각 항목 오른쪽의 `×` 버튼으로 바로 삭제할 수 있습니다.

저장된 파이프라인도 같은 방식으로 삭제할 수 있습니다.

프로젝트 목록의 `×` 버튼으로 프로젝트를 삭제할 수 있습니다. 연결된 API 케이스 또는 파이프라인이 남아 있으면 프로젝트를 삭제할 수 없습니다.

### 화면에서 작업하는 순서

1. 첫 화면의 `프로젝트 목록`에서 `새 프로젝트 만들기`를 누르고 프로젝트 이름과 Base URL을 입력합니다. 프로젝트 JSON 파일은 이름을 기준으로 자동 생성됩니다. 저장된 프로젝트 카드의 `수정` 버튼에서는 프로젝트 이름, Base URL, Proxy, verify를 변경할 수 있으며 파일명과 연결된 케이스·파이프라인은 유지됩니다.
2. 저장하면 해당 프로젝트의 `API 케이스 목록` 화면으로 바로 이동합니다. 목록의 `새 케이스`를 누르면 케이스 설정 화면에서 Tag, API 이름, 케이스 파일, HTTP method, URL을 입력하고 저장할 수 있습니다. 목록의 기존 케이스를 누르면 같은 설정 화면에서 수정하거나 실행할 수 있습니다.
3. `Params`, `Authorization`, `Headers`, `Body` 탭에서 요청 값을 입력합니다. Params의 마지막 행에 값을 입력하거나 `Parameter 추가`를 누르면 다음 입력 행을 만들 수 있습니다. Body는 `raw JSON` 또는 `form-data`를 선택할 수 있으며, form-data에서는 텍스트와 파일 행을 추가할 수 있습니다.
4. 기대 HTTP 상태와 응답 body를 입력하고, 필요에 따라 `strict 비교`를 설정합니다.
5. 저장하지 않은 현재 값만 확인하려면 `실행만`을 누릅니다. 케이스 파일까지 저장하려면 `저장` 또는 `저장 후 실행`을 사용합니다.
6. 왼쪽 사이드바의 `파이프라인` 목록에서 새 파이프라인을 만들거나 기존 항목을 선택합니다. 설정 화면에서 같은 프로젝트의 저장된 케이스를 단계로 추가하고 순서·재시도 정책을 지정합니다. 파이프라인도 `실행만`으로 저장 없이 현재 구성만 실행할 수 있습니다.

프로젝트 Base URL이 `https://api.example.com`일 때 케이스 URL에 `/users`를 입력하면 `https://api.example.com/users`로 실행됩니다. 외부 API처럼 절대 URL을 입력한 경우에는 Base URL을 붙이지 않습니다.

`strict 비교`를 켜면 값과 타입이 모두 같아야 합니다. 예를 들어 `9.0`과 `9`는 서로 다른 타입으로 실패합니다. 끄면 객체의 추가 키와 배열의 뒤쪽 요소를 허용하며, 숫자 값이 같다면 `9.0`과 `9`는 통과합니다. `true`와 `1`은 strict 여부와 관계없이 서로 다른 값으로 비교합니다.

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

## Docker Compose 실행

Docker Compose는 Python API 서버(`api`)와 React 개발 서버(`web`)를 함께 실행합니다. `.env.example`을 복사한 뒤 사내 네트워크 설정에 맞게 프록시와 패키지 저장소 값을 입력합니다. `.env`에는 인증 정보가 들어갈 수 있으므로 Git에 올리지 않습니다.

```bash
cp .env.example .env
docker compose up --build
```

실행 후 브라우저에서 `http://127.0.0.1:5173`을 엽니다. React 컨테이너의 `/api` 요청은 Docker 네트워크 안의 `api:8765`으로 프록시됩니다.

`.env`에서 주로 설정하는 값은 다음과 같습니다.

- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`: 컨테이너 실행과 Python API 호출에 사용할 네트워크 프록시입니다.
- `PIP_PROXY`, `PIP_TRUSTED_HOST`, `PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL`: Docker 빌드 중 Python 패키지 설치에 사용할 프록시, 신뢰 호스트 및 패키지 저장소입니다.
- `HTTP_PROXY`, `HTTPS_PROXY`는 Docker 빌드 중 `npm ci`에도 동일하게 적용됩니다. `NPM_REGISTRY`, `NPM_STRICT_SSL`로 npm registry 및 TLS 검증 설정을 추가로 지정할 수 있습니다.
- `API_PORT`, `WEB_PORT`: 호스트에 노출할 포트입니다. 기본값은 각각 `8765`, `5173`입니다.
- `CASE_VOLUME_PATH`, `LOG_VOLUME_PATH`: 각각 컨테이너의 `/app/case`, `/app/logs`에 마운트할 호스트 경로입니다. 기본값은 `./case`, `./logs`입니다. form-data로 올린 파일도 `/app/case` 아래에 저장되므로 `CASE_VOLUME_PATH`를 유지해야 저장 후 재실행할 수 있습니다.
- `PROJECT_VOLUME_PATH`: 프로젝트 Base URL 설정을 보관할 컨테이너의 `/app/projects`에 마운트할 호스트 경로입니다. 기본값은 `./projects`입니다.

예를 들어 케이스와 로그를 프로젝트 밖에 보관하려면 `.env`에서 다음처럼 변경합니다. Windows 경로는 `C:/api-test/case`처럼 `/`를 사용합니다.

```env
CASE_VOLUME_PATH=/data/api-test/case
LOG_VOLUME_PATH=/data/api-test/logs
PROJECT_VOLUME_PATH=/data/api-test/projects
```

중지하려면 다음 명령을 사용합니다.

```bash
docker compose down
```

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

form-data 첨부 파일을 `case`와 다른 위치에 보관하는 경우에는 `--file-root`를 지정합니다. 지정하지 않으면 `--case-root`를 사용합니다.

```bash
python3 run_api_tests.py pipelines/upload.json --case-root case --file-root case
```

프로젝트 Base URL 설정이 다른 경로에 있다면 `--project-root`를 지정합니다.

```bash
python3 run_api_tests.py pipelines/my_pipeline.json --project-root projects
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
      files/
        profile.png
pipelines/
  smoke.json
projects/
  member-api.json
```

예: `case/member/users/get_success.json`은 `member` 태그의 `users` API에 대한 성공 케이스입니다.

## 프로젝트 JSON

프로젝트마다 Base URL을 한 번만 저장하고, 케이스에서는 프로젝트 파일명과 상대 URL을 연결합니다.

```json
{
  "name": "회원 API",
  "base_url": "https://api.example.com",
  "advanced": {
    "http_proxy": "http://proxy.example.com:8080",
    "https_proxy": "http://proxy.example.com:8080",
    "verify": true
  }
}
```

`projects/member-api.json`을 저장한 뒤 케이스에 `"project": "member-api.json"`, `"url": "/users"`를 지정하면 `https://api.example.com/users`를 호출합니다.

- `advanced.http_proxy`, `advanced.https_proxy`: 선택 사항입니다. 값이 있으면 각각 HTTP와 HTTPS 요청에 자동으로 적용되며, 비우면 해당 프로토콜은 직접 연결합니다. 화면의 `HTTP/HTTPS 공통 주소 사용`을 선택하면 한 번의 입력으로 두 값에 같은 주소를 저장합니다. 많은 사내 프록시는 HTTPS 요청에도 `http://proxy.example.com:8080` 형식의 프록시 주소를 사용합니다.
- `advanced.verify`: 기본값은 `true`입니다. `false`로 설정하면 TLS 인증서 검증을 생략합니다. 자체 서명 인증서를 사용하는 개발 환경에서만 사용하세요.

## 케이스 JSON

각 케이스는 `request`, `expected`를 포함하는 JSON 객체입니다.

```json
{
  "project": "member-api.json",
  "request": {
    "method": "POST",
    "url": "/users",
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

- `project`: 프로젝트 탭에서 저장한 프로젝트 JSON 파일명입니다. 프로젝트가 지정된 케이스는 상대 URL을 사용할 수 있습니다.
- `request.method`: 선택 사항이며 기본값은 `GET`입니다.
- `request.url`: 필수입니다. 프로젝트가 있으면 `/users` 같은 상대 URL 또는 절대 URL을 사용할 수 있습니다.
- `request.headers`, `request.body`: 선택 사항입니다. `body`는 JSON으로 직렬화됩니다.
- `request.form_data`: 선택 사항입니다. 지정하면 `body` 대신 `multipart/form-data` 요청을 만듭니다. 각 행은 텍스트 `{ "key": "title", "value": "profile" }` 또는 파일 `{ "key": "file", "file": "member/users/files/profile.png", "filename": "profile.png" }` 형식입니다. `content_type`을 선택적으로 지정할 수 있습니다. 파일 참조는 `case` 루트 기준이며, 화면에서 고른 파일은 `case/{tag}/{api_name}/files/`에 저장됩니다.
- `expected.status`: 기대 HTTP 상태 코드입니다.
- `expected.body`: 기대 JSON 응답입니다.
- `expected.strict`: 기본값은 `true`입니다. `true`면 객체의 키, 배열 길이와 순서, 값과 타입이 모두 일치해야 합니다. `false`면 기대 객체에 없는 추가 키와 배열의 뒤쪽 요소를 허용하고, 값이 같은 int·float(예: `9`, `9.0`)는 동일하게 비교합니다. boolean과 숫자(예: `true`, `1`)는 서로 다른 타입입니다.

불일치 시 `$.body.user.id`처럼 정확한 JSON 경로와 기대값·실제값이 출력됩니다.

## 파이프라인 JSON

사용자는 `steps` 배열 순서대로 API 실행 파이프라인을 정의할 수 있습니다.

```json
{
  "project": "member-api.json",
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

- `project`: 파이프라인이 속한 프로젝트 JSON 파일명입니다. 화면에서는 같은 프로젝트의 케이스만 단계로 선택할 수 있습니다.
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
