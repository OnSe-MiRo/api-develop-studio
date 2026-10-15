# OpenAPI 원본 편집 API

OAS-1 편집기는 프로젝트에 저장된 OpenAPI 3.0/3.1 문서의 **원본 소유 파일**을 수정한다. 표시용 ref 해석 결과나 새 기본값을 삽입하는 분할 결과를 저장하지 않는다. 인라인 JSON은 하나의 `docs_file`, 분할 YAML/JSON은 기존 `docs_bundle`의 파일별 원문을 유지한다. 문서가 없는 새 프로젝트의 GET은 `origin.kind: draft`와 제목·버전·빈 paths만 있는 **저장 전 가상 3.0.3 초안**을 반환한다. 이 초안은 preview에서도 저장하지 않으며 apply 또는 명시적 import apply만 revision을 생성한다. 원격 `docs_url`만 있는 프로젝트는 GET 때 기존 20초·5 MB 제한으로 원본을 읽고, apply 때 명시적인 로컬 `docs_file` 사본으로 전환한다. 원격 내용이 그 사이 바뀌면 409로 거부한다.

`GET /api/projects/{reference}/openapi/editor`는 다음 정보를 반환한다.

- `source.kind` (`file` 또는 `bundle`), `entrypoint`, `files`(파일별 파싱된 **원본**), `rawFiles`(bundle의 원문 텍스트), 원격 소스면 `source.origin`
- `catalog.schemas`와 `securitySchemes`의 논리 이름, 실제 `file`·JSON `pointer`, 선언 위치 `entrypointPointer`; schema의 `refByFile`은 해당 파일에서 사용할 수 있는 `$ref`
- `catalog.operations`의 method/path, 실제 owner `file`·`pointer`; 전체 `references` 목록
- `sourceDigest`(원본 파일 내용 지문)과 `_storage.revision`

값 편집은 실제 owner `file`·`pointer`를 사용한다. schema/security 선언 삭제에는 `entrypointPointer`를 사용한다. 같은 owner를 여러 논리 path가 공유하면 preview의 `affectedOperations`에 모두 나타난다. 공유 component나 참조 의존성이 불확실한 변경은 `impactScope: conservative_shared_source`로 표시하고 영향 operation을 넓게 열거한다.

`POST /api/projects/{reference}/openapi/editor`는 동일한 엔진으로 `action: preview` 또는 `apply`를 실행한다.

```json
{
  "action": "preview",
  "_storage": {"revision": 4},
  "sourceDigest": "GET에서 받은 64자리 SHA-256",
  "edits": [
    {
      "file": "paths/items.yaml",
      "op": "replace",
      "path": "#/get/responses/422",
      "value": {
        "description": "Invalid input",
        "content": {"application/problem+json": {"schema": {"type": "object"}}}
      }
    }
  ]
}
```

`add`는 이미 있는 대상에 덮어쓰지 않고, `replace`/`remove`는 실제 존재하는 대상만 허용한다. 컴포넌트 schema/security scheme을 추가할 때만 없는 `components`와 해당 맵을 만든다. 배열은 숫자 인덱스 또는 추가용 `-`를 쓴다. JSON Pointer의 `~0`/`~1`을 적용하며 잘못된 escape·배열 인덱스·파일 경로는 거부한다. 부분 실패가 나도 저장하지 않는다.

preview는 저장 없이 `valid`, 전체 문서 `issues`, `changedFiles`, `affectedOperations`, 변경 후 `source`, `nextSourceDigest`를 반환한다. 구조/참조 오류는 error로 저장을 차단하고 조직 lint warning은 보인다. apply는 같은 검사를 다시 수행한 뒤 **한 번의 revision 조건부 저장**을 한다. 실패한 전체 문서 검사는 HTTP 400과 동일한 구조화 진단을 반환한다. revision 누락·불일치 또는 원본 digest 변경은 409이므로 최신 GET 후 다시 preview해야 한다.

가져오기는 `edits` 대신 `source` 전체를 명시적으로 보낸다. YAML/JSON 파일은 `{kind:"bundle",entrypoint:"spec.yaml",rawFiles:{"spec.yaml":"…"}}` 형태로 가져올 수 있다. `files`도 보내면 `rawFiles`를 다시 파싱한 값과 같아야 한다. 전역 소스 교체도 먼저 preview하고 전체 OpenAPI 검증 후 apply한다. 기존 bundle에서 일부만 수정할 때는 변경한 파일만 다시 직렬화하며 나머지 파일의 byte는 그대로 유지한다. 3.1의 boolean schema와 schema `$ref` sibling, 확장 필드는 보존한다. 원격 `$ref`, 경로 탈출, 5 MB/200파일 상한 및 지원하지 않는 참조 범위는 자동 변환·외부 fetch 없이 거부한다.

[개발 진행 기록](api-development-progress.md)에 구현·검증 범위를 남긴다.
