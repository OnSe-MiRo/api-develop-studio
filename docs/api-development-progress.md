# API 개발 기능 진행 기록

이 문서는 [`API 개발 기능 로드맵`](api-development-plan.md)의 구현 상태를 기록하는 단일 기준 문서다. 코드 변경과 진행 기록 갱신은 같은 작업 범위에서 수행한다.

## 현재 요약

- 최종 갱신일: 2026-09-07
- 현재 단계: 계획 수립 완료
- 전체 상태: 대기
- 작업 브랜치: `feature/developer-docs`
- 다음 작업: 통합 브랜치 이름 확정과 FND-1 기능 branch 통합 설계

상태는 `대기`, `진행`, `완료`, `차단` 중 하나만 사용한다. 완료 기준과 검증을 충족하기 전에는 `완료`로 변경하지 않는다.

## 단계별 현황

| ID | 작업 | 우선순위 | 상태 | 다음 확인 사항 |
| --- | --- | --- | --- | --- |
| FND-1 | 빠른 호출·실행 대시보드 branch 안전 통합 | P0 | 대기 | `dev`·`develop` 기준 결정 |
| FND-2 | frontend test·DB migration·모듈 분리 기반 | P0 | 대기 | 최소 migration 계약 |
| API-1 | 빠른 API 호출 | P0 | 대기 | 공통 request model |
| API-2 | 환경 프로필 | P0 | 대기 | 기존 `base_url` 호환 방식 |
| API-3 | 공통 인증 모델 | P0 | 대기 | 1차 지원 방식 확정 |
| RUN-1 | 구조화된 실행 결과와 CI report | P0 | 대기 | 결과 JSON schema |
| RUN-2 | 비동기 job과 실행 제한 | P0 | 대기 | worker lifecycle |
| OAS-1 | OpenAPI operation·schema·security 편집 | P0 | 대기 | 편집 데이터 모델 |
| OAS-2 | lint·응답 schema·breaking change 검증 | P0 | 대기 | lint 정책과 차단 수준 |
| TST-1 | 명세–케이스 커버리지 | P1 | 대기 | operation 안정 ID |
| TST-2 | 명세 변경과 케이스 동기화 | P1 | 대기 | 사용자 assertion 보존 규칙 |
| TST-3 | 테스트 데이터 setup·teardown | P1 | 대기 | 허용 generator 목록 |
| MOCK-1 | OpenAPI 기반 Mock Server | P1 | 대기 | state와 외부 공개 정책 |
| OBS-1 | 기능 테스트 실행 이력 | P1 | 대기 | RUN-1 공통 metadata |
| OBS-2 | 부하테스트 결과 대시보드 | P1 | 대기 | 별도 진행 기록 참조 |
| IOP-1 | cURL·Postman·HAR 연동 | P1 | 대기 | 지원 형식과 round trip 기준 |
| COL-1 | 로그인과 RBAC | P2 | 대기 | 인증 방식과 배포 형태 |
| COL-2 | Workspace 데이터 격리 | P2 | 대기 | migration과 권한 query |
| GOV-1 | API lifecycle과 변경 로그 | P2 | 대기 | release·revision 연결 |
| DOC-1 | 개발자 문서 portal | P2 | 대기 | 공개 범위와 인증 |
| EXT-1 | 비REST 프로토콜 확장 | P2 | 대기 | 사용자 수요 확인 |

OBS-2의 상세 상태는 [`API 부하테스트 및 대시보드 개발 진행 기록`](api-load-test-progress.md)에서도 관리한다. 두 문서의 상태가 다르면 실제 검증 기록이 최신인 문서를 확인하고 같은 작업 안에서 동기화한다.

## 현재 작업

- 작업 ID: 없음
- 목표: 없음
- 변경 예정 파일: 없음
- 시작 시각: 없음
- 상태: 대기
- 확인이 필요한 사항: 통합 브랜치가 `dev`인지 `develop`인지 결정 필요

## 검증 기록

| 일시 | 작업 ID | 명령 또는 확인 방법 | 결과 | 비고 |
| --- | --- | --- | --- | --- |
| 2026-09-07 | PLAN | 문서 링크, 작업 ID, trailing whitespace와 `git diff --check` 확인 | 통과 | 애플리케이션 코드는 변경하지 않음 |
| 2026-09-07 | PLAN | 현재 기능, 원격 기능 branch, 문서와 코드 구조 비교 | 완료 | 구현은 시작하지 않음 |

## 결정 기록

| 일자 | 결정 | 이유 | 영향 |
| --- | --- | --- | --- |
| 2026-09-07 | REST와 OpenAPI 핵심 흐름을 먼저 완성 | 현재 제품 구조와 보유 기능을 활용하고 범위 확산 방지 | GraphQL·gRPC·AsyncAPI는 P2 이후 검토 |
| 2026-09-07 | 기능 테스트와 부하테스트가 공통 run metadata 사용 | 실행 이력 저장과 화면의 중복 방지 | RUN-1이 두 대시보드보다 선행 |
| 2026-09-07 | quick-call과 execution-dashboard branch를 최신 기준에 재구성 | 두 branch가 후속 기능과 테스트보다 이전 기준에서 분기 | 원본 branch 직접 병합 금지 |
| 2026-09-07 | 임의 스크립트보다 declarative test data 기능 우선 | 로컬·다중 사용자 환경의 명령 실행 위험 축소 | generator와 setup·teardown 기능 범위 제한 |

## 변경 이력

최신 항목을 위에 추가하고 작업 ID, 변경 파일, 검증 결과, 알려진 제한과 다음 작업을 기록한다.

### 2026-09-07 — PLAN — API 개발 기능 로드맵 작성

- 변경: 현재 기능 격차, P0~P2 우선순위, 단계별 완료 기준과 의존 관계 정의
- 변경 파일: `docs/api-development-plan.md`, `docs/api-development-progress.md`, `docs/README.md`, `AGENTS.md`
- 검증: 저장소 문서, 현재 코드와 원격 기능 branch 비교, 문서 링크·형식 확인
- 제한: 구현 작업과 기능 테스트는 시작하지 않음
- 다음: 통합 브랜치 이름 확정 후 FND-1 착수

## 차단 사항

현재 구현은 시작하지 않아 차단 상태가 아니다. 다만 FND-1 착수 전 저장소 규칙의 `develop`과 실제 원격의 `dev` 중 통합 기준을 확정해야 한다.

차단이 발생하면 작업 ID, 발생 시각, 재현 방법, 영향, 시도한 해결책과 필요한 결정을 기록한다. 해소 후에도 항목을 삭제하지 않고 해결 시각과 방법을 추가한다.

## 갱신 체크리스트

- 작업 시작 전 `현재 요약`, `단계별 현황`, `현재 작업` 갱신
- 설계나 범위가 바뀌면 `결정 기록` 갱신
- 의미 있는 구현 단위마다 `변경 이력` 추가
- 실행한 검증의 성공과 실패를 `검증 기록`에 모두 추가
- 차단 시 관련 단계 상태와 `차단 사항` 갱신
- 완료 기준을 충족한 경우에만 단계 상태를 `완료`로 변경
- 사용자 완료 보고 전에 요약, 검증, 변경 이력과 다음 작업 갱신
