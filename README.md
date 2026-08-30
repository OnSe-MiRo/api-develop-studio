# API Develop Studio

JSON으로 HTTP 요청과 기대 응답을 정의하고, 응답 데이터가 정확히 같은지 검증하는 Python API 테스트 도구입니다.

## React 웹 화면

기존 데스크톱 GUI 대신 React 기반 웹 화면을 제공합니다. API 케이스와 파이프라인을 한 화면에서 만들고, 저장·불러오기·실행할 수 있습니다.

API 케이스와 파이프라인의 `실행만` 버튼은 현재 화면의 값을 저장하지 않고 임시 파일로 실행합니다. 임시 파일은 실행 직후 삭제되며, 실행 결과 로그는 기존처럼 `logs/`에 남습니다. `저장 후 실행`은 현재 값을 JSON 파일로 저장한 뒤 실행합니다.

저장된 API 케이스는 선택 후 `삭제` 버튼으로 제거할 수 있으며, 삭제 전 확인 창이 표시됩니다.

API 케이스와 파이프라인 목록에서도 각 항목 오른쪽의 `×` 버튼으로 바로 삭제할 수 있습니다.

저장된 파이프라인도 같은 방식으로 삭제할 수 있습니다.

프로젝트 목록의 `×` 버튼으로 프로젝트를 삭제할 수 있습니다. 연결된 파이프라인은 프로젝트와 함께 삭제됩니다. 연결된 API 케이스가 있으면 프로젝트를 삭제할 수 없으므로 케이스를 먼저 삭제해야 합니다.

### 화면에서 작업하는 순서

1. 첫 화면의 `프로젝트 목록`에서 `새 프로젝트 만들기`를 누르고 프로젝트 이름과 Base URL을 입력합니다. 필요하면 `설정 > OpenAPI 설정`에 문서 URL을 입력하거나 JSON 파일을 선택합니다. 프로젝트 JSON 파일은 이름을 기준으로 자동 생성됩니다. 저장된 프로젝트 카드의 `수정` 버튼에서는 프로젝트 이름, Base URL, API 문서, Proxy, verify를 변경할 수 있으며 파일명과 연결된 케이스·파이프라인은 유지됩니다.
2. 저장하면 해당 프로젝트의 `API 케이스 목록` 화면으로 바로 이동합니다. 목록의 `새 케이스`를 누르면 케이스 설정 화면에서 Tag, API 이름, 케이스 명, HTTP method, URL을 입력하고 저장할 수 있습니다. 목록의 기존 케이스를 누르면 같은 설정 화면에서 수정하거나 실행할 수 있습니다.
3. `Params`, `Authorization`, `Headers`, `Body` 탭에서 요청 값을 입력합니다. Params의 마지막 행에 값을 입력하거나 `Parameter 추가`를 누르면 다음 입력 행을 만들 수 있습니다. Body는 `raw JSON` 또는 `form-data`를 선택할 수 있으며, form-data에서는 텍스트와 파일 행을 추가할 수 있습니다.
4. 기대 HTTP 상태와 응답 body를 입력하고, 필요에 따라 `strict 비교`를 설정합니다.
5. 저장하지 않은 현재 값만 확인하려면 `실행만`을 누릅니다. 케이스 파일까지 저장하려면 `저장` 또는 `저장 후 실행`을 사용합니다.
6. 왼쪽 사이드바의 `파이프라인` 목록에서 새 파이프라인을 만들거나 기존 항목을 선택합니다. 설정 화면에서 같은 프로젝트의 저장된 케이스를 단계로 추가하고 순서·재시도 정책을 지정합니다. 파이프라인도 `실행만`으로 저장 없이 현재 구성만 실행할 수 있습니다.

### API 문서에서 케이스 초안 채우기

프로젝트 생성 또는 수정 화면의 `설정 > OpenAPI 설정`에서 OpenAPI 3.x 또는 Swagger 2.0의 원본 JSON/YAML 문서 URL(예: `https://api.example.com/openapi.json`)을 입력하거나 로컬 JSON 파일을 선택하고 저장합니다. URL과 파일 중 하나만 사용할 수 있으며, URL은 Swagger UI HTML 페이지 주소가 아니라 해당 UI가 참조하는 원본 문서 주소여야 합니다. 업로드하는 JSON 파일은 5MB 이하여야 합니다.

해당 프로젝트의 케이스 설정을 열면 문서가 자동으로 불러와집니다. `문서 API 선택`에서 API를 선택하면 문서의 경로와 method, query/header/path 파라미터 키와 예시값, JSON 요청 body, 기대 HTTP 상태, 응답 body 예시가 케이스 편집기에 자동 반영됩니다. 문서가 갱신된 경우에는 `문서 새로 불러오기`를 사용하세요. 문서에 `example`, `examples`, `default`, `enum`이 없으면 schema 타입을 기반으로 편집 가능한 기본 예시를 만듭니다. 반영 후 실제 서비스 규칙에 맞게 값과 strict 비교 여부를 검토한 뒤 저장하세요.

### OpenAPI API 작성 및 클라이언트 SDK 생성

상단의 `API 작성`을 선택하면 프로젝트별 `API 목록`과 `SDK 생성` 메뉴를 사용할 수 있습니다. `API 목록`의 `API 작성` 버튼에서는 method, path, operation ID, tag, summary, 파라미터, 요청·응답 JSON 예시를 입력해 OpenAPI 3.x operation을 저장할 수 있습니다. 작성된 API는 method별 색상과 path, 요청·응답 내용을 펼쳐보는 Swagger 스타일 목록으로 표시됩니다. 문서가 없는 프로젝트에서 처음 저장하면 OpenAPI 3.0.3 문서를 자동 생성하며, URL 문서는 원격 원본을 변경하지 않고 프로젝트 내부 편집 사본으로 전환합니다. Swagger 2.0 문서는 조회할 수 있지만 새 API 작성 전 OpenAPI 3.x로 변환해야 합니다.

`SDK 생성`에서 Python, JavaScript, TypeScript(Axios), Java, Kotlin, Go, C# 중 하나를 선택하고 `ZIP 생성 및 다운로드`를 누릅니다. 서버는 프로젝트에 저장된 OpenAPI URL 또는 업로드 문서를 다시 검증한 뒤 선택한 언어의 클라이언트 SDK를 생성합니다. 다운로드 ZIP에는 생성된 소스와 해당 시점의 문서를 정규화한 `openapi.yaml`이 함께 들어갑니다. URL 프로젝트에서 `No Proxy`를 선택했다면 SDK 생성 시 문서를 다시 가져올 때도 환경 프록시를 우회합니다.

SDK 생성은 OpenAPI Generator CLI를 사용하므로 Docker 밖에서 실행할 때 Java 11 이상이 필요합니다. `requirements.txt`를 설치하면 프로젝트에 고정된 Generator 버전도 함께 설치됩니다. Docker 이미지에는 Java 런타임이 포함됩니다.

프로젝트 Base URL이 `https://api.example.com`일 때 케이스 URL에 `/users`를 입력하면 `https://api.example.com/users`로 실행됩니다. 외부 API처럼 절대 URL을 입력한 경우에는 Base URL을 붙이지 않습니다.

`strict 비교`를 켜면 값과 타입이 모두 같아야 합니다. 예를 들어 `9.0`과 `9`는 서로 다른 타입으로 실패합니다. 끄면 객체의 추가 키와 배열의 뒤쪽 요소를 허용하며, 숫자 값이 같다면 `9.0`과 `9`는 통과합니다. `true`와 `1`은 strict 여부와 관계없이 서로 다른 값으로 비교합니다.

기대 응답에서는 `기대 응답 일치`와 `변수별 조건`을 독립적으로 선택할 수 있고 두 방법을 동시에 실행할 수도 있습니다. `기대 응답 일치`는 Expected body와 실제 응답의 값·구조를 비교하고, `변수별 조건`은 기대 응답 JSON의 중첩 객체와 배열을 변수 목록으로 자동 추출해 각 변수의 숫자 범위, 타입, 존재 여부, 문자열·배열 길이를 검사합니다. 조건 전용 모드에서는 Expected body를 변수 추출용 예시로만 사용하므로 실제 응답과 값이 달라도 조건만 만족하면 통과합니다.

터미널을 두 개 열어 아래처럼 실행합니다.

```bash
# 터미널 1: Python 파일 API 및 테스트 실행 서버
python3 react_server.py

# 터미널 2: React 개발 서버
cd web
npm install
npm run dev
```

처음 로컬 실행할 때는 프로젝트 루트에서 Python 의존성도 설치합니다.

```bash
python3 -m pip install -r requirements.txt
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
- `EXAMPLE_PROJECT`: 기본값은 `true`이며, 컨테이너 안의 예제 API와 `example-api` 프로젝트·케이스·파이프라인을 제공합니다. `false`로 설정하면 예제 API가 404로 비활성화되고 웹 프로젝트 목록에도 표시되지 않습니다.
- `encryption` 서비스: Docker 환경에서 프로젝트 보안 변수를 암·복호화하는 내부 전용 컨테이너입니다. 최초 실행 시 `encryption_keys` Docker 볼륨에 Fernet 키를 자동 생성하고, 재빌드·재시작에서도 같은 키를 사용합니다. 기존 `API_TEST_ENCRYPTION_KEY` 값이 있으면 최초 실행 때 그 값을 볼륨으로 이전합니다. 키를 확인하려면 `docker compose exec encryption cat /var/lib/api-test-encryption/key`를 실행하세요. `docker compose down -v`로 이 볼륨을 제거하면 기존 보안 변수를 복호화할 수 없습니다.
- `API_TEST_ENCRYPTION_KEY`: Docker 밖에서 API를 직접 실행할 때 사용하는 Fernet 키입니다. Docker Compose에서는 값이 있을 경우 첫 실행 때만 `encryption` 서비스의 영속 키 초기값으로 사용합니다.
- `CASE_VOLUME_PATH`, `LOG_VOLUME_PATH`: 각각 컨테이너의 `/app/case`, `/app/logs`에 마운트할 호스트 경로입니다. 기본값은 `./case`, `./logs`입니다. form-data로 올린 파일도 `/app/case` 아래에 저장되므로 `CASE_VOLUME_PATH`를 유지해야 저장 후 재실행할 수 있습니다.
- `PROJECT_VOLUME_PATH`: 프로젝트 Base URL 설정을 보관할 컨테이너의 `/app/projects`에 마운트할 호스트 경로입니다. 기본값은 `./projects`입니다.
- `DATA_VOLUME_PATH`: 협업용 SQLite 저장소를 보관할 컨테이너의 `/app/data`에 마운트할 호스트 경로입니다. 기본값은 `./data`입니다.

예를 들어 케이스와 로그를 프로젝트 밖에 보관하려면 `.env`에서 다음처럼 변경합니다. Windows 경로는 `C:/api-test/case`처럼 `/`를 사용합니다.

```env
CASE_VOLUME_PATH=/data/api-test/case
LOG_VOLUME_PATH=/data/api-test/logs
PROJECT_VOLUME_PATH=/data/api-test/projects
DATA_VOLUME_PATH=/data/api-test/studio-data
```

중지하려면 다음 명령을 사용합니다.

```bash
docker compose down
```

### 컨테이너 내장 예제 API

외부 네트워크 없이 API 케이스와 파이프라인을 확인하려면 `.env`에서 `EXAMPLE_PROJECT=true`로 설정한 뒤 컨테이너를 다시 시작하세요. `example-api` 프로젝트를 열어 개별 케이스를 실행하거나 `example-api.json` 파이프라인을 실행할 수 있습니다. 예제 API는 `POST /example-api/users`로 사용자 생성 결과를 반환하고, 다음 단계가 그 응답의 `id`를 사용해 `GET /example-api/users/{id}`를 호출합니다. `GET /example-api/secure-data`는 `X-API-Key` 헤더 인증 예제를 제공하며, `security/get_secure_data` 케이스는 프로젝트 공통 보안 변수 `{{project.api_key}}`를 사용합니다. 이 값은 현재 암호화 서비스로 암호화되어 예제 프로젝트에 한 번 저장되며, 기능 확인용 공개 예제이므로 실제 서비스 비밀값으로 사용하면 안 됩니다.

## 빠른 실행

### 하나의 파이프라인 실행

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py pipelines/example-api.json
```

### 기본 실행: 모든 파이프라인 실행

파이프라인 파일과 `--case`를 모두 생략하면 `pipelines/` 및 하위 디렉터리의 모든 `.json` 파이프라인을 이름순으로 실행합니다.

```bash
python3 run_api_tests.py
```

### 여러 파이프라인 한 번에 실행

파이프라인 파일을 공백으로 구분해 나열합니다. 앞 파이프라인이 실패해도 나머지 파이프라인은 계속 실행하며, 실패한 실행이 하나라도 있으면 프로세스 종료 코드는 `1`입니다.

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py pipelines/example-api.json --log-dir test-logs
```

### 개별 API 케이스 실행

`--case`에 `case` 루트 기준 경로를 넣으면 파이프라인 없이 API 하나 또는 여러 개를 실행합니다. 여러 케이스는 명령 한 번으로 입력되며, 결과와 로그 순서를 보장하기 위해 입력한 순서대로 실행됩니다.

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py --case example/users/get_user.json --log-dir test-logs
```

```bash
python3 run_api_tests.py --case \
  example/users/create_user.json \
  example/users/get_user.json \
  --log-dir test-logs
```

### 파이프라인과 개별 API 함께 실행

파이프라인 파일을 먼저 쓰고 `--case`를 뒤에 붙이면 한 명령에서 함께 실행할 수 있습니다. 파이프라인들이 먼저 실행된 뒤 개별 API 케이스들이 실행됩니다. 두 종류 모두 실패하더라도 남은 대상은 계속 실행됩니다.

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py \
  pipelines/example-api.json \
  --case example/users/get_user.json \
  --log-dir test-logs
```

`pipelines/example-api.json`은 다음 2단계 예제입니다. 실행하려면 API 서버를 `EXAMPLE_PROJECT=true`로 시작해야 합니다.

1. `create_user`: 예제 사용자를 생성합니다.
2. `get_user`: 첫 단계 응답의 `id`를 URL 값 전달 설정으로 전달해 사용자를 조회합니다.

## 내장 예제 API 케이스

`EXAMPLE_PROJECT=true`이면 외부 네트워크 없이 다음 케이스를 실행할 수 있습니다.

| Method | 케이스 파일 | 검증 내용 |
| --- | --- | --- |
| POST | `example/users/create_user.json` | 사용자 생성 및 `201` 응답 |
| GET | `example/users/get_user.json` | 사용자 조회 및 `200` 응답 |
| GET | `example/security/get_secure_data.json` | `X-API-Key` 인증 및 `200` 응답 |

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py pipelines/example-api.json --log-dir test-logs
```

API Key 예제 케이스만 실행하려면 다음 명령을 사용합니다.

```bash
EXAMPLE_PROJECT=true python3 run_api_tests.py --case example/security/get_secure_data.json --log-dir test-logs
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

## 협업 영구 저장소

웹 스튜디오에서 저장하는 프로젝트·API 케이스·파이프라인은 기본적으로 `data/studio.db` SQLite 데이터베이스에 저장됩니다. 각 문서는 변경되지 않는 ID와 증가하는 리비전을 가지며, 수정할 때마다 전체 JSON 스냅샷과 변경 사용자·시각이 새 리비전으로 기록됩니다.

기존 CLI 호환성을 위해 현재 리비전은 동시에 다음 JSON 파일로 반영됩니다.

- 프로젝트: `projects/{project_file}.json`
- API 케이스: `case/{tag}/{api_name}/{case_file}.json`
- 파이프라인: `pipelines/{pipeline_file}.json`

서버를 처음 실행하면 기존 JSON 파일을 리비전 1로 자동 가져옵니다. 서버가 중지된 동안 Git 등에서 JSON 파일이 변경된 경우 다음 시작 시 새 리비전으로 가져옵니다. 따라서 웹 협업 데이터의 기준은 SQLite이고, JSON은 CLI 실행과 Git 내보내기를 위한 현재 버전 투영본입니다.

문서 조회 API는 다음 저장 메타데이터를 반환합니다. 편집 화면은 이 값을 저장 요청에 다시 보내며, 그 사이 다른 사용자가 문서를 저장했다면 서버가 `409 Conflict`를 반환해 조용한 덮어쓰기를 방지합니다. `_storage`는 실행용 JSON 파일에는 기록되지 않습니다.

```json
{
  "_storage": {
    "id": "doc_...",
    "revision": 3,
    "created_at": "2026-08-26T01:00:00+00:00",
    "updated_at": "2026-08-26T01:30:00+00:00"
  }
}
```

리비전 목록은 `GET /api/cases/{reference}/revisions`, `GET /api/pipelines/{reference}/revisions`, `GET /api/projects/{reference}/revisions`로 조회할 수 있습니다. 삭제는 DB에서 소프트 삭제로 기록하고 CLI용 JSON 투영본만 제거합니다.

로컬 실행에서 DB 위치를 바꾸려면 `STUDIO_DB_PATH` 환경 변수를 사용합니다. Docker에서는 `/app/data/studio.db`로 고정되고 `DATA_VOLUME_PATH`가 해당 디렉터리를 보존합니다. 백업할 때는 `data/`, `case/`, `projects/`, `pipelines/`와 `API_TEST_ENCRYPTION_KEY`를 함께 관리해야 합니다.

현재 `X-Studio-Actor` 요청 헤더는 리비전 작성자를 구분하기 위한 감사 식별자이며 인증 수단이 아닙니다. 실제 다중 사용자 배포 전에는 로그인·세션과 프로젝트 역할 검증을 연결해야 합니다.

## 프로젝트 JSON

프로젝트마다 Base URL을 한 번만 저장하고, 케이스에서는 프로젝트 파일명과 상대 URL을 연결합니다.

```json
{
  "name": "회원 API",
  "base_url": "https://api.example.com",
  "variables": {
    "plain": {
      "tenant_id": "alpha"
    },
    "secret": {
      "api_key": "암호화된 Fernet 토큰"
    }
  },
  "advanced": {
    "use_proxy": true,
    "http_proxy": "http://proxy.example.com:8080",
    "https_proxy": "http://proxy.example.com:8080",
    "verify": true
  }
}
```

`projects/member-api.json`을 저장한 뒤 케이스에 `"project": "member-api.json"`, `"url": "/users"`를 지정하면 `https://api.example.com/users`를 호출합니다.

- `advanced.use_proxy`: 기본값은 `true`입니다. `false`이면 등록된 주소와 환경 프록시를 모두 사용하지 않습니다.
- `advanced.http_proxy`, `advanced.https_proxy`: 선택 사항입니다. `use_proxy`가 `true`일 때 값이 있으면 각각 HTTP와 HTTPS 요청에 자동으로 적용되며, 비우면 해당 프로토콜은 직접 연결합니다. 화면의 `HTTP/HTTPS 공통 주소 사용`을 선택하면 한 번의 입력으로 두 값에 같은 주소를 저장합니다. 많은 사내 프록시는 HTTPS 요청에도 `http://proxy.example.com:8080` 형식의 프록시 주소를 사용합니다.
- `advanced.verify`: 기본값은 `true`입니다. `false`로 설정하면 TLS 인증서 검증을 생략합니다. 자체 서명 인증서를 사용하는 개발 환경에서만 사용하세요.

### 프로젝트 공통 변수

프로젝트 수정 화면의 `설정 > 프로젝트 공통 변수`에서 다음 두 종류를 관리합니다.

- `일반 변수`: 프로젝트 JSON의 `variables.plain`에 평문으로 저장합니다. 공개되어도 되는 테넌트 ID, 공통 경로 등에 사용합니다.
- `보안 변수`: `variables.secret`에 Fernet 암호문으로 저장합니다. API Key, Access Token처럼 공개되면 안 되는 값에 사용합니다. 프로젝트 조회 API와 수정 화면에는 실제 값이 다시 표시되지 않습니다.

보안 변수를 사용하려면 먼저 `.env`에 암호화 키를 설정합니다. 키는 한 번 생성해 계속 사용하고 별도 비밀 저장소나 안전한 백업에 보관하세요. 키를 잃거나 바꾸면 기존 보안 변수를 복호화할 수 없습니다.

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```env
API_TEST_ENCRYPTION_KEY=생성한_Fernet_키
```

API 케이스의 URL·Params·Authorization·Headers·JSON Body·form-data 텍스트 값에서 `{{project.변수명}}`을 사용할 수 있습니다. 요청을 실행하기 직전에 현재 프로젝트의 값으로 치환됩니다.

케이스 설정의 `케이스 전용 보안 변수`는 해당 API 케이스에서만 쓰는 API Key·토큰을 암호화해 저장합니다. 저장한 값은 다시 표시되지 않으며, 같은 케이스의 URL·Params·Authorization·Headers·JSON Body·form-data 텍스트 값에서 `{{case.변수명}}`으로 참조합니다. 프로젝트 공통 보안 변수와 케이스 전용 보안 변수를 함께 사용할 수 있고, 실행 로그에서는 둘 다 마스킹됩니다.

```json
{
  "project": "member-api.json",
  "request": {
    "method": "GET",
    "url": "/tenants/{{project.tenant_id}}/users",
    "headers": {
      "X-API-Key": "{{project.api_key}}"
    }
  },
  "expected": {
    "status": 200
  }
}
```

정의되지 않은 변수를 참조하거나 암호화 키가 없거나 다른 경우에는 HTTP 요청 전에 구성 오류로 중단됩니다. 실행 실패 로그에서는 사용된 보안 변수 값이 `***REDACTED***`로 마스킹됩니다.

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
- `request.headers`, `request.body`: 선택 사항입니다. `body`는 JSON으로 직렬화됩니다. 프로젝트 공통값은 `{{project.변수명}}`으로 참조할 수 있습니다.
- `request.form_data`: 선택 사항입니다. 지정하면 `body` 대신 `multipart/form-data` 요청을 만듭니다. 각 행은 텍스트 `{ "key": "title", "value": "profile" }` 또는 파일 `{ "key": "file", "file": "member/users/files/profile.png", "filename": "profile.png" }` 형식입니다. `content_type`을 선택적으로 지정할 수 있습니다. 파일 참조는 `case` 루트 기준이며, 화면에서 고른 파일은 `case/{tag}/{api_name}/files/`에 저장됩니다.
- `expected.status`: 기대 HTTP 상태 코드입니다.
- `expected.body`: 기대 JSON 응답입니다.
- `expected.strict`: 기본값은 `true`입니다. `true`면 객체의 키, 배열 길이와 순서, 값과 타입이 모두 일치해야 합니다. `false`면 기대 객체에 없는 추가 키와 배열의 뒤쪽 요소를 허용하고, 값이 같은 int·float(예: `9`, `9.0`)는 동일하게 비교합니다. boolean과 숫자(예: `true`, `1`)는 서로 다른 타입입니다.
- `expected.assertions`: 응답 경로에 적용할 조건 배열입니다. 기존 `expected.body` 비교와 함께 사용할 수 있으며 모든 조건을 만족해야 합니다.
- `expected.validation_modes.exact_body`: `true`이면 `expected.body`와 실제 body를 비교합니다.
- `expected.validation_modes.conditions`: `true`이면 `expected.assertions`를 평가합니다.

불일치 시 `$.body.user.id`처럼 정확한 JSON 경로와 기대값·실제값이 출력됩니다.

### 검증 방법 선택

| exact_body | conditions | 실행 방식 |
| --- | --- | --- |
| `true` | `false` | 기대 응답 일치만 검증 |
| `false` | `true` | 변수별 조건만 검증 |
| `true` | `true` | 기대 응답 일치와 변수별 조건을 모두 검증 |

`validation_modes`가 없는 기존 케이스는 `body`와 `assertions`의 존재 여부에 따라 이전과 동일하게 동작합니다.

### 변수별 조건 검증

다음 케이스는 Expected body의 값 자체는 비교하지 않고, `age`가 18 이상 65 이하이고, `score`가 80 이상이며, `items`가 1~100개인지 검증합니다.

```json
{
  "request": {
    "url": "https://api.example.com/users/1"
  },
  "expected": {
    "status": 200,
    "body": {
      "age": 24,
      "score": 80,
      "items": []
    },
    "validation_modes": {
      "exact_body": false,
      "conditions": true
    },
    "assertions": [
      {
        "path": "body.age",
        "operator": "between",
        "min": 18,
        "max": 65,
        "include_min": true,
        "include_max": true
      },
      {
        "path": "body.score",
        "operator": "gte",
        "value": 80
      },
      {
        "path": "body.items",
        "operator": "length_between",
        "min": 1,
        "max": 100
      }
    ]
  }
}
```

지원 조건은 다음과 같습니다.

| operator | 검증 내용 | 설정값 |
| --- | --- | --- |
| `gt`, `gte`, `lt`, `lte` | 숫자 초과·이상·미만·이하 | `value` |
| `between` | 숫자 범위 | `min`, `max`, 선택적 `include_min`, `include_max` |
| `exists`, `not_exists` | 경로 존재·미존재 | 없음 |
| `type` | JSON 타입 | `value`: `number`, `integer`, `string`, `boolean`, `object`, `array`, `null` |
| `length_between` | 문자열 또는 배열 길이 범위 | 0 이상의 정수 `min`, `max` |

잘못된 경로, 지원하지 않는 조건, 숫자가 아닌 범위 또는 최솟값이 최댓값보다 큰 설정은 HTTP 요청 전에 구성 오류로 처리됩니다. 조건 불일치는 정확한 응답 경로, 조건, 실제값과 함께 로그에 기록됩니다.

실행 결과와 로그에는 등록한 모든 변수 조건의 집계(`TOTAL`, `PASS`, `FAIL`)와 조건별 판정, 실제값이 표시됩니다. 따라서 전체 케이스가 통과한 `실행 완료` 상태에서도 각 조건이 어떤 값으로 통과했는지 확인할 수 있습니다.

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
      "retry_interval_seconds": 2,
      "input_mappings": [
        {
          "source_step": "create_user",
          "response_path": "body.id",
          "target": "url",
          "template": "/users/{{value}}"
        },
        {
          "source_step": "create_user",
          "response_path": "body.id",
          "target": "body",
          "target_key": "user_id"
        }
      ]
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
- `steps[].input_mappings`: 이전 단계의 응답값을 이 단계 요청에 전달하는 선택 설정입니다. 파이프라인 화면에서 각 단계의 `값 전달` 버튼으로 구성할 수 있으며 원본 API 케이스는 변경하지 않습니다.
  - `source_step`: 값을 가져올 이전 단계 이름입니다.
  - `response_path`: `body.id`, `body.user.id`, `status` 형식의 응답 경로입니다.
  - `target`: `url`, `header`, `body` 중 적용 위치입니다. `header`, `body`에는 `target_key`가 필요하며 Body는 `user.id`처럼 중첩 키를 지정할 수 있습니다.
  - `template`: 기본값은 `{{value}}`입니다. URL 조합은 `/users/{{value}}`, Header 조합은 `Bearer {{value}}`처럼 입력합니다.

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
