# 릴리스 개발자 문서와 영속 SDK (DOC-1)

프로젝트 사이드바의 **개발자 문서**에서 published/deprecated 릴리스를 선택한다. URL의 `project`와 `release`가 특정 릴리스를 가리키므로 새로고침·링크 공유 후에도 같은 원본을 조회한다. 이 기능은 Workspace 구성원용이며 익명 공개 portal이 아니다. draft/retired 및 삭제된 프로젝트는 소비자 화면에 노출하지 않는다.

## 고정된 문서

화면은 현재 편집 중인 프로젝트가 아닌 GOV-1 snapshot을 사용한다. 명세 revision·원본 지문·release version·변경 로그를 표시하고 method, path, operationId, 설명, tag로 검색한다. Parameters, inherited/operation security 요구사항, securitySchemes와 request/response의 미디어 타입·inline 예시를 탐색할 수 있다. 명시 예시가 없으면 깊이/항목 수를 제한한 **설명용 schema 예시**를 만들며 실제 요청 검증 통과를 보장하는 fixture로 표시하지 않는다. 외부 example URL을 자동으로 불러오거나 실제 API 요청/인증을 실행하지 않는다.

OpenAPI server override와 변수를 표시하고, 해당 프로젝트 revision의 기본/named/environment URL도 별도로 고정한다. 프로젝트 변수·secret·auth profile은 복사하지 않는다. 프로젝트 URL의 userinfo 및 token/password/API key 후보 query는 제거/치환한다. 이 후보 필터가 임의의 민감정보를 모두 식별하는 것은 아니다. OpenAPI 자체의 설명·예시는 원문을 보존하므로 발행자가 검토한다.

## 같은 원본의 SDK

1. 실행 권한(Owner/Admin/Editor/Runner)이 있는 구성원이 언어를 선택하고 **이 릴리스로 SDK 생성**을 누른다.
2. 기존 JobManager의 worker/queue/user/project 한도와 조회·취소 경계를 사용한다. 언어 선택과 run ID는 release/language 범위로 복원하며 자동 재제출·다운로드를 하지 않는다.
3. 고정 OpenAPI Generator7.24.0과 bounded SDK executor가 저장된 file/bundle snapshot에서 생성한다. 현재 프로젝트 수정, body의 source/revision/workspace 필드는 원본을 바꾸지 못한다. URL 원본을 다시 다운로드하지 않는다.
4. 완료 ZIP 안의 보존 원본을 직접 읽어 sourceDigest를 다시 계산한다. 생성 결과 metadata와 ZIP 내부 원본 둘 다 릴리스 지문과 일치해야 보존한다.
5. ZIP과 SHA-256·generator version·생성 주체를 DB에 보존한다. job TTL 또는 API 애플리케이션 재시작과 무관하게 같은 ZIP bytes를 다운로드한다.

지원 언어는 Python, JavaScript, TypeScript(Axios), Java, Kotlin, Go, C#이다. ZIP 루트의 `studio-release.json`에 releaseId, version, projectRevision, sourceDigest, language, generatorVersion, sourceKind, **sourcePath**를 기록한다. 일부 생성기에는 중간 명세(`api/openapi.yaml` 등)도 있으므로 manifest의 sourcePath가 가리키는 보존 원본을 사용한다. file은 `openapi.yaml`, bundle은 `openapi/{entrypoint}`이며 모든 bundle raw 파일을 보존한다.

언어별 artifact는 한 번만 보존한다. 동시에 같은 언어를 생성하면 먼저 저장한 한 건만 남고 다른 작업은 충돌 오류로 종료된다. 취소·timeout·실패 또는 생성 중 release 폐기/membership 해제는 새 artifact를 게시하지 않는다. durable commit을 시작한 뒤에는 취소가 너무 늦은 것으로 처리하며 완료된 ZIP을 조용히 제거하지 않는다.

## 용량·다운로드·정리

- ZIP당32 MiB, Workspace당 압축 ZIP 논리 용량128 MiB. base64 저장·DB/WAL·원본 명세 공간은 별도다. 한도 초과 시 기존 릴리스를 임의 퇴거하지 않고 오류로 중단한다.
- 동시에 최대4개 다운로드. 응답 실패/연결 취소에도 lease를 해제한다. 응답은 `private, no-store`이며 저장 SHA-256과 길이를 다시 확인한다.
- Owner/Admin은 사유를 기록하여 **retired 릴리스 또는 삭제된 프로젝트**의 ZIP payload를 영구 정리할 수 있다. SHA-256·원본 지문·생성/정리 주체·시각·사유는 남는다. 필요한 ZIP/DB를 백업한 뒤 수행한다.
- 정리 후 프로젝트를 복원해도 같은 artifact bytes가 돌아오거나 같은 언어를 덮어써서 재생성되지는 않는다. portal은 정리 상태를 표시하며 다시 제공하려면 새 릴리스를 만든다.
- 진행 중 다운로드는 이미 승인해 읽은 bytes를 끝까지 전송할 수 있다. 이후 다운로드는 현재 release/membership 상태로 다시 검사한다.

## API와 저장소

- `GET /api/projects/{reference}/portal`: visible 릴리스 목록(기본20, 최대100, before cursor).
- `GET .../portal/{releaseId}`: 고정 명세·변경 로그·환경·artifact metadata·현재 생성 권한.
- `POST .../portal/{releaseId}/sdk`: `{language}`,202 job 접수. 기존 `/api/runs/{runId}`와 `/cancel`을 사용한다.
- `GET .../portal/{releaseId}/sdk/{language}`: 보존 ZIP.
- `POST .../portal/{releaseId}/sdk/{language}/purge`: `{reason}`, Owner/Admin 전용 정리.

전용 release schema v2는 portal metadata와 `api_release_artifacts`를 추가한다. v1 릴리스의 환경 metadata는 **그 릴리스의 immutable project revision**에서 backfill하며 현재 프로젝트 설정을 사용하지 않는다. SQLite→PostgreSQL 이관 시 payload·길이·ZIP hash·release sourceDigest와 Workspace 연결을 검증한다.

## 검증 범위와 통합 조건

실제 Java로7개 언어 생성, 실제 HTTP 다운로드, ZIP CRC/hash·보존 원본·manifest, Python syntax, API 애플리케이션 재시작 후 동일 bytes를 확인했다. 재귀 bundle의 raw 파일 보존, 실제 Java 취소·timeout·자식/임시 정리도 별도로 확인했다. 모든 언어 SDK의 컴파일·실제 대상 API 호출을 검증한 것은 아니다.

GOV-1/DOC-1은 같은 `feature/api-release-lifecycle`에서 구현됐고 일반 RUN-2 SDK의 bounded executor를 의존 코드로 재사용했다. 별도 COL-2/콜-1 인증 경계와 최종 통합해야 원격 다중 사용자 서비스로 배포할 수 있다. 특히 portal SDK POST의 Runner 권한 routing, job의 commit 취소 경계, OAuth vault/일반 SDK job과의 공통 문맥을 통합 회귀한다. 브라우저 도구의 localhost 접근 거절 때문에 실제 화면·브라우저 파일 전송·responsive 검증은 별도 미완료다. HTTP ZIP 검증을 브라우저 다운로드 증거로 대체하지 않는다.
