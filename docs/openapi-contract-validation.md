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
- operation은 method·path template으로 연결하고 구체적인 path가 template보다 우선한다. 프로젝트 base URL 또는 root servers의 path prefix를 제거할 수 있다. 모호하거나 매칭되지 않으면 실패한다. operation별 server override·server variable 확장은 후속이다.
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
