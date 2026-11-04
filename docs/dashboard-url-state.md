# 실행 대시보드 URL 상태 복원

## URL 계약

`/dashboard?project=demo&days=30&status=failed&page=2&search=failed&run=<Run ID>&outcomes=contract`

- project는 기존 프로젝트 slug이며 API 조회에는 JSON reference로 복원한다.
- days는7/30/90, status는passed/failed/error/timeout/cancelled 또는 빈 값, page는1~1000000이다. 잘못된 값은 기본값7/전체/1로 읽는다. 검색어는 앞뒤 공백을 제거하고 최대200자를 사용한다.
- outcomes는 상세 항목 필터다. failures는 실패·오류·중단, contract는 유효한 OpenAPI 계약 실패를 선택한다. 기본 all은 URL에서 생략하며 잘못된 값과 run 없는 필터는 전체로 읽는다. 필터 변경은 목록 조건과 Run ID를 유지하고 추가 API 호출을 유발하지 않는다. 새로고침/back/forward에서 복원하며 다른 Run을 열거나 상세를 닫으면 초기화한다.
- run은 선택한 상세 Run ID다. 직접 진입·새로고침·뒤로/앞으로에서 상세를 다시 조회한다. 복원은 GET만 수행하며 실패 재실행 POST를 자동 제출하지 않는다.
- 상세 열기/닫기는 필터와 페이지를 유지한다. 프로젝트·기간·결과·검색 변경은 page1로 이동하고 상세를 닫는다. 페이지 변경도 다른 조건은 유지하며 상세를 닫는다. 검색은 Enter/검색 버튼으로 적용하며 미제출 입력은 URL에 저장하지 않는다.
- 기본값은 새 URL 생성 시 생략한다. 외부에서 잘못된 query로 진입하면 화면에서 정규화해 사용하되 최초 URL 자체를 강제로 다시 쓰지 않는다. backend-valid이지만 데이터 범위를 넘는 페이지는 기존 API대로 빈 목록이며 마지막 페이지로 자동 보정하지 않는다.

## 보존한 경계

프로젝트/기간은 KPI·추이의 집계 범위이며 결과/검색은 목록과 목록 건수에만 적용한다. 상세 조회는 목록 필터와 독립적이므로 선택한 Run이 현재 페이지에 없어도 서버가 허용하면 조회한다. URL은 권한이 아니며 Workspace는 서버 인증 context에서 결정한다. Workspace 전환은 기존 full navigation으로 `/projects`에 복귀해 이전 URL과 private 화면을 제거한다. 다른 Workspace/없는 run의 상세는 기존404/오류·재시도·닫기 흐름을 사용한다.

계약 통과/실패 요약, 명세 지문, 이전 요청 abort/늦은 응답 무시, 서버 소유 재실행 경로와 job 복원은 변경하지 않았다. 프로젝트/케이스/파이프라인/부하테스트 URL에 dashboard query가 섞이지 않는다.

## 검증 (2026-10-28)

- 전체 frontend151개(34파일,worker2), production build, diff 검사 통과. 독립 작성된 routed dashboard5개는 직접 URL/재마운트/상세/필터/페이지/popstate·지연 응답·없는 상세 복귀 및 POST0회를 확인했다. 추가 라우터2개는 한글·공백·%·+ 인코딩과 입력경계, auth1개는 상세 URL에서 Workspace 전환 시 이전 private 화면 제거를 검사했다.
- 관련 Python 이력10개 통과. 이번 작업에서 backend runtime/API/저장 구조를 변경하지 않았고 전체 Python을 새로 실행한 것으로 표기하지 않는다.
- 별도 read-only 에이전트가 실제 diff와 서버 입력 제한/Workspace 경계를 점검했고 actionable 결함은 없었다.
- 실제 브라우저: 격리 DB의 페이지 검증용 합성 이력28건과 실제 child runner 실행1건을 사용했다. project/demo·days30·failed·page2·search/failed·실제 Run ID를 포함한 URL 직접 진입에서 목록7개와 계약 상세 복원, reload, 상세 닫기/back/forward, 이전 페이지와 필터 보존, 기간 변경의 상세 초기화, 검색1건, missing Run404 후 조건 보존을 확인했다. 이력 수는29개로 유지되어 자동 재실행이 없었다. [화면](dashboard-url-restoration.jpg).
- 브라우저 fixture는 로컬 인증이다. Workspace 전환은 React 테스트와 기존 서버 격리 검증으로 확인했으며 이번에 운영 OIDC/SSO 브라우저 검증을 반복한 것은 아니다. 콘솔 오류/경고0개.
- 구현 테스트 실패 없음. 로그: /tmp/dashboard-url-web.log, /tmp/dashboard-url-build.log, /tmp/dashboard-url-history.log, /tmp/dashboard-route-agent-tests.log.

기존 contract-result-summary 미커밋 변경 위에서 이어간 작업이다. 현재 feature/contract-result-summary와 HEAD/develop8debdee를 유지하며 커밋·병합·푸시는 하지 않았다. 운영 배포·전체 부하 캠페인·기존 실패/unknown은 변경하지 않았다.

## 상세 필터 URL 확장 검증 (2026-11-04)

- outcomes=failures|contract의 직접 URL·reload/back/forward 복원, 잘못된 값/Run 없는 값 정규화, 다른 Run/닫기 초기화를 추가했다. 이전 화면 내 임시 상태 정책을 이 단계에서 확장한다.
- frontend155개(34파일)·build·diff 통과. 자동 회귀는 필터 변경 시 추가 API 호출 없음과 복원 시 POST0회를 확인했다. 실제 브라우저는 격리 합성 이력으로 직접 진입·reload·back/forward·다른 Run·닫기 및 기간 유지 확인, 콘솔 오류/경고0. [화면](execution-detail-filter-url.png).
- feature/execution-detail-filter-url, develop d43fc42 기준 미커밋. 백엔드 변경/전체 Python 재실행/원격 푸시 없음.
