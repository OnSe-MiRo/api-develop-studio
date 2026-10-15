# 프로젝트 목록 페이지네이션·검색·정렬

프로젝트 목록 화면(`/projects`)은 페이지 조회 API를 사용한다. 기존 편집기/대시보드의 프로젝트 선택과 케이스·파이프라인 목록은 이번 범위에 포함하지 않는다.

## API 계약

`GET /api/projects?page_size=20&q=검색어&sort=reference_asc&cursor=...`

- `page_size`: 1~100, 기본20. 화면 선택은10/20/50/100이다.
- `q`: 앞뒤 공백을 제거한 최대100자. 프로젝트 이름(`name`) 또는 파일명/reference의 literal 부분 문자열이다. `%`, `_`, `!`는 wildcard가 아니라 검색 문자다. ASCII 대소문자는 구분하지 않는다. ASCII 밖의 대소문자 처리는 각 DB의 LOWER 규칙을 따른다.
- `sort`: `reference_asc`(기본), `reference_desc`, `created_desc`. 파일명은 DB locale과 무관한 binary/C 정렬이다. 생성일 동률은 reference 내림차순으로 구분한다.
- `cursor`: 응답이 반환한 불투명 문자열을 그대로 사용한다. Workspace·검색어·정렬·크기·예제 표시 설정이 달라지거나 커서 형식이 잘못되면400이다. 클라이언트가 scope를 제공하더라도 실제 SQL은 인증된 서버 Workspace와 membership을 사용한다.
- 응답은 기존 `items`, public `details`(name/base_url)에 `nextCursor`, `previousCursor`를 추가한다. 이동할 페이지가 없으면 null이다. 불필요한 전체 개수 조회는 하지 않는다.
- 위 네 query parameter를 모두 생략하면 기존 전체 목록 계약이 유지된다. 프로젝트 화면의 초기 로딩은 이 전체 목록을 요청하지 않는다.

SQL은 `LIMIT page_size + 1`과 keyset 조건을 적용한다. 페이지 결과의 현재 revision만 읽으며 전체 목록을 Python으로 가져온 후 자르거나 reference별 문서를 반복 조회하지 않는다. 이름 검색은 현재 revision의 JSON name을 조회하므로 대규모 substring 검색에 대한 별도 성능 보장은 하지 않는다.

## 페이지 일관성과 화면

조회 조건과 커서는 URL에 저장된다. 검색 제출(Enter 포함), 정렬/크기 변경 시 첫 페이지로 이동한다. 새로고침·브라우저 뒤로 가기로 조건을 복원하고 오래된 요청 응답은 무시한다. Workspace 전환은 기존 인증 흐름에 따라 프로젝트 화면 및 조건을 초기화한다.

페이지 이동은 고정 snapshot이 아닌 현재 데이터 기준이다. 중간 행의 삽입/삭제로 OFFSET이 밀리며 기존 행을 중복/누락하는 문제를 피한다. 이미 지나간 위치에 새로 생긴 행, 검색 이름이 변경된 행까지 고정된 목록으로 보장하지 않는다. 그런 변경을 모두 다시 확인하려면 첫 페이지부터 새로 조회한다. 마지막 페이지의 항목이 모두 삭제되면 첫 페이지로 복귀한다.

## 검증

- SQLite·실제 API 집중5개, PostgreSQL 집중1개: 세 정렬의 전/후 페이지 순회, 생성일 동률, 중간 삭제/삽입, 한글 및 literal wildcard 검색, 예제 숨김, Workspace/조건별 커서 거부, 입력 경계, 기존 API 호환, 전체/개별 반복 조회 미사용.
- 전체 Python560개(skip0,121.865초), 최종 frontend117개(29파일) 및 production build 통과. 관련11개도 통과했다. 생성 코드 최신성·diff 검사 통과.
- 실제 브라우저: 임시 OIDC/격리 DB의 팀 A46개가20→20→6개로 표시, 이전 이동과 둘째 페이지 새로고침, 이름 검색7개, 내림차순·최신순·크기 변경, Enter/빈 검색, 프로젝트 진입 후 뒤로가기 복원 확인. 팀 B는4개이고 검색 결과1개로 격리됐다. 프로젝트 목록 초기 요청에는 모두 page_size가 있었다. 프로젝트 상세 진입 시 기존 편집기 선택용 전체 조회는 유지된다.
- 실제 브라우저 콘솔 오류/경고0개. [화면 증거](project-list-pagination-browser.jpg).
- 로그: `/tmp/project-pagination-python-all.log`, `/tmp/project-pagination-pg.log`, `/tmp/project-pagination-web-final-all.log`, `/tmp/project-pagination-web-final-focused.log`, `/tmp/project-pagination-build.log`, `/tmp/project-pagination-generated-check.log`.
