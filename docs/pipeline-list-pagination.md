# 파이프라인 목록 페이지네이션·검색·정렬

## 범위

케이스 목록을 커밋49a842f·로컬 develop 병합e83778e로 반영한 뒤 `feature/pipeline-list-pagination`에서 구현했다. 새 변경은 미커밋이며 원격 푸시는 하지 않았다. 파이프라인 단계·실행 계약과 기존 편집기의 전체 케이스 선택을 보존한다.

## API 및 화면 계약

`GET /api/pipelines?project=demo.json&page_size=20&q=검색어&sort=reference_asc&cursor=...`

- 페이지 조회는 존재하는 Workspace 내 project reference가 필수다. page_size/q/sort/cursor를 모두 생략하면 기존 전체 조회 계약을 유지한다.
- 페이지 크기1~100(기본20), 화면10/20/50/100. q는 공백 제거 후 최대100자, name 또는 파일명/reference의 literal 부분 문자열이다. `%`, `_`, `!`는 wildcard가 아니다. ASCII 대소문자는 무시하며 그 밖에는 DB LOWER 규칙을 따른다.
- `reference_asc`, `reference_desc`, `created_desc`를 제공한다. 최신 생성일 동률은 reference 내림차순으로 구분한다. reference는 SQLite binary/PostgreSQL C collation을 사용한다.
- 커서는 문서 종류·Workspace·project·검색·정렬·페이지 크기에 묶이며 변경된 조건/잘못된 형식은400이다. SQL은 서버 인증 context와 membership을 사용한다.
- 응답 items와 nextCursor/previousCursor(경계에서 null), 빈 details만 반환한다. 단계 내용·인증/secret을 목록에 노출하지 않는다. DB에 keyset 조건과 LIMIT page_size+1을 적용한다.
- URL에 조회 조건을 보존해 reload/back으로 복원한다. 검색(Enter)/정렬/크기 변경은 첫 페이지, 삭제 후 빈 페이지도 첫 페이지로 복귀한다. 지연된 이전 응답은 무시하고 오류 재시도/조건 초기화를 제공한다.
- 목록의 초기 전체 case/pipeline 조회는 제거했다. 편집기로 이동할 때에는 기존 전체 선택 목록을 유지한다. 프로젝트 메타데이터가 아직 로딩 중이어도 URL project를 우선해 섹션 이동 시 프로젝트가 사라지지 않게 했다.
- keyset은 live 목록이며 동시 삽입/이름 변경 전체를 고정 snapshot으로 보장하지 않는다. 이름 부분검색의 대규모 SLO와 전체 부하 캠페인은 이번 범위가 아니다.

## 검증

- 목록 SQLite/API 집중12개, 화면/라우터/App 집중16개 통과. 파이프라인 전/후 순회·검색·세 정렬·입력 오류·중간 삭제/삽입·프로젝트/Workspace 격리·기존 전체조회·단계 내용 비노출을 포함한다. PostgreSQL 파이프라인 순회도 전체 테스트에서 통과했다.
- 최종 전체 Python570개(skip0,148.693초), frontend131개(31파일), production build, OpenAPI 생성 최신성·diff 검사 통과. frontend에는 로딩 중 섹션 이동 회귀를 추가했다.
- 실제 브라우저: 격리 DB/임시 OIDC로 팀A45개20→20→5, 이전 이동·둘째 페이지 reload, 한글 이름 검색7개·내림/최신순·크기·Enter 및 back 조건 복원 확인. 처음11회 목록 요청은 모두 페이지 크기 제한이 있었으며 편집기 진입부터 기존 전체 case 선택을 조회했다.
- 기존 편집기에서 케이스 선택·필수 단계 이름 입력·단계 추가·저장 후 뒤로 가기를 확인했다. 최초 단계 이름을 비운 저장은 정상 거부됐으며 값을 입력한 뒤 저장 성공했다. 파이프라인 실행 성공을 이번 브라우저에서 새로 측정한 것은 아니다.
- 다른 프로젝트는1개만 조회되고 그 테스트 항목 삭제 후0개/안내 표시를 확인했다. 삭제 클릭의 CDP 응답 지연은 재클릭 없이 최종 화면으로 완료를 확인했다. 팀B는3개이고 검색 결과1개로 격리됐다. 콘솔 오류/경고0개.
- 초기 브라우저 조작에서 프로젝트 로딩 중 섹션 이동의 선택값 경합을 발견해 URL project 우선으로 수정하고 회귀 테스트를 추가했다.
- [화면 증거](pipeline-list-pagination-browser.jpg). 로그 `/tmp/pipeline-focused-python.log`, `/tmp/pipeline-focused-web.log`, `/tmp/pipeline-python-all.log`, `/tmp/pipeline-web-final.log`, `/tmp/pipeline-build.log`, `/tmp/pipeline-generated-check.log`.

## 2026-10-23 복구 재검증

임시 경로의 파일 소실 후 작업 기록과 Git 기준으로 소스/테스트를 복구했다. Python570개·frontend131개/build를 다시 통과했다. 화면 PNG는 오늘 격리 로컬모드에서20개 페이지·다음/reload·검색7개를 재확인한 이미지로 교체했다. 과거 OIDC 및 Workspace 실브라우저 검증과 구분한다.
