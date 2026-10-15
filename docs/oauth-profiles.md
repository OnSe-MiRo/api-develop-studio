# OAuth 2.0 인증 프로필

프로젝트의 `auth_profiles` 또는 환경의 `auth_profiles`에 이름을 붙인 `OAuth 2.0` 프로필을 저장한다. 같은 이름의 환경 프로필은 해당 환경에서 프로젝트 프로필을 덮어쓴다. 환경을 API에 명시하지 않으면 프로젝트 공통 프로필을 조회한다. 실제 빠른 호출·케이스·파이프라인·CLI 실행은 선택한 환경(설정된 기본 환경 포함)의 유효 프로필을 사용한다. 파이프라인은 각 케이스의 `auth_profile` 참조를 실행하며 별도의 파이프라인 프로필 필드를 만들지 않는다.

```json
{
  "type": "OAuth 2.0",
  "grantType": "client_credentials",
  "clientId": "studio-client",
  "clientSecret": "{{project.OAUTH_CLIENT_SECRET}}",
  "tokenUrl": "https://issuer.example.test/token",
  "clientAuthMethod": "basic",
  "scopes": ["read"]
}
```

`grantType`은 `client_credentials` 또는 `authorization_code`, `clientAuthMethod`는 `basic`, `post`, `none`이다. `none`은 공개 authorization-code 클라이언트에만 사용하고 `clientSecret` 필드를 넣지 않는다. 그 외 방법의 `clientSecret`은 반드시 프로젝트/환경에 암호화 저장된 `{{project.NAME}}` 참조여야 한다. authorization-code 프로필에는 `authorizationUrl`도 필요하다. `scopes`는 공백 없는 고유 문자열 배열이며, 구성에 따라 `issuer`를 설정하면 callback 응답의 `iss`를 확인한다. 서버는 임시 access/refresh token이나 code/verifier를 프로필 JSON·projection·revision에 저장하지 않는다.

인증 관리 API는 다음과 같다.

| 방법 | 경로 | 동작 |
| --- | --- | --- |
| GET | `/api/projects/{reference}/oauth/profiles/{profile}?environment=dev` | `configured`, `connected`, `grantType`, `expiresAt`, `canRefresh`, `callbackUri`만 반환 |
| POST | 위 경로의 `/token` | `{ "environment":"dev", "action":"issue" }` 또는 `refresh`; token 값은 반환하지 않음 |
| POST | 위 경로의 `/authorize` | `{ "environment":"dev" }`; `authorizationUrl`·`callbackUri` 반환 및 HttpOnly SameSite=Lax 상태 cookie 설정 |
| GET | `/api/oauth/callback/{providerKey}` | state/cookie/UA/프로필·issuer·S256 PKCE 확인과 code 교환 후 query 정보 없이 프로젝트 설정으로 303 |
| DELETE | 프로필 GET 경로 | 해당 환경의 **로컬** token 및 pending state 삭제; provider revocation은 하지 않음 |

프로젝트 설정 화면에서 callback URI를 먼저 확인해 provider에 **정확히 등록**한다. 운영에서는 `STUDIO_OAUTH_CALLBACK_ORIGIN`에 신뢰할 수 있는 HTTPS origin을 설정한다. TLS를 종료하는 역방향 proxy는 공개 origin의 `Host` authority를 백엔드까지 그대로 전달해야 한다. 백엔드 연결의 `http` scheme 자체는 허용하지만 임의의 `Forwarded`/`X-Forwarded-Proto` 요청 헤더는 callback origin 판단에 신뢰하지 않는다. 로컬 `LOCAL_SERVER=true`만 loopback Host와 HTTP fake provider를 허용한다. 시작 요청은 provider가 이미 쓴 `state`, `code_challenge`, `redirect_uri` 등의 예약 query 키를 거부한다. callback은 별도 provider-key 경로와 5분 단일 사용 state·cookie binding을 사용하며, 성공 시 `/projects/settings?project=<slug>`로 code/state가 없는 303을 보낸다. Uvicorn callback access log에서는 query를 지운다. reverse proxy access log도 동일하게 query를 제거하도록 운영에서 설정해야 한다.

token endpoint는 DNS를 검사해 공개 IP에만 연결하고, 직접 고정 주소로 연결하면서 원래 hostname의 TLS 인증서를 확인한다. redirect를 따르지 않으며 연결·응답 교환의 8초 총 상한과 64 KiB 제한, provider 오류 원문 비노출 규칙을 적용한다. 운영체제 DNS 조회 자체의 timeout은 별도 OS 설정에 따른다. 로컬 fake provider의 loopback HTTP만 예외다. 발급 token은 암호화된 Studio migration v6의 임시 테이블에 저장한다. workspace/user/project/environment/profile 및 설정·secret 지문으로 구분하고, 다른 프로세스의 refresh는 트랜잭션 lease로 직렬화한다. 결과가 불확실한 만료 refresh lease는 이전 회전 token을 재사용하지 않고 재연결을 요구한다. 수동 동시 refresh는 한 건만 수행하고 나머지는 409로 거부한다. access `expires_in`이 없으면 `expiresAt:null`이며 1시간 사용 상한 뒤 갱신/재발급한다. refresh token은 별도 최대 7일 보존하고 다음 작업에서 만료 행을 정리한다.

발급된 Bearer token은 저장된 프로젝트/환경 API의 **정확한 origin**으로 향하는 요청의 Authorization header에만 넣는다. OAuth resource 요청은 프로젝트의 TLS 검증 해제 설정이나 로컬 소유권 생략과 관계없이 인증서 검증 및 redirect 차단을 강제한다. 저장된 HTTPS proxy 설정은 기존 동작을 유지하되 loopback HTTP OAuth 요청의 proxy는 명시적으로 거부한다. 401에서 provider token을 자동 재시도하지 않는다. 케이스 변수는 client secret 참조를 바꾸지 못하며, token·code/verifier·password는 API 응답·CLI 로그·실행 보고서/이력에 넣지 않는다.

프로토콜 경계는 [OAuth 2.0 RFC 6749](https://www.rfc-editor.org/rfc/rfc6749), [PKCE RFC 7636](https://www.rfc-editor.org/rfc/rfc7636), [OAuth 2.0 Security BCP RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)을 따른다. 이번 검증은 합성 credential과 제어한 로컬 가짜 provider를 사용한다. 실제 외부 provider 등록·운영 secret·배포 프록시는 별도 운영 검증 대상이다.
