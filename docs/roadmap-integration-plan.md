# 개별 기능 통합 계획

2026-10-13의 로컬 develop `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 기준이다. 7개 worktree의 HEAD부터 현재 미커밋 파일까지 읽기 전용으로 비교했다. 사용자 승인 후 원격 develop이 이 SHA와 같음을 재확인했다. 파일별 SHA와 쌍별 비교는 [감사 JSON](roadmap-integration-audit.json)에 있다.

## 대상과 보존

| 순서 | 작업 | 현재 브랜치 |
| --- | --- | --- |
| 1 | P0 실행 접수·P1 회복 진단 | feature/load-test-baseline-recovery |
| 2 | OAS-1 편집·계약 보완 | feature/openapi-editor-completion |
| 3 | COL-2 격리·COL-1 로그인 | feature/workspace-isolation |
| 4 | API-3 OAuth profile 발급 | feature/oauth-profile-issuance |
| 5 | RUN-2 SDK generation | feature/sdk-generation-jobs |
| 6 | IOP-1 도구 연동 | feature/tool-interoperability |
| 7 | GOV-1 release·DOC-1 portal | feature/api-release-lifecycle |

사용자 승인으로 별도 `feature/roadmap-integration`에 통합했다. 원본 worktree와 기존 미커밋 변경은 그대로 보존한다. 원본 파일 SHA를 다시 비교하고 달라졌으면 감사 결과를 갱신한다. OAS-1에는 P0의 기초 커밋이 이미 들어 있으므로 중복 적용하지 않는다. 커밋·develop 병합·원격 게시·원본 브랜치 삭제를 이번 사전 감사에 포함하지 않았다.

## 확인한 충돌과 해결 기준

겹치는 경로 102개, 쌍별 텍스트 충돌 경로 78개다. 이 중 생성 코드 61개는 수작업으로 각각 병합하지 않고 원본 OpenAPI와 template을 결합한 뒤 고정 generator로 다시 생성한다. 쌍별 텍스트 무충돌은 다중 통합 또는 동작 호환을 입증하지 않는다.

- `api_test/dependencies.py`, OpenAPI template: public session/login 경계와 private request context, 업로드·JSON 크기 제한을 모두 유지한다. 라우트별 권한을 새 SDK/portal/import 기능에도 적용한다.
- `api_test/jobs.py`, `services/execution.py`: P0 admission, COL context 전달, SDK initial metadata, release artifact commit 이후 취소 금지를 함께 유지한다. queue 상태와 artifact 영구 저장의 경합을 회귀 검사한다.
- `api_test/migrate_postgres.py`: OAuth transient vault, identity 전용 migration, release/artifact 전용 migration의 순서와 영구·일시 데이터 정책을 대조한다. 감사/release/artifact는 보존하고 세션과 pending state는 복사하지 않는 계약을 검사한다. 각 원본 버전 DB에서 업그레이드를 확인한다.
- `web/src/App.jsx`, `ApiList.jsx`, `ClientGenerator.jsx`: AuthenticationGate 아래 기존 페이지·import·release·portal·SDK job 흐름을 연결한다. RUN-2의 직접 fetch를 authenticatedFetch와 결합해 CSRF 및 Workspace binding을 유지한다. 페이지 전환과 세션 만료가 기존 폼/실행 복원 상태를 누출하지 않아야 한다.
- `openapi/studio.yaml`, 생성 검사, frontend styles: 중복 선언을 제거하고 모든 새 route/DTO를 함께 생성한다. UI 의미 충돌은 테스트와 실제 브라우저로 확인한다.
- 진행 문서와 load-test 안내: 완료·실패·unknown·브라우저 차단을 당시 결과 그대로 보존하고 통합 이후 결과를 별도 기록한다.

## 통합 검증의 완료 기준

1. 전체 Python discovery, frontend test/build, generated server check, diff check 통과.
2. 두 Workspace에서 동명 프로젝트의 OAuth 발급/실행, import, SDK 생성·download, release·portal 접근을 교차 검사. 권한 해제·변조 reference·이전 Workspace 요청 거부 포함.
3. 실제 generator로 SDK source revision/digest 일치, cancel/timeout/commit 경합, 재시작 후 영구 artifact 조회 확인.
4. SQLite/PostgreSQL 각 이전 DB의 migration 및 audit/release/artifact parity 검증. 일시 인증 데이터 이전 금지와 재로그인 확인.
5. 빠른 호출→케이스→파이프라인→실행 결과→대시보드 및 release→portal→SDK 경로의 실제 HTTP 검증.
6. 브라우저 접근이 복구되면 로그인·Workspace 전환·import·release 발행·원본 조회·SDK 다운로드와 새로고침/뒤로 가기 확인. HTTP·JSDOM 결과로 이 항목을 대체하지 않는다.

## 현재 결과와 남은 검증

사용자가 새 통합 범위를 승인했고, 7개 작업의 코드를 통합했다. [검증 결과](roadmap-integration-validation.json)와 [진행 기록](api-development-progress.md)에 실제 통과 범위와 실패 후 수정 이력을 기록했다. 원본 worktree의521개 파일 항목은 변하지 않았다. 커밋·develop 병합·원격 반영·원본 삭제는 수행하지 않았다.

이전 채팅의 브라우저 접근 차단은 새 채팅의 정상 `cua_repl` 도구에서 재현되지 않았다. 임시 인증 로그인/로그아웃·Workspace 격리·cURL 가져오기·릴리스 발행/원본·포털 및 실제 SDK ZIP 다운로드·새로고침/뒤로 가기를 확인했다. 케이스 실행은 소유권 미확인 오류의 동일 Run ID 복원을 확인했으며 성공 실행으로 표기하지 않는다. 실제 운영 issuer 등록과 외부 TLS 배포는 수행하지 않았다. 공통 목록 pagination, OAS-2 추가 범위, LT 전체 캠페인/SLO/Windows 측정도 별도 잔여 항목이다. 로컬 통합을 전체 로드맵/출시 완료로 판정하지 않는다.
