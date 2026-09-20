# TST-1·TST-2·TST-3 사용 안내

## 명세와 케이스 연결

프로젝트의 **API 목록 및 API 작성 → 명세–케이스 커버리지**에서 operation·응답별 연결 수와 최근 성공 시각을 확인한다. `200` 같은 개별 응답, `2XX` 범위, `default` 순으로 가장 구체적인 응답에 연결한다. 케이스 연결은 실행 성공을 의미하지 않으므로 최근 성공 시각을 함께 확인한다.

OpenAPI에서 케이스를 만들면 `spec_source`에 operation ID, method/path/status와 명세 fingerprint가 저장된다. 기존 케이스는 method/path가 유일하게 일치할 때 연결을 추정한다. 경로 인자가 있는 요청도 연결한다. operationId가 있으면 경로 변경 후에도 연결을 유지한다. operationId가 없거나 중복되거나 변경된 경우 연결을 수동 검토해야 한다. 삭제되거나 모호한 operation의 케이스는 별도로 표시한다.

최근 성공 시각은 이번 기능 도입 이후 저장된 케이스 실행의 결과 metadata로 집계한다. 미저장 preview 실행은 제외한다. 기존 실행 이력에는 개별 케이스 결과가 없어 소급 집계하지 않는다. HTTP 원문, header, secret, 추출 변수는 이력에 저장하지 않는다. 실행 당시 성공 시각이며 현재 케이스 revision의 재검증을 뜻하지 않는다.

## 선택적 동기화

1. 케이스의 **변경 미리보기**를 연다.
2. 변경 가능한 필드를 선택한다.
3. **선택 필드 및 연결 기준 저장**을 누른다.

자동 갱신 범위는 `request.method`, `request.url`, `expected.status`다. 저장된 생성 기준과 현재 케이스 값이 같은 필드만 갱신한다. 사용자 assertion, body, header, 인증, 변수와 secret은 보존한다. URL에 인자나 query를 넣은 경우도 사용자 수정으로 취급해 보존한다. 요청/응답 schema 변경은 영향 케이스로 표시하고 body·assertion의 수정은 케이스 편집기에서 직접 수행한다. 공유 component 변경은 누락을 피하기 위해 모든 연결 operation에 보수적으로 영향 표시한다.

선택하지 않은 필드는 유지하고 현재 명세를 새 연결 기준으로 저장한다. 연결 기준이 없는 케이스는 첫 저장에서 기준만 등록한다. 오래된 preview로 저장하면 프로젝트/케이스 revision 충돌을 안내한다. Example은 조회만 가능하다.

## 실행별 데이터와 정리

파이프라인 편집기의 **실행별 테스트 데이터**에서 변수 이름과 UUID·UTC 시각·정수 범위를 선택한다. seed가 같으면 생성 결과를 재현할 수 있다. seed를 비우면 매 실행 새 값을 만든다. 고정 seed의 UTC 시각은 실제 현재 시각이 아닌 재현 가능한 2000~2100년 범위의 시각이다.

요청에서 `${run.id}`처럼 참조한다. 값 전체가 변수 참조이면 숫자·배열·객체 타입을 유지하며 문자열 일부의 참조는 문자열로 치환한다. 변수는 파이프라인 실행마다 별도로 생성한다.

단계 추가에서 준비·테스트·정리를 선택하고 응답 추출 변수 이름과 `body.id`, `body.items.0.id`, `status` 같은 경로를 지정할 수 있다. 추출한 값도 `${run.created_id}`로 사용한다. JSON 문서에서는 단계별 `extract`에 여러 변수를 선언할 수 있다.

```json
{
  "seed": "repeatable-test",
  "generators": {
    "id": {"type": "uuid"},
    "count": {"type": "integer", "min": 1, "max": 10}
  },
  "steps": [
    {"name": "create", "case": "items/create/ok.json", "phase": "setup", "extract": {"created_id": "body.id"}},
    {"name": "check", "case": "items/get/ok.json"},
    {"name": "cleanup", "case": "items/delete/ok.json", "phase": "teardown"}
  ]
}
```

일반 단계가 실패하면 남은 일반 단계는 중단하고 모든 정리 단계를 계속 실행한다. 정리 실패가 다른 정리 단계를 중단하지 않는다. 결과에 `phase`, `mainStatus`, `cleanupStatus`를 표시하며 전체 exit code는 정리 실패도 실패로 처리한다. 임의 shell/Python 코드를 실행하는 generator는 지원하지 않는다.

프로세스 강제 종료, 실행 취소 또는 전체 job timeout에서는 정리를 보장하지 않는다. 삭제 API는 재실행 가능한 방식으로 작성하고 필요한 운영 정리는 별도로 수행한다. 기존 외부 setup의 소유권·승인·재시도 제한은 유지한다.
