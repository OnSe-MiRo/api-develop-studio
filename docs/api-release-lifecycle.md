# API 릴리스와 승인 이력 (GOV-1)

API 목록의 **API 릴리스**에서 현재 프로젝트 revision으로 초안을 만든다. 릴리스에는 version, 변경 설명, 고정된 명세 원본, 원본 SHA-256, 비교 기준과 분석 결과가 저장된다. 프로젝트 변수·secret·인증 프로필은 릴리스 snapshot에 복사하지 않는다. 명세 자체에 포함된 예시와 설명은 원본 그대로 보존하므로 작성자는 발행 전에 이를 검토한다.

## 원본과 버전

- 파일 또는 bundle로 저장된 OpenAPI 3.0/3.1만 릴리스한다. lint 오류와 외부/file 참조는 거부하며 원본은5 MiB 이하이다. bundle의 raw 파일 텍스트와 안전한 상대 경로를 보존한다.
- URL-only 프로젝트 revision은 URL의 실제 내용이 고정되지 않아 거부한다. 프로젝트에 명세를 저장한 다음 릴리스한다.
- 접수한 `projectRevision`이 현재 저장 revision과 다르면409이다. DB의 immutable document revision에서 명세만 읽으며 프로젝트 파일을 다시 다운로드하지 않는다.
- version은 `1.2.3` 형태(선행 `v`, prerelease/build 식별자 허용), 최대80자이다. 같은 Workspace·프로젝트에서 사용한 version은 재사용하지 않는다. 초안도 원본·version·설명을 수정하지 않는다. 잘못 만든 초안은 사유와 함께 폐기하고 새 version으로 만든다.
- bundle/file source digest는 `kind` 및 원본 필드를 canonical JSON(키 정렬·UTF-8·공백 없는 separator)으로 인코딩한 SHA-256이다. RUN-2 SDK의 동일 원본 digest와 연결 가능한 계약이며, sourceDigest를 artifact의 ZIP digest와 혼동하지 않는다.

## 상태와 승인

| 현재 상태 | 가능한 다음 상태 | 권한 |
| --- | --- | --- |
| draft | published, retired | Owner 또는 Admin |
| published | deprecated, retired | Owner 또는 Admin |
| deprecated | retired | Owner 또는 Admin |
| retired | 없음 | 상태 변경 불가 |

Owner/Admin/Editor는 초안을 만들고 active Workspace 구성원은 해당 Workspace의 릴리스와 원본을 조회한다. 상태 전환에는 최신 **릴리스 revision**과1~2,000자 사유가 필요하다. 프로젝트 revision과 릴리스 revision은 서로 다른 값이다. 같은 revision을 동시에 변경하면 한 요청만 성공한다.

발행은 Workspace 내부 릴리스 상태를 바꾸는 동작이다. 외부 공개, Git push, 배포, 공개 portal 게시를 자동 수행하지 않는다. 승인자는 body의 `approvedBy`가 아니라 서버 저장소 context의 사용자로 기록한다. 릴리스 상태/revision과 승인 이벤트는 한 transaction에서 저장되어 이벤트 저장이 실패하면 상태도 되돌아간다.

## 변경 로그와 deprecated

기준 릴리스를 명시하지 않으면 초안 생성 당시 최근 published/deprecated 릴리스를 사용한다. 명시 기준은 같은 Workspace·프로젝트의 발행된 릴리스여야 한다. 분석 기준은 초안에 고정되며 뒤에 발행된 다른 릴리스로 조용히 바뀌지 않는다.

- operation 추가/삭제/수정, deprecated 설정/해제를 별도로 보여준다.
- OAS-2의 보수적 호환성 분석으로 breaking/review 항목을 기록한다. 항목이 있으면 발행자가 **호환성 변경을 검토하고 승인합니다**를 명시적으로 선택해야 한다.
- 분석 자체의 오류는 수동 승인으로 우회할 수 없다.
- 비교 결과는 원래 분석 결과로 보존한다. 승인했다고 `comparison.compatible`을 다시 쓰지 않으며 승인 여부·사유·사용자는 별도 이벤트에서 확인한다.
- 릴리스 전체의 deprecated 상태와 명세 operation의 `deprecated:true`는 별개다. 화면은 둘 다 보여주며 상태 전환으로 원본 명세를 수정하지 않는다.

## API와 저장소

- `GET/POST /api/projects/{reference}/releases`: 목록/초안 생성. 목록은20개 기본,1~100개 limit 및 `before` cursor로 페이지를 나눈다.
- `GET /api/projects/{reference}/releases/{releaseId}`: metadata, 변경 분석, deprecated operations, 승인 이벤트.
- `GET .../{releaseId}/source`: 고정 원본과 projectRevision/sourceDigest.
- `POST .../{releaseId}/transition`: `{state, revision, reason, acknowledgeChanges}`.

모든 lookup은 Workspace와 프로젝트를 함께 검사한다. 다른 Workspace의 release ID·baseline·cursor는404이다. 프로젝트가 soft-delete되면 해당 경로의 릴리스도 숨기되 데이터는 보존한다.

`api_releases`, `api_release_events`는 전용 `release_schema_migrations` ledger로 관리한다(v1: 릴리스/이력, v2: portal metadata/영속 SDK). 기존 Studio schema와 OAuth branch의 migration6를 변경하지 않는다. SQLite→PostgreSQL importer는 snapshot 내부에서 이 schema를 준비한 뒤 원본·이벤트를 복사하고 row/digest·Workspace 연결·원본 지문을 검증한다. 원본 SQLite 파일을 수정하지 않는다.

## 단계 경계

이 기능은 `feature/api-release-lifecycle`에서 별도로 구현됐다. COL-2의 실제 HTTP CurrentUser/RBAC 경계와 통합한 뒤 승인 주체·역할을 종단 재검증해야 하며, COL-1 로그인 전에는 외부 다중 사용자 서비스로 배포하지 않는다. 같은 분기의 DOC-1에서 SDK ZIP 보존·연결과 릴리스별 인증/환경/예시 portal을 구현했다. [DOC-1 계약](developer-portal.md)을 참고한다. 실제 브라우저·인증 경계 통합 검증은 별도 완료 조건이며 내부 published 상태만으로 외부 공개를 의미하지 않는다.
