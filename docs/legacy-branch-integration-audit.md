# 미병합 기능 브랜치 감사·통합 (2026-11-04)

기준 develop: `95c8518e1c27c0de7de3fbf7106cff477c5249d0`.
대상은 로컬 미병합 기능 브랜치6개다. main은 보호 브랜치로 그대로 유지한다. 원격 fetch/push/delete는 하지 않는다.

## 판정

| 브랜치 | tip | 실제 미반영 내용과 처리 |
| --- | --- | --- |
| feature/quick-api-call | ac9a7ed | 기능은 이미 이식됨. 기존 최신 제품 코드 유지, 이력만 연결 |
| feature/api-execution-dashboard | 6fca6d2 | 기능은 이미 재구현·확장됨. 기존 최신 제품 코드 유지, 이력만 연결 |
| feature/run-admission-policy | 40a852f | 접수 정책·k6 모델·검증 자료 통합됨. baseline 병합으로 이력 연결 |
| feature/openapi-editor-completion | 40a852f | 브랜치 이름과 달리 tip은 동일 P0 커밋. OAS 편집은 roadmap 통합2c54a41에 포함. baseline 병합으로 이력 연결 |
| feature/load-test-baseline-recovery | b4007dd | ebf7672 대비 제품 코드 동일, 진행 기록2파일22줄만 추가. 일반 병합으로 기록 보존 |
| feature/readme-main-overview | 838adfe | 영문 개요가 실제 미반영. 기존 한국어 README를 유지하고 최신 develop에 맞춘 README.en.md로 반영 |

## 코드·이식 근거

- quick-api-call의 `0b4317e/6375592/94b4cd4/ac9a7ed`와 develop의 `7619e13/1dc1e65/120158c/a917510`을 range-diff 및 개별 파일 diff로 대조했다. `6375592`와 `ac9a7ed`는 patch-equivalent다. 요청/인증 이식의 차이는 기존 응답 시간 측정 및 maxResponseTimeMs 보존이다. authorization.py와 해당 인증 테스트는 이식 시점에 동일했다. 현재 공통 요청 경로·AuthorizationEditor·ApiCallPage에서 후속 환경/인증/계약/소유권 경계를 유지한다.
- dashboard는 `6fca6d2`의 이력 기록, 기간/프로젝트/상태/페이지, KPI·일별 추이 기능이 `43a534d`에서 최신 구조로 재구현됐다. 숫자 ID는 공통 Run ID로 변경됐고 현재 `api_test/execution_history.py`, `web/src/pages/dashboard/ExecutionDashboard.jsx`에 Workspace·상세·검색·재실행·URL 복원이 확장됐다. 옛 monolithic react_server.py와 web/src/ExecutionDashboard.jsx를 다시 도입하지 않는다.
- P0의 JobError code/admission metadata 및 RUN_WORKERS_BUSY/RUN_CAPACITY_EXCEEDED/RUN_USER_LIMIT_EXCEEDED/RUN_PROJECT_LIMIT_EXCEEDED가 현재 jobs/main에 존재한다. run-sustained·sustained_verdict와 관련 회귀도 보존되어 있다. `load-tests/k6/run-admission.js`, 해당 Node 테스트, `docs/run-admission-validation.json`은40a852f와 현재 develop에서 byte 동일하다.
- b4007dd는40a852f와ebf7672의 병합이다. `git diff --name-status ebf7672 b4007dd` 결과는 진행 문서2개뿐이다. 따라서 이 브랜치에서 추가 제품 코드를 가져올 항목이 없다.
- README 변경은 예전 main 전용 요약이다. Python HTTP server/SQLite 전용 안내, API 포트 직접 노출, 로그인 설정 없는 Compose 안내를 그대로 가져오면 현재 FastAPI·PostgreSQL/Redis·인증 gateway 구성과 어긋난다. 영문 개요를 최신 구조와 로컬/원격 실행 경계에 맞추고 원본 한국어 상세 안내는 보존한다.

## 병합 방식과 보존

`feature/legacy-branch-integration`에서 작업한다. baseline은 일반 병합, 이미 이식된 quick/dashboard는 `-s ours`로 과거 이력만 연결한다. 이는 미반영 코드를 무시하기 위한 일괄 전략이 아니라 위 비교로 이미 반영된 변경을 최신 코드로 유지하기 위한 선택이다. README 브랜치는 최신 영문 개요를 별도 파일에 적용한 병합으로 기록한다.

원본 worktree의 미커밋 README.md 및 진행 문서2개는 이번 병합 대상이 아니다. 원본 HEAD·status·세 파일 SHA-256을 `/tmp/api-studio-legacy-integration-before.json`에 저장하고 완료 시 다시 비교한다. 다른 worktree를 stash/reset/삭제하지 않으며 브랜치 삭제도 이 작업에서 하지 않는다.
