# 빠른 호출, 환경과 인증 프로필

프로젝트 설정의 **환경 프로필 JSON**에 환경별 `base_url`, `variables`와 선택적인 `auth_profiles`를 입력한다. 기본 환경 이름을 비우면 기존 `base_url`을 사용한다. 환경이 없는 기존 프로젝트는 그대로 실행된다.

```json
{
  "local": {"base_url": "http://127.0.0.1:8080", "variables": {"plain": {"tenant": "local"}, "secret": {}}},
  "dev": {"base_url": "https://dev.example.com", "variables": {"plain": {"tenant": "dev"}, "secret": {}}},
  "stage": {"base_url": "https://stage.example.com", "variables": {"plain": {"tenant": "stage"}, "secret": {}}}
}
```

- 빠른 호출·케이스 편집·파이프라인 편집에서 실행 환경을 선택한다. 선택값을 케이스에 저장하지 않는다.
- CLI는 `python3 run_api_tests.py --case tag/api/case.json --environment dev`처럼 실행한다. 파이프라인에도 같은 옵션을 사용한다.
- 일반/암호화 변수는 공통 → 환경 → 케이스 순서로 적용한다. 케이스 변수는 같은 이름의 `{{project.NAME}}` 참조에도 우선 적용되며 기존 `{{case.NAME}}` 암호화 참조도 유지한다.
- 환경을 선택하면 환경의 Base URL이 기존 케이스 `base_url_name`보다 우선한다. 절대 요청 URL은 그대로 유지되므로 환경 주소를 바꾸려면 `/users` 같은 상대 URL을 사용한다.
- 새로운 환경의 대상 주소도 소유권 검증이 필요하다. 환경 주소를 변경하면 기존 검증 상태가 취소된다.

## 인증

프로젝트 공통 보안 변수에 자격 증명을 먼저 등록한다. **공통 인증 프로필 JSON**에 아래와 같이 입력하고 빠른 호출 또는 케이스에서 이름을 선택한다. 파이프라인은 각 케이스의 인증 참조를 사용한다.

```json
{
  "none": {"type": "No Auth"},
  "login": {"type": "Bearer Token", "token": "{{project.token}}"},
  "key": {"type": "API Key", "key": "X-API-Key", "value": "{{project.api_key}}"},
  "query": {"type": "API Key", "key": "api_key", "value": "{{project.api_key}}", "addTo": "Query Params"},
  "basic": {"type": "Basic Auth", "username": "user", "password": "{{project.password}}"}
}
```

실제로 사용하는 항목만 등록한다. `token`, `api_key`, `password`는 각각 암호화 변수로 존재해야 한다. 환경의 `auth_profiles`로 같은 이름을 덮어쓸 수 있다. 프로필의 token·password·value에 평문을 입력하면 저장을 거부한다.

환경의 보안 변수는 `"secret": {"token": {"value": "새 값"}}` 형태로 제출한다. 저장 시 기존 암호화 서비스를 사용하며, 조회에는 `{"configured": true}`만 반환한다. 화면에서 configured 항목을 그대로 두면 기존 암호문을 보존하고, API로 보존할 때는 `{"preserve": true}`를 전송한다. 암호화 서비스 또는 키가 준비되어 있어야 한다.

## 빠른 호출

JSON·Text·Form Data 본문과 상대 URL·프로젝트 변수·인증 프로필을 지원한다. Form Data는 `[{"key":"name","value":"Ada"}]` 형태이며, 파일은 기존 `case/` 아래 첨부 파일 경로를 `file`로 지정한다.

응답의 상태·헤더·본문·시간과 UTF-8 본문 크기를 표시한다. 사용한 자격 증명이 응답에 포함되어 돌아오면 마스킹한다. cURL 복사는 민감 필드를 마스킹하며 텍스트 본문은 생략한다. 변수와 프로필 인증은 복사한 명령에서 직접 설정해야 한다.

**현재 요청을 새 케이스로 저장**은 `tag/api_name/case_file.json` 경로를 사용한다. 환경 선택은 저장하지 않으며 현재 요청 모델을 그대로 저장한다. 직접 입력한 인증을 저장하려면 먼저 공통 인증 프로필로 전환한다.

**응답 대기 취소**는 브라우저의 대기를 중단하고 재실행을 허용한다. 이미 시작한 서버 측 HTTP 전송을 강제 종료하지는 않는다. OAuth 2.0 토큰 발급 흐름은 API-3의 2차 범위로 남아 있다.
