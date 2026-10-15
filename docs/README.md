# 문서 안내

현재 기능의 사용법과 운영 계약은 `docs/` 루트에서 관리하고, 개발 과정의 일회성 인계·리뷰·검증 기록은 `docs/archive/`에 보관한다.

## 계획과 진행 상태

- [통합 계획과 검증](roadmap-integration-plan.md)
- [API 개발 기능 로드맵](api-development-plan.md)
- [API 개발 기능 진행 기록](api-development-progress.md)
- [API 부하테스트 계획](api-load-test-plan.md)
- [API 부하테스트 및 대시보드 개발 진행 기록](api-load-test-progress.md)

## 기능 및 운영 문서

- [OIDC 로그인과 Workspace 세션](oidc-login.md)
- [Workspace 요청·실행 격리](workspace-isolation.md)
- [도구 가져오기·내보내기](tool-interoperability.md)
- [릴리스 개발자 문서와 영속 SDK](developer-portal.md)

- [API 릴리스와 승인 이력](api-release-lifecycle.md)

- [잠정 부하테스트 기준선·용량·병목 보고서](load-test-baseline-report.md)
- [P1 동일 조건 기준선·회복 진단 사용법](load-test-harness.md)
- [P1 정규 Baseline 결과](p1-baseline-report.md) · [전체 증거 JSON](p1-baseline-evidence.json)
- [P1 정규 회복 진단 결과](p1-recovery-report.md) · [전체 증거 JSON](p1-recovery-evidence.json)
- [P1 측정 해석과 남은 한계](p1-baseline-recovery-analysis.md) · [검증 색인](p1-validation.json)
- [부하테스트 fixture와 격리 k6 하네스](load-test-harness.md)
- [부하테스트 결과 계약과 importer](load-test-results.md)
- [Mock Server](mock-server.md)
- [비동기 실행](async-runs.md)
- [SDK 비동기 생성과 ZIP 수명주기](sdk-generation-jobs.md)
- [실행 보고서](run-reports.md)
- [OpenAPI 원본 편집 API](openapi-editor.md)
- [OpenAPI 계약 검증](openapi-contract-validation.md)
- [테스트 커버리지와 데이터 수명주기](test-coverage-lifecycle.md)
- [요청 프로필](request-profiles.md)
- [OAuth 2.0 프로필 발급·연결](oauth-profiles.md)
- [API 소유권 확인과 외부 Setup](ownership-verification.md)
- [FastAPI HTTP 계약](fnd-3-http-contract.md)
- [PostgreSQL·Redis 저장소 운영 계약](fnd-4-storage.md)
- [OpenAPI Generator 서버 구조](generated-server.md)

## 보관 기록

- [MOCK-1 개발·리뷰·검증 기록](archive/mock-1/README.md)

보관 문서는 당시 판단과 실행 증거를 유지하기 위한 자료다. 현재 상태를 판단할 때는 진행 기록과 기능 문서를 우선한다.
