# API 부하테스트 및 대시보드 개발 진행 기록

## 프로젝트 목록 로컬 develop 병합 완료 (2026-10-15)

- 프로젝트 목록 커밋 `8939e2ef580913116fad4cc8ff385872f3b77bde`를 로컬 develop에 충돌 없이 병합했다. 이 기록은 병합 커밋에 포함한다. 검증한 제품 코드와 병합 결과는 동일하며 완료 문서만 추가했다.
- 원격 푸시·기존 원본 worktree 수정·브랜치 삭제 없음. 다음 API 케이스 목록 개발은 이 병합 이후 새 기능 브랜치에서 진행한다.

## 프로젝트 목록 커밋·develop 병합 준비 (2026-10-15)

- 사용자 승인으로 프로젝트 목록 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 제외한다.
- 현재 HEAD/develop `407983a`, 원격 develop `fb75a46` 확인. 변경 내용·diff 검사·기존 전체 Python560개/build/생성 검사 로그를 확인했으며 커밋 직전 프로젝트 집중5개와 frontend 전체117개를 재실행해 통과했다.
- 이어서 API 케이스 목록의 페이지·검색·태그·정렬을 새 feature 브랜치에서 개발한다. 새 단계 변경은 미커밋 상태로 남긴다.

## 프로젝트 목록 조회 개선 관련 기록 (2026-10-15)

- 프로젝트 화면의 DB keyset 페이지·이름/파일명 검색·정렬을 `feature/project-list-pagination`에서 구현·검증했다. [개발 기록](api-development-progress.md)과 [상세 계약](project-list-pagination.md)을 참조한다. 기존 부하 수치·실패/unknown은 변경하지 않았으며 이번 작업에서 부하 캠페인은 실행하지 않았다. 커밋·푸시 없음.

## 통합 커밋·로컬 develop 병합 완료 (2026-10-15)

- 사용자 승인으로 통합 커밋 `2c54a41b406bf90c6a9da039011ca3cc79148a3d`를 만들고 로컬 `develop`에 `--no-ff` 병합했다. 이 완료 기록은 병합 커밋에 포함한다. 원격 푸시는 수행하지 않았다.
- 검증: 커밋 전 Python 554개(skip 0, 137.740초), OAuth 집중5개·frontend111개·production build·생성 최신성·diff 검사 통과. 병합은 충돌 없고 검증한 통합 커밋과 제품 코드/테스트가 동일하며 완료 기록 문서만 추가했다.
- 보존: 작업 시작 당시 원본521개 파일 SHA와 대조해 변경0개를 확인했다. 통합 기능 브랜치와 원본 worktree는 모두 보존했다.
- checkout: 통합은 기존 roadmap-integration 경로, 로컬 develop은 `/tmp/api-studio-develop-20261015`이다. 기존 원본 저장소의 미커밋 변경은 그대로 유지했다.
- 범위: 이 기록은 로컬 Git 반영이다. 운영 인증/배포·전체 LT 캠페인·공통 pagination 등 잔여 개발 및 2026-10-13 브라우저 검증 범위를 변경하지 않는다.

## 통합 커밋 전 검증 완료 (2026-10-15)

- 전체 Python 554개(skip 0, 137.74초), OAuth 집중 5개, frontend 전체 111개, production build, OpenAPI 생성 최신성 및 diff 검사 통과.
- 실패/보완: 최초 frontend 110개 통과·1개 실패는 OAuth 초기 조회 중 비활성 연결 버튼을 클릭한 테스트 경합이었다. `OAuthProfileStatus.test.jsx`에서 버튼 활성화를 기다린 뒤 클릭하도록 보완했다. 관련 및 전체 재검증 통과, runtime 코드 변경 없음.
- 사용자 승인 범위는 통합 커밋과 로컬 develop 병합이며 원격 푸시 및 원본 브랜치 삭제는 제외한다. 실제 브라우저 증거는 2026-10-13 기록을 유지한다.

## 통합 커밋·로컬 develop 병합 시작 (2026-10-15)

- 승인: 사용자 요청으로 통합 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 수행하지 않는다.
- 기준 확인: 통합 HEAD·로컬 develop·읽기 전용 조회한 원격 develop이 모두 `fb75a467fba8c430f6da4a8e215d1c0f3b995470`이다. 기존 통합 변경 307개 파일과 원본 521개 파일의 현재 SHA를 확인했다.
- 검증: 현재 통합 소스의 전체 Python, frontend test/build, 생성 코드 최신성을 재실행 중이다. 기존 브라우저 증거는 2026-10-13 실행 기록이며 이번에 재실행한 것으로 표기하지 않는다.
- 병합 방식: 원본 worktree를 전환하거나 초기화하지 않고 별도 develop checkout에서 병합한다. 모든 원본 변경과 기능 브랜치를 보존한다.

## 실제 브라우저 통합 검증 및 최종 회귀 완료 (2026-10-13)

- 브라우저: 같은 5182 주소의 정상 in-app browser에서 임시 OIDC 로그인·로그아웃·재로그인 및 팀 A/B 전환을 확인했다. 과거 도구 차단은 재현되지 않았으며 사용자 설정 오류로 단정하지 않는다. 우회 없음.
- 가져오기: 팀 A에서 로컬 테스트 공급자의 공개 metadata GET을 cURL preview→항목 저장→새로고침 후 케이스 1개 유지로 확인했다. 팀 B에는 케이스 0개였다.
- 릴리스: `1.0.0-browser` 초안→발행(release revision 2)→고정 원본 조회를 수행했다. 포털 명세 revision 1과 source digest가 같고 뒤로 가기·새로고침·재로그인 후 보존됐다. 팀 B에는 발행 릴리스 및 팀 A SDK job이 없었다.
- 실제 다운로드: 포털 Python 릴리스 ZIP 32,707 bytes(SHA `602bcee3e7a59bfa78e6d58c93150dd021935c7cc24f8239c5703bb002e56bfc`), 일반 TypeScript ZIP 9,619 bytes(SHA `3feb07d9304a4356925049d345b7a1a4268da356b9dd2cc147978767e8952ba8`)를 브라우저 download 완료 이벤트와 Downloads 파일로 확인했다. 두 ZIP CRC 통과, 릴리스 manifest의 revision/source digest/릴리스 ID 일치. 일반 SDK 동일 job ID의 새로고침 복원도 통과.
- 실행 복원 경계: 가져온 케이스의 Run ID `cdfeef4b-b047-4294-9da4-0ce09b9d0a66`과 terminal 오류가 새로고침 후 복원됐다. fixture는 대상 소유권 증명이 없어 `configuration_error`로 정상 차단됐다. 이를 성공 API 실행으로 표시하지 않으며 앞선 실제 HTTP 성공 증거와 구분한다.
- 최종 검증: shutdown 수정 후 현재 통합 상태에서 **Python 554개(skip 0, 142.777초)**, 프런트엔드 **111개/27파일**, production build, OpenAPI 생성 최신성, `git diff --check` 통과. 과거 552개 결과는 수정 전 이력으로 보존했다. 로그는 `/tmp/roadmap-integration-final-{python,web,build,generated}.log`.
- 원본 확인: 이전 manifest 521개 중 P1 진행 문서 2개만 앞선 사용자 요청의 재검증 기록으로 달랐다. 이번 통합 계속 작업에서는 원본 worktree를 수정하지 않았다. 기존 통합 코드는 보존했고 발견된 제품 결함 및 제품 코드 수정 없음.
- 정리/반영: 임시 계정 로그아웃·브라우저 탭 종료·검증 서버 정상 종료(exit 0). 증거/계획/두 진행 문서와 스크린샷만 갱신했다. 브랜치 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 유지, 커밋·병합·푸시 없음.
- 남은 범위: 운영 공급자·배포·전체 LT 캠페인/SLO·공통 pagination 등은 여전히 별도다. 이번 결과는 지정된 로컬 통합 브라우저 흐름 검증이며 전체 로드맵 완료가 아니다.

## 새 채팅 브라우저 통합 검증 시작 (2026-10-13)

- 시작: 지정 통합 worktree의 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 및 미커밋 통합 변경을 확인했다. 기존 변경과 원본 worktree를 보존한다.
- 환경: 기존 임시 스크립트와 Python 환경을 확인하고, 사용자 데이터와 분리된 새 임시 DB/두 Workspace/OIDC 공급자를 같은 5182·5183 포트로 실행했다.
- 접근: 정상 `cua_repl` in-app browser로 5182 로그인 화면과 SSO 로그인 후 팀 A 프로젝트 목록을 확인했다. 이전 저장 권한 정책 거절은 이번 세션에서 재현되지 않았다. 다른 포트/브라우저/직접 명령 우회 없음.
- 기록 정정: 과거 기록의 사용자 설정 변경 필요 단정은 확인된 원인이 아니다. 사용자는 이미 항상 허용을 확인했으며 이번 정상 도구 접근은 성공했다.
- 진행: Workspace·import·release·portal·SDK 다운로드 및 새로고침/뒤로 가기/실행 복원을 실제 브라우저로 검증한다. 기존 552개 전체 Python은 마지막 shutdown 수정 전 결과임을 유지한다.

## 브라우저 차단 사유 재확인

- 사용자 재개 요청 후 기존 검증 주소 `http://127.0.0.1:5182`를 확인했으며, 브라우저 도구가 저장된 사용자 권한 설정에 의한 차단이라고 명시했다. 일반 채팅 승인이 부족한 상태가 아니라 저장된 사이트 차단 설정의 변경이 필요하다.
- 차단 해제 여부를 사용자에게 요청했다. 해제 답변 전 재접속·다른 브라우저·주소 변경·직접 브라우저 명령으로 우회하지 않는다. 제품 코드 변경·테스트 재실행·Git 게시 없음.

## 통합 SDK 실제 Java 취소·시간 초과 확인 (2026-10-13)

- 시작: 통합 계획의 실제 generator lifecycle 근거를 현재 feature/roadmap-integration에서 확인했다. 제품 코드는 변경하지 않았다.
- 검증: 임시3500 operation 명세의 Java 프로세스 실행을 관측한 뒤 취소(0.497초), 별도2초 deadline으로 timeout(2.062초)을 확인했다. 각 작업의 준비/Java 프로세스2개 모두 종료, 작업 임시 디렉터리0개, 게시 ZIP 없음.
- 관측 이력: 최초5초 제한은 생성이 제한 전에 정상 완료돼 timeout fixture 조건을 만족하지 않았다. 제한을2초로 명시해 별도 실행했으며 제품 timeout 실패로 해석하지 않는다.
- 결과/남은 게이트: [통합 검증 JSON](roadmap-integration-validation.json)에 기록했다. 실제 브라우저 검증은 도구 접근 거절로 대기, 운영 issuer/client 정보도 미제공 상태다. Git 게시 없음.

## 7개 작업 로컬 통합·검증 (2026-10-13)

- 승인/기준: 사용자 `승인`에 따라 원격 develop `fb75a46`과 같은 기준으로 `feature/roadmap-integration`을 생성했다. 7개 원본 worktree의521개 파일 항목을 snapshot/hash로 보존했고 완료 시 원본 변경0개를 확인했다. commit/develop merge/push는 하지 않았다.
- 변경: P0/P1·OAS-1·API-3·RUN-2·IOP-1·COL-1/2·GOV-1/DOC-1을 결합했다. OpenAPI route/model102개를 재생성하고 인증 gate·import·release·portal·SDK 화면과 스타일을 함께 연결했다.
- 통합 수정: OAuth 실행 Vault를 현재 사용자/Workspace에 연결, Runner의 OAuth 발급 허용, SDK queue 시작 전 membership 재확인, portal ZIP에도 authenticatedFetch 적용, API OAuth callback query 로그 제거, P1 계측의 Workspace case root 사용, shutdown 시 영구 commit을 끝낸 release job의 성공 상태 보존을 반영했다.
- 저장소: identity/release 독립 migration과 OAuth v6를 결합했다. 계정·감사·release·SDK ZIP은 이관하고 session/pending 및 OAuth token은 제외한다. 하나의 SQLite source에 모든 기능을 넣어 PostgreSQL parity·ZIP bytes·migration version·원본 DB 불변을 확인했다.
- 자동 검증: 전체 Python552개(skip0,78.093초), frontend111개·production build, 생성 최신성·diff 검사 통과. 이후 shutdown commit 경계 수정은 job/SDK/portal/교차 기능45개(8.685초), 결합 PostgreSQL 이관 신규1개(0.299초)로 검증했다. 전체552개를 최종 shutdown 수정 후 재실행한 것으로 표기하지 않는다.
- 실제 HTTP: 테스트 인증 어댑터와 독립 loopback 서버에서 두 Workspace의 OAuth 발급→빠른 호출→실제 Python 자식 runner→파이프라인→이력 및 import/export 격리 확인. 실제 Java 생성기로 Python SDK·release Go SDK를 생성해 ZIP CRC/SHA·원본 revision/digest·타 Workspace404·작업 관리자 재시작 후 동일 파일을 확인했다.
- 실제 HTTPS: 임시 CA 검증을 켠 OIDC 공급자와 Uvicorn에서 로그인·PKCE·CSRF·Workspace 전환·logout·replay 거부·token 미저장 fixture를 통합 코드로 다시 실행해 통과했다. 운영 공급자를 사용한 결과는 아니다.
- 실패 이력: 첫 Python 통합 실행547개는 기존 TestClient host/identity fixture 불일치13실패·3오류였다. loopback Host·임시 identity DB·trusted adapter로 fixture를 수정했다. 추가 실제 runner 검증의 첫 실행은 임시 fixture ROOT에 CLI entrypoint가 없어 실패했으며 repo 실행 root와 임시 data root를 구분해 해소했다.
- 완료 경계: 로컬 코드 통합과 위 검증까지. 실제 브라우저 접근은 사용자 허용 후에도 도구 정책 거절 상태로 남아 있다. 운영 issuer 등록·외부 배포·전체 LT campaign·공통 pagination 등은 미완료이며 이전 실패/unknown을 변경하지 않는다.
- 자료: [통합 검증 JSON](roadmap-integration-validation.json), [원본 파일 해시](roadmap-integration-source-manifest.json), [통합 계획](roadmap-integration-plan.md).

## 통합 시작 (2026-10-13)

사용자 승인으로 `feature/roadmap-integration`에서 7개 작업을 통합한다. 원본 worktree는 보존하고 commit/develop merge/push는 하지 않는다. 인증·저장소·job·화면 계약을 결합하고 전체 회귀 및 교차 Workspace 통합 검증을 수행한다. 브라우저 접근 제한은 별도다.

### 원본 단계별 기록

- [COL 기존 기록](archive/integration-sources/COL/api-load-test-progress.md)
- [P1 기존 기록](archive/integration-sources/P1/api-load-test-progress.md)
- [OAS 기존 기록](archive/integration-sources/OAS/api-load-test-progress.md)
