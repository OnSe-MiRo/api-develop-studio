# 도구 가져오기·내보내기 (IOP-1)

프로젝트의 **API 케이스 → 가져오기·내보내기**에서 원본을 붙여넣거나 파일을 선택하고, 미리보기를 확인한 뒤 **이 항목 저장**을 누른다. 이 과정에서는 대상 API 호출, cURL 명령, Postman script를 실행하지 않는다. 원본 입력은 요청 처리 중에만 사용하고 저장소에는 정제한 요청만 저장한다.

## 지원 범위

| 입력 | 지원 | 명시적으로 제외 |
| --- | --- | --- |
| cURL | HTTP(S) URL 1개, `-X/--request`, `-H/--header`, `-d/--data/--data-raw/--data-binary`의 직접 문자열, `-G/--get`, `-I/--head`, `--url`, `--form-string`, 긴 옵션 `=값` 및 `-XPOST` 등의 짧은 옵션 | 셸 연결·리다이렉션, config, 파일 읽기·첨부, 여러 URL, 알 수 없는 옵션 |
| Postman | Collection v2.0/v2.1 폴더(최대 깊이16), raw URL, enabled query/header, JSON·urlencoded·문자열 formdata | script/event 실행, 인증 이관, 동적 변수, 별도 path variable, 파일·GraphQL body |
| Environment | enabled 문자열 변수, `{{name}}` → `{{project.name}}`, 기존 named environment에 plain 변수 병합 | secret 타입·민감 이름 변수 이관, 기본 환경 자동 선택 |
| HAR | `log.entries[].request`의 method/URL/header/postData, form-urlencoded·파일 없는 multipart | 응답·쿠키 이관, 첨부파일·인코딩된 본문 |

입력 원문은 UTF-8 기준 1 MiB, 요청은 한 번에100개, Environment 변수는500개까지 지원한다. HTTP JSON 포장은 8 MiB에서 중단한다. 지원하지 않는 의미를 조용히 버리지 않고 오류로 표시하되, 민감값·script·응답 등 의도적으로 제외하는 항목은 미리보기에 경고한다.

## 저장과 충돌

케이스는 `case/{tag}/{요청이름-프로젝트지문-순번}/{형식}.json`에 저장한다. tag 기본값은 `imported`이고 새 가져오기 묶음에는 다른 태그를 사용할 수 있다. 프로젝트 지문은 다른 프로젝트 간 경로 충돌을 줄인다. 파일 참조는 `/` 구분자를 사용한다.

- 미리보기는 저장하지 않는다. 새 케이스의 예상 HTTP 상태는 **200**으로 시작하며 사용자가 실제 계약에 맞게 편집한다. HAR response를 검증값으로 복사하지 않는다.
- 정제한 문서·프로젝트 revision·대상 케이스 revision에 묶인 digest를 저장 시 재계산한다. 달라지면409로 중단한다. DB 저장에도 expected revision을 전달한다.
- 같은 프로젝트의 기존 케이스는 **기존 항목 덮어쓰기 확인** 후 교체한다. 요청뿐 아니라 해당 케이스의 expected 설정도 가져온 문서로 교체되므로 미리보기를 확인한다. 다른 프로젝트의 케이스와 충돌하면 덮어쓸 수 없다.
- 항목별 저장이며 일괄 transaction이 아니다. 저장 후 나머지는 새 미리보기로 다시 확인한다.
- Environment는 이름을 안전한 slug로 바꾸고 기존 환경에 plain 변수를 병합한다. 기존 base URL·secret·default_environment는 유지하고, 새 환경의 base URL은 프로젝트 기본값을 사용한다. 기존 secret과 같은 이름의 plain 변수가 들어오면 차단한다.

## 민감값과 cURL 출력

Authorization/Cookie 및 token/secret/password/API key/credential 계열 이름을 검사한다. URL userinfo는 제거하고 민감 query와 JSON/form 값은 `[REDACTED]`로 바꾼다. 구조를 확인할 수 없는 본문은 비우고 경고한다. 이 처리는 이름 기반 후보 필터이며 임의의 개인 정보나 의미상 비밀을 모두 식별하는 기능은 아니다. 미리보기와 출력은 사용자가 검토해야 한다.

cURL 출력은 POSIX shell 인용 규칙을 사용하며 `--disable`로 사용자 curl config 읽기를 막고 `--globoff`로 URL glob을 끈다. 출력 자체는 실행하지 않는다. JSON 및 문자열 form 전송을 지원하고 파일·auth 프로필·secret 값은 해석하지 않는다. 변수가 남은 요청은 안전한 값으로 대체한 다음 내보내도록 오류를 표시한다. 상대 URL은 기본 환경 또는 케이스의 named Base URL에 맞춰 구성한다. 프로젝트 proxy·TLS 등의 전송 설정을 복제하는 기능은 아니다. Windows에서는 POSIX shell(예: Git Bash)을 사용하며 PowerShell/cmd 명령 변환은 지원하지 않는다.

API는 `POST /api/interoperability/preview`, `/apply`, `/curl`이다. canonical 계약은 `openapi/paths/interoperability.yaml`에 있다. 형식별 fixture, 실제 로컬 echo round trip, 저장 충돌·secret 보존 테스트는 `tests/test_interoperability.py`에 있다.
