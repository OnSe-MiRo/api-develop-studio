# API 케이스 목록 페이지네이션·검색·정렬

## 범위와 호환성

`feature/case-list-pagination`은 프로젝트 목록이 병합된 로컬 develop `ff6f18c`에서 시작했다. 케이스 저장 경로 `case/{tag}/{api_name}/{case_file}.json`과 실행·편집·파이프라인·가져오기/내보내기 API를 보존한다. 파이프라인 목록 자체의 페이지 조회는 이번 범위가 아니다.

## 조회 계약

`GET /api/cases?project=demo.json&page_size=20&q=users&tag=auth&sort=name_asc`

- 페이지 조회는 `project`가 필수이며 해당 Workspace의 프로젝트가 존재해야 한다. `page_size`, `q`, `tag`, `sort`, `cursor`를 모두 생략하면 기존 전체 조회 계약을 유지한다.
- `page_size`는1~100(기본20), 화면은10/20/50/100을 제공한다.
- `q`는 앞뒤 공백 제거 후 최대100자이며 저장된 `name` 또는 태그/API/케이스 reference의 literal 부분 문자열을 검색한다. `%`, `_`, `!`는 wildcard가 아니다. ASCII 대소문자는 구분하지 않으며 그 밖의 문자는 DB LOWER 규칙을 따른다.
- `tag`는 reference 첫 구간에 정확히 일치한다. 최대128자이며 `/`, `\`를 포함하지 않는다. 빈 값은 전체 태그다.
- `name_asc`/`name_desc`는 현재 카드 이름인 케이스 파일명 순이며, 같은 파일명은 전체 reference를 같은 방향으로 정렬해 구분한다. `created_desc`는 생성일 내림차순 후 reference 내림차순이다. 파일명/reference 비교는 SQLite binary/PostgreSQL C collation이다.
- `cursor`는 Workspace·project·검색·태그·정렬·페이지 크기에 묶인다. 조건이 바뀐 커서나 잘못된 형식은400이다. 인증된 서버 Workspace로 SQL과 membership을 검사하므로 커서 내용은 권한 근거가 아니다.
- 응답은 `items`, 기존 public `details.url`, `nextCursor`, `previousCursor`다. 헤더·본문·secret은 포함하지 않는다. 페이지 경계에서는 해당 cursor가 null이다.

DB에서 keyset 조건과 `LIMIT page_size + 1`을 적용한다. 프로젝트 조회와 공통 구현을 공유하며 기존 프로젝트 커서 scope/anchor 형식도 보존한다. 페이지를 Python에서 전체 조회 후 자르거나 케이스별 문서를 반복 조회하지 않는다.

조회는 live 목록이다. 이미 지나간 위치에 삽입된 항목까지 포함하는 고정 snapshot이 아니며, 검색 대상 이름 변경도 다음 조회에 반영된다. 변경된 전체 목록은 첫 페이지부터 다시 확인한다. JSON 부분 문자열 검색과 파일명 정렬의 대규모 성능/SLO는 이번 검증 범위가 아니다.

## SQLite 전체 목록의 URL 요약

페이지 조건을 생략한 전체 조회는 Workspace·프로젝트에 해당하는 정렬된 참조를 DB에서 얻고, 각 케이스의 현재 `request.url`을 `details`로 반환한다. POSIX에서 직접 접근할 수 있는 일반 JSON 파일은 검증된 URL을 재사용한다. 각 목록 요청에서 상위 디렉터리의 실제 경로와 파일의 장치·inode·크기·mtime·ctime을 확인한다. 파일이 바뀌면 기존 경로 검사와 UTF-8 JSON 읽기를 수행한다. 파일을 읽는 동안 버전이 바뀌거나 최근 2초 안에 변경된 파일은 재사용 대상에서 제외한다.

프로세스 내 최대 32,768개 항목으로 제한하고, 경로와 URL 두 문자열의 합산 객체 크기가 1 KiB 이내인 값만 보관한다. 자격 증명 후보·사용자정보·fragment가 있는 URL, 별칭이나 심볼릭 링크는 기존 검사 경로로 읽는다. 전체 URL 응답은 이 보관 조건과 독립적이다. Windows에서는 ctime이 생성 시간을 나타낼 수 있어 파일을 직접 확인한다. PostgreSQL은 저장 리비전을 조회한다. P1의 파일 읽기 건수와 byte 계측은 전체 목록이 실제로 연 파일만 센다. 캐시 확인 및 파일 상태 조회 비용은 handler의 기타 시간에 포함된다.

## 화면 동작

검색어·태그·정렬·크기·커서를 URL에 저장하고 새로고침/뒤로 가기에서 복원한다. 검색(Enter 포함)·태그·정렬·크기 변경 시 첫 페이지로 이동한다. 늦게 도착한 이전 응답은 무시한다. 삭제 후 현재 페이지를 다시 읽고 비어 있으면 첫 페이지로 복귀한다. 오류 재시도/조건 초기화와 읽기 전용 예제 상태를 유지한다.

케이스 목록의 초기 로딩은 전체 케이스/파이프라인 목록을 읽지 않는다. 기존 내보내기 선택이 현재 페이지로 잘리지 않도록, 가져오기·내보내기 패널을 열 때만 별도로 프로젝트의 전체 케이스 선택 목록을 읽는다. 가져오기 저장 후 목록과 내보내기 선택을 갱신하며 현재 검색/태그 조건은 유지한다. 파이프라인 편집기와 케이스 편집기로 이동하면 기존 전체 선택 목록을 로딩한다.

부하 기준선 진단은 기존 전체 케이스 목록 프로토콜만 계측한다. 새 페이지 요청은 실제 페이지 handler에 위임하며 legacy 전체 조회로 대체하지 않는다. 기존 부하 수치/실패/unknown은 이번 기능의 측정값으로 변경하지 않는다.

## 검증 기록

- SQLite/API 집중9개, PostgreSQL2개, React/라우터/App 집중19개 통과. 세 정렬의 양방향 순회, 동률, 삽입/삭제, 한글/API 검색, 정확한 태그, Workspace/project/조건별 커서 거부, 비페이지 호환, public 필드만 반환, 요청 경합, 삭제 빈 페이지, 전체 export/pipeline 선택을 검사했다.
- 전체 frontend124개(30파일), production build, OpenAPI 생성 최신성·diff 검사 통과.
- 첫 전체 Python565개는 기존 P1 대역 요청의 HTTP query_params 누락으로1오류였다. 대역을 실제 요청 구조에 맞추고, P1 래퍼가 새 페이지 요청을 original handler로 위임하는 회귀를 추가했다. 관련 P1 9개 통과 후 최종 전체 Python566개(skip0,85.568초)가 통과했다.
- 실제 브라우저: 임시 인증·격리 DB에서 팀A 케이스45개20→20→5, 이전 이동·둘째 페이지 reload, 한글+auth4개, 내림/최신순·크기 변경·Enter 및 URL/back 복원 확인. 페이지 조작10회 동안 전체 케이스 조회0회를 확인했다.
- 실제 import/export: 검색 결과 밖의 case-44를 포함한 전체45개 export 선택과 cURL 생성, 새 케이스 preview/apply→최신순 첫 항목 표시, 삭제 후 목록/전체 export 갱신 확인. 삭제 클릭의 브라우저 CDP 응답 timeout이 있었으나 재클릭 없이 화면을 관찰해 완료와 제거된 항목을 확인했다.
- 실제 기존 흐름: case-44 편집기와 뒤로 가기, 파이프라인 편집기의 전체45개 선택 유지. 다른 프로젝트1개와 팀B3개/태그auth2개로 격리 확인. 이 브라우저 실행에서는 API 호출 성공이나 파이프라인 실행 성공을 새로 측정하지 않았다.
- 콘솔 오류/경고0개. [화면 증거](case-list-pagination-browser.jpg).
- 로그: `/tmp/case-pagination-focused-python.log`, `/tmp/case-pagination-focused-pg.log`, `/tmp/case-pagination-focused-web.log`, `/tmp/case-pagination-web-all.log`, `/tmp/case-pagination-build.log`, `/tmp/case-pagination-baseline-regression.log`, `/tmp/case-pagination-python-final.log`, `/tmp/case-pagination-generated-check.log`.
