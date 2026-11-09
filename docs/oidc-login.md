# OIDC 로그인과 Workspace 세션

COL-1은 FastAPI가 OIDC Authorization Code + S256 PKCE를 처리하고 서버 DB에 Studio 세션을 저장하는 구성이다. Native local 모드는 loopback 전용 기존 사용법을 유지한다. 원격 모드에서는 로그인과 유효한 Workspace membership이 필요하다.

## 공급자와 서버 설정

1. 공급자에서 Code flow, S256 PKCE, RS256 ID token을 지원하는 client를 등록한다. callback은 `STUDIO_PUBLIC_URL/auth/callback`이며 프록시 헤더로 변경하지 않는다.
2. `.env.example`의 `STUDIO_PUBLIC_URL`을 외부 HTTPS origin으로, `STUDIO_OIDC_ISSUER`와 `STUDIO_OIDC_CLIENT_ID`를 등록값으로 지정한다. 인증 방식은 `STUDIO_OIDC_AUTH_METHOD`의 `client_secret_basic`, `client_secret_post`, `none` 중 공급자 등록에 맞춘다.
3. `STUDIO_OIDC_CLIENT_SECRET`과 안정적인 Fernet `STUDIO_SESSION_KEY`를 설정한다. 운영에서는 대응하는 `_FILE` secret mount를 사용할 수 있다. 세션 키를 재시작마다 생성하지 않는다. 키/인증 구성 변경은 기존 세션을 무효화한다.
4. issuer와 다른 token/JWKS origin은 `STUDIO_OIDC_ENDPOINT_ORIGINS`에 정확한 origin을 등록한다. 사설망 공급자는 별도로 `STUDIO_OIDC_PRIVATE_ORIGINS`에 등록하고 필요한 CA는 `STUDIO_OIDC_CA_FILE`에 지정한다. TLS 인증서 검증을 끄지 않는다.
5. 서버 운영자가 검증한 issuer/subject를 사용자와 Workspace에 연결한다. email이나 토큰 role claim으로 자동 가입·승격하지 않는다.

```sh
python -m api_test.identity_admin \
  --issuer https://identity.example.com \
  --subject registered-subject \
  --user-id engineer-1 --display-name Engineer \
  --workspace engineering --workspace-name Engineering --role owner
```

CLI에는 실제 서비스와 같은 DB 구성을 적용한다. 이미 연결된 issuer/subject를 다른 사용자에게 재할당할 수 없다. `STUDIO_OIDC_ALLOW_LOOPBACK_HTTP=true`는 `LOCAL_SERVER=true`와 함께 사용하는 명시적인 loopback 개발 설정이며 운영 HTTPS 대체 수단이 아니다.

## 세션과 권한

- HTTPS 쿠키는 `__Host-` prefix, Secure, HttpOnly, SameSite=Lax를 사용한다. 브라우저에는 공급자의 access/refresh/ID token을 보관하지 않는다. DB에는 opaque 세션 ID의 hash를 저장한다.
- ID token은 고정 RS256, 서명·issuer·audience·expiry·nonce·azp와 관련 claim을 검사한다. state는 브라우저 binding과 결합한 일회용 값이다. 공급자 통신은 redirect를 따르지 않고 검증한 DNS 주소에 연결한다.
- 기본 idle 만료는 1,800초, 최대 수명은 28,800초다. `STUDIO_SESSION_IDLE_SECONDS`, `STUDIO_SESSION_MAX_SECONDS`로 조정한다. 로그아웃은 Studio 세션을 폐기하며 공급자의 전역 SSO 로그아웃은 수행하지 않는다.
- 변경 요청은 일치하는 Origin과 세션 CSRF token을 요구한다. 데이터 요청의 `X-Studio-Workspace`는 서버 세션의 Workspace와 일치해야 한다. 헤더로 Workspace나 역할을 선택할 수 없다.
- Workspace 전환은 전체 페이지를 다시 불러온다. 이전 화면의 비동기 요청은 기존 Workspace 헤더를 유지하므로 전환 후 다른 Workspace에 쓰지 못한다. 실행 복원 키도 user/workspace로 구분한다.
- 역할과 활성 상태는 DB membership을 기준으로 확인한다. 현재 membership이 해제돼도 다른 유효 Workspace 선택과 로그아웃은 가능하다.

## 멤버와 감사 기록

Owner/Admin은 현재 Workspace 멤버와 감사 기록을 조회하고 기존 membership을 변경할 수 있다. Owner 변경은 Owner만 가능하며 마지막 활성 Owner를 제거할 수 없다. 변경 사유와 목록에서 받은 `revision`이 필요하다. 동시 변경은 409를 반환하고 목록을 다시 조회한다.

로그인·로그아웃·Workspace 선택·membership 변경과 서버 요청 문맥의 secret 접근 요청을 감사 기록에 남긴다. `secret.read_requested`는 복호화 전 접근 요청이며 복호화 성공을 뜻하지 않는다. secret의 scope/name은 기록하지만 평문·암호문·token은 기록하지 않는다. 서버 요청 문맥이 없는 오프라인 CLI는 이 secret 감사 범위에 포함되지 않는다.

SQLite→PostgreSQL 이전은 영구 감사 기록을 보존하지만 pending 로그인 state와 session은 이전하지 않는다. 이전 후 다시 로그인해야 한다. identity 전용 migration ledger를 사용하며 membership version은 v2에서 추가된다.

## 배포 경계

Compose는 API 포트를 host에 게시하지 않고 Nginx gateway만 기본 `127.0.0.1:5173`에 게시한다. 외부 운영 접근에는 HTTPS 종료 프록시와 정확한 public origin 설정이 필요하다. gateway는 `/api/`, `/auth/`를 같은 origin으로 연결한다. callback query가 access log에 남지 않도록 서버 필터와 gateway 설정을 적용했다.

## 검증 상태

2026-10-13: Python 전체 419개, 프런트엔드 56개와 production build를 통과했다. 테스트용 공급자 및 Uvicorn의 실제 HTTPS에서 인증서 검증을 유지한 로그인·PKCE·CSRF·Workspace 전환·이전 Workspace 요청 거부·claim 권한 무시·로그아웃·state 재사용 거부·로그 마스킹을 확인했다. SQLite/PostgreSQL 회귀와 migration 검증을 포함한다.

실제 운영 공급자 연동, 브라우저 SSO 화면, 외부 HTTPS 배포와 다른 기능 worktree 통합은 미완료다. 실제 HTTPS API 검증을 브라우저 검증으로 취급하지 않는다. 사용자 허용 후 브라우저 도구가 사이트 접근을 다시 거절하여 GOV-1 화면 검증도 대기 중이다. 상세 결과는 [검증 JSON](oidc-login-validation.json)에 기록한다.

후속 통신 검증: TLS handshake에도 남은 deadline을 적용하고 연결을 중단 타이머에 등록한다. CA 준비 실패 시 소켓을 닫으며 중단된 연결의 자동 재접속을 금지한다. DNS 조회 자체의 시간은 native resolver를 따르므로 요청 전체의 절대 8초 제한을 보장하는 것은 아니다. 관련16개 테스트와 실제 HTTPS 로그인 fixture를 최종 코드에서 재실행해 통과했다.

## 2026-11-06 로컬 HTTPS 브라우저 검증

릴리스 검증 범위를 사용자 요청에 따라 루프백 환경으로 정했다. Uvicorn이 Studio의 배포용 React 빌드를 HTTPS로 제공하고, 별도 HTTPS origin에서 임시 OIDC 공급자가 discovery·JWKS·서명된 ID token 발급을 수행했다. 인증 코드는 한 번만 사용할 수 있고 공급자가 S256 challenge를 확인했다. 브라우저는 폐기 가능한 전용 Chrome 프로필에서 테스트 서버 인증서만 신뢰했다. Studio는 임시 CA로 공급자의 TLS를 검증했다.

| Chrome 156에서 확인한 항목 | 결과 |
| --- | --- |
| 로그인과 세션 | SSO 버튼에서 공급자 화면과 callback을 거쳐 프로젝트 목록 표시. Secure·HttpOnly 세션 쿠키 확인 |
| 팀 A 소유자 → 팀 B 조회자 | 실제 Workspace 선택기로 전환. 각 목록과 상세에서 자기 팀 프로젝트만 조회 가능 |
| 문서 격리 | 양쪽 모두 자기 문서 200, 상대 문서와 존재하지 않는 문서는 같은 400. 이전 Workspace 헤더 403 |
| 역할 제한과 로그아웃 | 조회자의 문서 저장 403, UI 로그아웃 후 세션 쿠키 제거 및 비공개 목록 401 |

최초 테스트 인증서의 Authority Key Identifier 누락을 고쳐 Python의 엄격한 TLS 검증을 통과했다. Firefox 기동 문제 이후 별도 Chrome 프로필로 확인했다. 검증 범위는 합성 계정·격리 DB를 사용한 로컬 배포다.

### Mac Compose의 공개 회원가입 (Dex 2.44)

로그인 전 **회원가입**에서 이메일과 비밀번호를 등록한 후 **SSO 로그인**을 선택한다. 이 배포에서는 이메일을 로그인 이름으로 사용하며 메일 소유권 확인 절차는 없다. 첫 로그인 시 가입 서비스가 발급한 Dex 로컬 계정에 개인 Workspace와 그 Workspace의 owner 권한을 생성한다. 다른 Workspace에 참가하려면 별도 membership이 필요하다. 기존 계정의 암호와 권한은 가입 요청으로 수정할 수 없다.

이 기능은 기본적으로 비활성이다. 같은 Mac 배포 구성을 복원할 때는 다음을 함께 적용한다.

- Dex는 영구 SQLite 볼륨과 password DB를 사용한다. gRPC 주소를 `127.0.0.1:5557`로 설정한다.
- Compose에서 `deploy/dex-signup`을 빌드한 서비스에 `network_mode: service:dex`와 Studio의 HTTPS `STUDIO_PUBLIC_URL`을 설정한다. 이 서비스의 HTTP 포트 5559와 Dex 관리 포트 5557은 호스트에 게시하지 않는다.
- Studio용 HTTPS 게이트웨이에서 `location = /auth/signup`만 `http://dex:5559`로 전달한다. 요청 본문은 4 KiB, IP별 요청은 분당 6회와 burst 5로 제한하고, Cookie와 Authorization 헤더는 제거한다. 기존 `/auth/login`과 콜백은 Studio API로 전달한다.
- Studio API 환경에 `STUDIO_DEX_SELF_SIGNUP=true`를 설정한다. 이 플래그는 로그인 화면의 가입 버튼과 검증된 Dex 신규 가입 subject의 최초 Workspace 생성을 활성화한다. 가입 서비스는 입력된 비밀번호를 bcrypt 해시로 변환한 뒤 Dex CreatePassword RPC만 호출한다.
