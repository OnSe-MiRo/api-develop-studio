# OAS-2 OpenAPI 계약 검증

## 화면에서 사용

1. 프로젝트에 OpenAPI JSON 또는 bundle을 저장한다. URL만 저장된 문서는 revision별 원문이 고정되지 않으므로 계약 검사에서 제외한다.
2. **API 목록 → OpenAPI 계약 검증 → 계약 검사**로 현재 명세를 lint한다.
3. **비교 기준 revision**을 선택해 현재 저장된 revision과 비교한다. 응답의 `currentRevision`과 `baselineRevision`이 실제 비교한 snapshot이다. 검사는 저장된 명세를 변경하지 않는다.
4. **API 호출**에서 프로젝트를 선택하고 **OpenAPI 실제 응답 검증**을 켠다. HTTP 호출 직후 status·content type·응답 header·body schema를 검사한다. HTTP 200이어도 계약이 다르면 실패로 표시한다.

실제 응답 검증은 이번 단계에서 빠른 호출에 적용된다. 저장 케이스·파이프라인의 기존 assertion/보고서는 변경하지 않았으며 자동 계약 검증 연동은 후속이다. 검증 결과는 일시적인 호출 응답으로만 반환하며 이력 DB와 Redis에 원문을 추가 저장하지 않는다.

## 정책

- OpenAPI 3.0/3.1 구조: `openapi-spec-validator` 0.7.2.
- 응답 schema: `openapi-schema-validator` 0.6.3, version별 nullable/JSON Schema 처리, format 및 read-context required 검사.
- 구조 오류, 중복 operationId, 잘못된 참조는 오류로 차단한다. operationId/summary 누락은 조직 lint 경고다.
- 응답은 정확한 status → `2XX` 등 범위 → `default` 순서로 선택한다. content type은 parameter를 제거하고 정확한 media type → `type/*` → `*/*` 순서로 선택한다.
- 헤더 이름은 대소문자를 구별하지 않는다. required header 누락 및 scalar schema를 검사한다. header content/array 직렬화는 지원하지 않는다는 실패를 반환한다.
- HEAD·204·304는 본문이 없어야 한다. JSON media type의 잘못된 JSON은 schema 검증 전에 실패한다.
- operation은 method·path template으로 연결하고 구체적인 path가 template보다 우선한다. server는 operation → path item → root 순으로 선택하고 각 operation 안에서만 prefix를 제거한다. 빈 override 배열은 상위 설정을 상속하지 않고 루트 경로로 해석한다. 모호하거나 매칭되지 않으면 실패한다.
- 선언된 server 변수의 문자열 default를 치환한다. enum이 있으면 default가 enum에 속해야 한다. 빠른 호출의 serverVariables 문자열 map으로 명시값을 지정할 수 있다. 아래2026-10-24 계약을 따른다. 명세 위치가 없으면 치환 후 절대 HTTP(S) URL 및 `/`로 시작하는 URL을 지원한다. 선택적 `contractDocumentUrl`이 있으면 일반 상대 server도 이 문서 위치에 대해 해석한다. 문서 위치 정보가 없는 일반 상대 URL(`api/v2`)·query/fragment·미정의 변수는 실패 처리한다.
- project base URL alias는 operation/path server override가 없을 때만 추가한다. 명시적 server가 있으면 해당 prefix를 생략한 경로로 검사하지 않는다. 이 기능은 응답의 경로 매칭이며 origin/host 접근 허용이나 소유권 검증을 대신하지 않는다. 서버 주소를 가져오는 네트워크 동작은 없다.
- 우선순위와 기본값 근거: [OpenAPI 3.1 Operation/Server 정의](https://spec.openapis.org/oas/v3.1.0#operation-object).
- 검사기는 외부 URL/file 참조를 가져오지 않는다. bundle/CLI에서는 root 디렉터리 안의 JSON/YAML 파일을 내부 JSON Pointer로 변환하고 재귀 schema를 유지한다. 파일 200개·원본 총 5 MB·중첩 100단계를 제한한다.
- `$id`, anchor/dynamic reference, JSON Pointer 이외 fragment, 사용자 정의 schema dialect 및 `$ref`와 함께 있는 구조 제약 sibling은 지원하지 않으므로 명시적으로 차단한다. `$ref`의 description/summary sibling은 허용한다.
- 진단에는 규칙 코드와 위치를 남기며 validator가 출력하는 실제 값·enum/example 값·원문 응답 메시지는 포함하지 않는다. 기존 호출 응답은 기존 마스킹 정책을 유지한다.

공식 동작 참고: [명세 검증기](https://github.com/python-openapi/openapi-spec-validator), [schema 검증기](https://github.com/python-openapi/openapi-schema-validator).

## 변경 분류

`breaking`은 operation/status/media 제거, 필수 request parameter·body·property 추가, response 필수 property 제거, 타입·nullable 변경, 방향에 따라 호환을 깨는 enum 변경 등을 포함한다. 경로 공통 parameter와 operation override, 중첩 component reference를 함께 검사한다.

`review`는 schema constraint·조합 변경, 보안·server·header·callback·webhook·operationId 변경 등 자동으로 호환을 입증하지 않는 경우다. `breaking`과 `review` 모두 기본 차단한다. 설명/예시 변경, 새 operation 및 일반적인 optional property 추가는 통과한다. 닫힌 response object에 새 property를 추가하면 review로 분류한다.

범위 밖 확장(`x-*`)의 사용자 정의 의미와 모든 JSON Schema의 수학적 포함 관계를 증명하지는 않는다. 분류는 지원하는 규칙 기반이며 review는 의도적인 보수적 판정이다. 사용하지 않는 component만 바뀐 경우에는 호출 계약 변경으로 분류하지 않는다.

## CLI 및 CI

저장소 root에서 실행한다. macOS/Linux/Windows 모두 Python 명령을 사용할 수 있다.

```sh
python -m api_test.contracts current/openapi.yaml
python -m api_test.contracts current/openapi.yaml --baseline baseline/openapi.yaml --output contract-report.json
```

- exit `0`: 구조 검사 및 호환성 gate 통과. 경고는 허용한다.
- exit `1`: lint 오류 또는 미승인 breaking/review 존재.
- exit `2`: 파일·참조·승인 기록 등 입력 오류.

`.github/workflows/openapi-compatibility.yml`은 PR의 고정 base SHA에서 명세를 추출해 현재 명세와 비교하고 JSON 결과를 artifact로 남긴다. 새 workflow의 원격 실행과 브랜치 보호의 required-check 설정은 이 로컬 구현에서 수행하지 않았다.

## 허용된 변경의 승인 기록

보고서에서 `baselineHash`, `currentHash`, 허용할 변경의 `id`를 복사해 `.openapi-contract-approvals.json`을 작성한다.

```json
{
  "baselineHash": "보고서의 이전 명세 SHA-256",
  "currentHash": "보고서의 현재 명세 SHA-256",
  "approvals": [
    {
      "id": "보고서의 변경 ID",
      "reason": "서비스 소비자 전환을 완료한 계획된 제거",
      "approvedBy": "실제 검토자 식별자"
    }
  ]
}
```

```sh
python -m api_test.contracts current/openapi.yaml --baseline baseline/openapi.yaml --approvals .openapi-contract-approvals.json --output contract-report.json
```

두 hash가 모두 일치해야 하며 알려진 변경 ID·비어 있지 않은 사유와 승인자 기록이 필요하다. 다른 명세로 변경하면 이전 승인은 실패한다. lint 오류는 승인할 수 없다. CI가 이 파일을 읽으며 사유와 승인자 기록을 최종 보고서에 포함한다.

`approvedBy`는 기록용 필드이며 로그인이나 암호학적 서명이 아니다. 실제 승인 권한은 저장소 PR 검토와 보호 규칙으로 관리해야 한다. 이 작업은 승인 기록의 파일/CLI 계약만 구현하며 서버 RBAC나 인증된 승인 UI를 추가하지 않는다.

## HTTP

`POST /api/projects/{reference}/openapi/contract`

```json
{"baselineRevision": 1}
```

본문 `{}`는 현재 lint만 수행한다. `baselineRevision`은 양의 정수다. 현재 프로젝트와 과거 revision 조회는 store에 바인딩된 workspace 안에서만 수행한다. 없는 프로젝트/revision은 404, 잘못된 입력은 400이다. body로 workspace·actor를 선택하지 않는다.

`POST /api/request`에 `validateContract: true`와 `project`를 전달하면 응답에 `contract: {valid, operation?, issues}`가 추가된다. 명세 lint 오류는 외부 HTTP 요청 전에 차단한다. 기존 호출 계약은 검증을 켜지 않으면 유지한다.

## Server 경로 매칭 검증 (2026-10-23)

- feature/openapi-server-matching은 파이프라인이 병합된 develop f6b890f에서 분기했다. 새 변경은 미커밋/미푸시다.
- 3.0/3.1 우선순위, 다중 server, 기본값/enum, prefix 경계, 빈 override, 미정의 변수/일반 상대 URL 거부, concrete 우선·모호함 거부, 값 비노출과 기존 project base alias를 검증했다. 실제 loopback HTTP 빠른 호출 경로에서 올바른 경로와 상위 prefix 경로의 HTTP200 계약 판정을 확인했다.
- 집중 계약/API 테스트28개, 전체 Python579개(skip0,83.573초), 생성 최신성·diff 검사 통과. 이번 단계는 React 변경이 없으며 앞선 파이프라인 복구에서 frontend131개 및 build 통과를 확인했다.
- 실제 브라우저의 격리 로컬모드/임시 DB에서 `/fixture/v2/items`는 계약 통과, `/old/items`는 HTTP200이어도 operation_or_reference_error로 실패했다. [통과 화면](openapi-server-matching-browser.jpg), [실패 화면](openapi-server-mismatch-browser.jpg). 콘솔 오류/경고0개. 운영 issuer나 외부 API를 사용하지 않았다.
- 임시 fixture 최초 실행의 중괄호 오류와 SPA fallback 라우트 우선순위 오류를 수정했다. 잘못된 HTML 응답은 undocumented_content_type으로 정상 거부됐으며 수정 후 실제 JSON 응답으로 재검증했다. 제품 코드의 실패로 혼동하지 않는다.
- 로그: `/tmp/oas-server-focused.log`, `/tmp/oas-server-all.log`, `/tmp/oas-server-generated-check.log`. 저장 케이스/파이프라인 자동 계약검증·사용자 지정 server 변수·일반 상대 server 해석은 후속이다.

## OAS-2 server 변수 명시값 완료 (2026-10-24)

- server 매칭 커밋b47709b·로컬 develop 병합d5dd592 완료. 새 feature/openapi-server-variables에서 빠른 호출 serverVariables map 및 JSON 입력 UI를 구현했다. 실제 URL은 변경하지 않고 응답 경로 매칭에만 적용한다.
- validateContract=true에서만 지정한다. 최대32개 문자열, 이름1~128자·값512자 이하이며 제어문자는 거부한다. 미지정 변수는 default, 빈 map도 기존 동작이다. 사용되지 않는 변수·enum 위반·매칭 실패·형식 오류는 입력값 없는400으로 대상 호출 전에 차단한다. 명시값 사용 시 project base alias로 우회하지 않는다.
- UI에서 검증 해제 시 전송하지 않고 프로젝트/환경 변경 시 초기화한다. 프로젝트/케이스/이력에 값을 추가 저장하지 않는다. 소유권·인증 정책은 기존대로 적용하며 일반 상대 server 해석과 저장 케이스 자동 계약검증은 후속이다.
- 검증: 계약/API 집중34개(실제 loopback HTTP 포함), 전체 Python585개(skip0,104.414초), frontend133개(31파일), production build·생성 최신성·diff 검사 통과. 부분 치환·변수 scope·모호함·값 비노출·입력경계·UI 초기화를 포함한다.
- 실제 브라우저: 격리 로컬 fixture에서 default v1 및 명시값v2의 HTTP200/계약 통과, v3/API400·잘못된JSON/UI 차단을 확인했다. 대상 카운터는 성공2회 이후 증가하지 않았다. 프로젝트 전환 초기화 및 콘솔 오류/경고0 확인. [화면](openapi-server-variables-browser.jpg).
- 실패/보완: 모호함 fixture가 실제 중복이 아닌 v1 기본값을 사용해1개 실패했고 v2로 바로잡았다. 신규 UI2개 label 조회 실패는 textarea의 명시적 접근성 이름으로 수정했다. npm root 실행은 web/에서 재실행했다. 모두 수정 후 위 검증을 통과했다. 문서 쓰기 자동검토 시간초과는 같은 작업을 재요청했다.
- 로그: /tmp/server-vars-focused-python.log, /tmp/server-vars-python-all.log, /tmp/server-vars-web-all.log, /tmp/server-vars-build.log, /tmp/server-vars-generated-check.log.
- 반영: 새 기능은 d5dd592 기준 미커밋/미병합, 원격 푸시 및 원본 worktree 변경 없음. 운영 배포·전체 부하 캠페인·기존 실패/unknown은 변경하지 않는다.


요청 예: `{"project":"demo.json","url":"https://api.example.test/v2/items","validateContract":true,"serverVariables":{"version":"v2"}}`. 실제 요청 URL은 직접 입력한다.

## 문서 기준 상대 server 해석 (2026-10-24, 다음 단계)

빠른 호출에서 계약 검증을 켜면 **OpenAPI 문서 기준 URL**을 입력할 수 있다. 이 값은 저장된 명세의 원래 위치를 명시하는 일회성 힌트이며 해당 URL에서 문서를 다운로드하지 않는다. 실제 호출 URL이나 프로젝트 Base URL도 변경하지 않는다. 빈 입력은 이전 동작을 유지한다.

예를 들어 문서 위치가 `https://docs.example/service/spec/openapi.json`이고 operation server가 `../{version}`, version이 v2라면 server 경로는 `/service/v2`가 된다. `v2`는 `/service/spec/v2`, `/v2`는 `/v2`가 된다. 디렉터리 기준 URL의 마지막 `/`는 의미가 있으므로 임의로 덧붙이지 않는다. [OpenAPI Server Object](https://spec.openapis.org/oas/v3.1.0.html#server-object)의 문서 기준 규칙을 적용한다.

API 예:

```json
{"project":"demo.json","url":"https://api.example/service/v2/items","validateContract":true,"serverVariables":{"version":"v2"},"contractDocumentUrl":"https://docs.example/service/spec/openapi.json"}
```

- contractDocumentUrl은 검증이 켜졌을 때만 지정한다. 1~2048자의 HTTP(S) 절대 URL이며 사용자정보·query·fragment·공백/제어문자·역슬래시를 허용하지 않는다. 명시적 null/빈값/상대값은400이고 UI의 빈 입력은 필드 자체를 보내지 않는다.
- server 변수 치환 후 URL reference를 문서 위치에 대해 해석한다. operation→path→root 우선순위와 concrete path 우선/모호함 거부는 유지한다. 명시적 문서 기준 URL이 있으면 project base alias로 잘못된 기준을 우회하지 않는다.
- 제공된 기준 URL의 형식 또는 매칭이 잘못되면 실제 대상 호출 전에 값 비노출400으로 거부한다. 기준 URL을 생략한 일반 상대 server는 기존처럼 응답 계약 실패다. 검증 해제 시 필드를 보내지 않고 프로젝트/환경 변경 시 지운다. 프로젝트·케이스·이력 저장에 추가하지 않는다.
- 이 단계는 한 명세의 entry document 위치를 명시하는 범위다. 다중 외부 문서별 위치 추적, 원격 참조/명세 가져오기, host/origin 접근 허용, 저장 케이스/파이프라인 자동 계약 검증은 포함하지 않는다. 기존 소유권/인증 정책은 그대로다.

검증: 계약/API 집중40개(실제 loopback HTTP 포함), 전체 Python591개(skip0,188.541초), frontend135개(31파일), production build·생성 최신성·diff 검사 통과. 3.0/3.1, 상대·상위·루트·절대·scheme-relative URL, 변수 기본값/명시값, trailing slash, server scope, project alias 우회 방지, 부적절한 기준 URL/비노출/요청 전 차단, 문서 힌트 미접속을 포함한다.

실제 브라우저: 격리 로컬 fixture에서 기준 없음은 계약 실패, 올바른 기준과 default v1/명시값 v2는 통과했다. 대상 호출3회 후 잘못된 기준 및 file URL을 입력해도 카운터가 늘지 않았고 `/service/spec/openapi.json` 요청은0건이었다. 프로젝트 전환 초기화·콘솔 오류/경고0 확인. [통과 화면](openapi-relative-server-browser.jpg). 첫 공식 명세 조회 도구의 연결 실패는 재조회로 해소했다.

로그: /tmp/relative-server-focused-python.log, /tmp/relative-server-python-all.log, /tmp/relative-server-web-all.log, /tmp/relative-server-build.log, /tmp/relative-server-generated-check.log. 직전 serverVariables 작업과 같은 feature/openapi-server-variables에서 계속 작업했으며 이번에도 커밋·병합·푸시는 하지 않았다.
