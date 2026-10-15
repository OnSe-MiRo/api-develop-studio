# Workspace 요청·실행 격리 (COL-2)

HTTP 요청에서 확인한 사용자·Workspace 문맥을 저장소, thread pool, 공통 job worker, 테스트 runner 자식 프로세스까지 전달한다. 원본 문서와 revision의 권한 판정은 기존 `users`, `workspaces`, `memberships`의 active 상태와 role을 기준으로 한다. FND-4에 이미 존재하는 schema를 사용하며 새 migration 번호를 소비하지 않는다.

## 인증 경계

- `STUDIO_AUTH_MODE=local`이 native 실행의 기본값이다. loopback bind와 loopback Host만 허용하고 `default`/`local-user`를 사용한다. `LOCAL_SERVER`는 기존 소유권 확인 정책이며 인증 모드와 별개다.
- `STUDIO_AUTH_MODE=remote`에서는 인증 공급자가 없으면 데이터 API가401로 실패한다. Docker Compose는 remote를 명시한다. `/health`는 개인정보 없는 프로세스 상태 응답이며 데이터 API 접근 권한을 주지 않는다.
- 인증 어댑터는 `create_app(studio, current_user_provider=...)`로 설치하고 검증된 `CurrentUser(user_id, workspace_id)`를 반환한다. sync/async 어댑터를 지원한다. **CurrentUser 생성 자체는 인증이 아니다.** 어댑터는 OIDC/session 또는 내부 서명 token/mTLS를 검증한 이후에만 이 객체를 만들어야 한다.
- role은 어댑터에서 받지 않고 요청마다 DB에서 확인한다. `X-Studio-Actor`, body의 `user_id`/`workspace_id`로 주체를 바꿀 수 없다. 선택적 `X-Studio-Workspace`는 인증 문맥과 일치해야 하며 다른 Workspace 선택 수단이 아니다.
- provider subject → 내부 user ID 연결, 로그인·Workspace 선택 UI, 계정/멤버십 관리, CSRF 및 실제 내부 서비스 인증은 COL-1에서 연결한다. 이 브랜치만 배포한 remote/Docker 데이터 API는 인증 어댑터가 설치되기 전까지401이며 이를 익명 local-user로 우회하지 않는다.

## 권한

| 동작 | Owner | Admin | Editor | Runner | Viewer |
| --- | --- | --- | --- | --- | --- |
| 문서·revision·결과 조회 | 허용 | 허용 | 허용 | 허용 | 허용 |
| 문서·첨부·Mock 설정 저장 | 허용 | 허용 | 허용 | 거부 | 거부 |
| quick call·기능 테스트·SDK 생성·자기 job 취소·Mock 실행 | 허용 | 허용 | 허용 | 허용 | 거부 |
| 부하 결과 bundle 가져오기 | 허용 | 허용 | 허용 | 거부 | 거부 |
| 소유권 issue/verify 및 외부 승인 변경 | 허용 | 허용 | 거부 | 거부 | 거부 |

기존 소유권 검증과 운영자 승인 키 조건은 별도로 유지한다. 같은 Workspace라도 다른 사용자의 process-local job 조회·취소는404이며, 완료된 저장 실행 이력은 Workspace 구성원의 조회 권한으로 접근한다. active 상태를 확인할 수 없으면 접근하지 않는다. 대기 작업은 시작할 때 권한을 다시 확인하고, 비로컬 runner는 HTTP 실행 전에도 membership/role을 확인한다.

## 데이터·파일·실행

- 저장소 인스턴스의 context는 불변이며 요청 중 공유 singleton의 사용자나 Workspace를 바꾸지 않는다. ContextVar는 실행 후 복원하고 job 접수 시 복사한다.
- document/revision/audit, 기능 실행 이력, 부하 결과의 조회·저장에 Workspace 조건을 적용한다. SQLite에도 membership을 검사하며 PostgreSQL과 동일한 역할 경계를 유지한다. revision/audit 저장은 기존 transaction 안에서 이루어진다.
- 기본 Workspace의 기존 파일 위치는 유지한다. 다른 Workspace는 각 projection root의 `_workspaces/{workspace_id}/` 아래에 저장하고 내부의 `case/{tag}/{api_name}/{case_file}.json` 참조 구조와 `/` 구분자를 유지한다. HTTP 응답의 파일 참조에는 물리적 `_workspaces` 경로를 노출하지 않는다.
- `_workspaces`를 직접 참조하거나 symlink로 기본 root에서 다른 Workspace 파일에 도달하는 경로를 차단한다. 초기 local 파일 import와 기본 pipeline 검색도 예약 영역을 제외한다.
- runner에 `--case-root`, `--project-root`, `--file-root`를 명시하고 인증 문맥은 서버가 구성한 child environment로 전달한다. CLI의 암묵적 전체 pipeline 검색으로 다른 Workspace를 실행하지 않는다. 동기 실행의 임시 report/log와 비동기 job artifact는 종료 후 정리한다.
- 프로젝트 변수와 인증 프로필은 해당 Workspace의 파일/문서에서만 해석한다. UI에는 기존 configured/redacted 계약을 유지한다. OAuth vault와 SDK artifact의 별도 기능 worktree는 통합 시 동일 문맥 계약으로 추가 회귀해야 한다.
- Mock 관리 registry는 `(workspace, project)`로 분리한다. A의 stop/reset/config가 동명 B를 변경하지 않는다. 실제 mock HTTP listener는 기존 loopback 개발 서버이므로 OS/네트워크 수준에서 다른 사용자를 격리하는 호스팅 제품으로 간주하지 않는다.

## 검증과 후속 통합

`tests/test_workspace_isolation.py`는 두 Workspace의 동명 문서·revision·secret, 역할 행렬, actor/header 위조, concurrent quick calls, job 소유권, queue 중 membership 취소, 첨부·symlink, 부하 결과, 실제 Mock lifecycle, 실제 Python child/echo 서버·실행 이력을 검증한다. `tests/test_postgres_storage.py`는 별도 임시 PostgreSQL DB에서 HTTP 격리·역할 변경·membership 취소를 검증한다.

인증 provider fixture는 테스트 전용이며 production에는 헤더를 신뢰하는 테스트 어댑터를 설치하지 않는다. 기존 API-3 OAuth, RUN-2 SDK, IOP-1 미커밋 worktree와는 별도 develop 기반 브랜치다. 통합 시 동일 파일 충돌을 조정하고 OAuth callback·refresh/runner vault, SDK 다운로드 owner와 job context, IOP 저장 경로를 재검증해야 한다. 실제 SSO·브라우저 로그인, secret 사용/권한 변경 감사 이벤트, 외부 포트 차단 종단 검증은 COL-1 완료 조건으로 남아 있다.
