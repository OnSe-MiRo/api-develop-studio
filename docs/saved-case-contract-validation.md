# 저장 케이스 OpenAPI 응답 계약 검증

## 켜기와 저장 형식

케이스 편집기의 **OpenAPI 응답 계약 → 저장된 프로젝트 명세로 응답 검증**을 켜고 저장한다. 선택적으로 계약 server 변수(JSON)와 문서 기준 URL을 지정할 수 있다. 설정은 케이스 JSON에 저장되므로 인증정보를 넣지 않는다. 끄고 저장하면 설정이 제거된다. 기존 케이스와 설정이 없는 케이스는 이전 실행 판정을 유지한다.

```json
{
  "project": "demo.json",
  "request": {"method": "GET", "url": "/service/v2/items"},
  "expected": {"status": 200},
  "contract_validation": {
    "enabled": true,
    "server_variables": {"version": "v2"},
    "document_url": "https://docs.example/service/spec/openapi.json"
  }
}
```

`enabled`는 필수 boolean이다. 추가 설정키를 허용하지 않는다. server_variables는 최대32개 문자열 map(키1~128자·값512자), document_url은 사용자정보/query/fragment 없는2048자 이하 HTTP(S) 문서 위치다. 빠른 호출의 server 매칭과 같은 규칙을 사용하며 요청 URL은 자동 변경하지 않는다.

## 실행 계약

- CLI의 직접 케이스·파이프라인 및 웹의 실제 자식 runner에서 공통 ApiTestRunner 경로로 적용된다. 웹 편집기의 실행 버튼은 기존대로 임시 inlineCase를 실행한다. 파이프라인은 저장된 케이스의 설정을 읽는다.
- 각 케이스를 시작할 때 해당 project root 안의 실행용 프로젝트 JSON에서 저장 OpenAPI 문서/bundle을 읽어 snapshot으로 고정한다. 같은 케이스의 재시도는 같은 snapshot을 사용한다. pipeline 전체의 원자 snapshot이나 DB revision pin을 구현한 것은 아니다. 원래의 DB→JSON 투영 계약을 따른다.
- enabled 케이스에는 project와 저장 명세가 필요하다. URL만 있는 명세는 다운로드하지 않고 configuration_error로 거부한다. 설정·명세 lint·operation 매칭 오류는 대상 HTTP 호출 전에 중단한다. Workspace별 project root와 경로 경계를 유지한다.
- 원래의 expected status/body/assertion/시간 제한을 그대로 검사하고 OpenAPI status/content type/header/body 검증을 추가한다. 어느 하나라도 실패하면 failed다. 계약 실패는 기존 retry 정책을 따른다. 원격 호출 소유권·인증·proxy/timeout 동작은 변경하지 않는다.
- 계약 불일치는 규칙 코드만 포함한 `$.contract` Difference를 남긴다. JSON/JUnit 판정에는 `contract_failed`를 사용한다. 기존 assertion도 함께 실패할 수 있으며 원래 Difference는 보존한다.
- JSON report와 실행 이력의 optional contract에는 valid·issueCount·documentDigest만 기록한다. 진단 원문/본문/token/변수값은 이 필드에 저장하지 않는다. digest는 실제 검사한 명세 snapshot을 식별하며 이력이 원본 명세를 보관한다는 뜻이 아니다. 기존 UI의 요청/응답 표시 및 마스킹 정책은 유지한다.

## 검증 근거

- 집중6개: opt-in/opt-out·기존 status 검사 병행, 설정/명세/operation 오류의 대상 호출0회, 재시도 중 원본 변경에도 snapshot 유지, server 변수·상대 문서 기준 결합, project root 경계, URL-only/malformed 프로젝트 실패, JSON/JUnit/이력 값 비노출, 실제 CLI와 pipeline의 contract_failed 종료, API 설정 왕복과 동명 프로젝트 Workspace별 판정.
- 최종 전체 Python597개(skip0,194.581초) 및 frontend138개(worker2), production build 통과. 새 편집기 테스트는 설정 load/save/disable 및 기존 expected/storage revision 보존을 포함한다.
- 브라우저의 격리 로컬 fixture와 실제 Python 자식 runner에서 opt-out의 잘못된 body+HTTP200은 이전대로 통과했다. opt-in 저장·reload 후 동일 응답은 schema_type/contract_failed, 같은 저장 케이스를 쓰는 pipeline도 실패했다. 케이스 URL을 정상 fixture로 바꿔 저장 후 pipeline은 통과했다.
- 실제 HTTP job 결과의 실패/통과 두 targets를 확인했다. 계약 결과는 각각 valid false/true, issueCount1/0, 같은 documentDigest였고 원문 테스트 값은 JSON 결과에 없었다. [성공 화면](saved-case-contract-result.jpg). 콘솔 오류/경고0개.
- 브라우저에서 저장 안내는 기존 명세 목록 재조회 안내로 바뀌어 텍스트 대기가 끝났지만, 새로고침의 설정/URL 보존과 실제 pipeline 결과로 저장을 확인했다. 최초 테스트 명세 fixture 구문 오류는 기존 검증된 spec helper를 사용해 해결했다.
- 로그: /tmp/saved-contract-focused-python.log, /tmp/saved-contract-python-verified.log, /tmp/saved-contract-web-all.log, /tmp/saved-contract-build.log, /tmp/saved-contract-generated-check.log.

서버 변수/상대 URL 변경은 커밋0de1fca·develop 병합a51c176이다. 이 기능은 feature/saved-case-contract-validation의 미커밋 변경이며 원격 푸시는 하지 않았다. 운영 공급자·배포·전체 부하 캠페인 및 기존 부하 실패/unknown은 이번 기능 검증과 별개다.
