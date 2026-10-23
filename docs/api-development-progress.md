# API 개발 기능 진행 기록

## 저장 케이스 계약검증 커밋·병합 준비 (2026-10-24)

- 사용자 승인으로 저장 케이스 계약검증을 커밋하고 로컬 develop에 병합한다. 원격 푸시 없음.
- 현재 diff와 기존 전체 Python597개/build/생성 기록 확인. 집중6개·전체 UI138개(worker2) 재검증 통과. 자동 권한 검토가 처음 시간초과되어 미실행을 확인하고 같은 명령을 한 번 재요청해 성공했다.
- 다음은 OBS-1/OAS-2 실행 결과·이력의 계약 요약 표시다. 새 브랜치에 미커밋으로 남긴다.

## 저장 케이스 OpenAPI 계약검증 완료 (2026-10-24)

- 구현: contract_validation opt-in 설정·편집 UI·API 저장/복원, Workspace별 프로젝트 명세의 케이스 단위 snapshot, 웹/CLI 공통 runner와 pipeline의 추가 응답 계약 판정을 연결했다. 기존 status/body/assertion/시간 제한은 보존했다.
- 경계: malformed 설정·명세/operation은 대상 호출 전 configuration_error, 응답 불일치는 contract_failed. JSON/JUnit·이력에는 valid/issueCount/documentDigest만 추가하며 원문·token은 추가 저장하지 않는다. 재시도는 동일 명세snapshot이고 pipeline 전체 원자snapshot은 비범위다.
- 검증: 최종 전체 Python597개(skip0,194.581초), 집중6개(실HTTP·CLI·pipeline·Workspace/API), frontend138개(worker2), production build·생성 최신성·diff 검사 통과. 이전596개 및597개 실행 기록도 보존하고 마지막 malformed docs_file guard 보완 후 전체597개를 다시 통과했다.
- 실제 브라우저: opt-out HTTP200은 기존 통과, opt-in 저장/reload 후 같은 body는 schema_type/contract_failed, 저장 케이스를 쓰는 pipeline도 실패. 정상 fixture URL로 저장 후 pipeline 성공. 두 job result의 같은 명세digest·valid false/true·issueCount1/0 및 원문 비노출 확인. 콘솔 오류/경고0.
- 실패/조치: 최초 테스트 fixture의 중괄호 오류를 검증된 helper 사용으로 해결했다. 저장 완료 안내가 기존 명세 재조회 안내로 바뀌어 browser wait가 실패했으나 reload/실행으로 저장을 확인했다. 커밋 전 기존 CaseList 테스트1개의 기본 병렬 실패는 단독5개/worker2 전체135개 통과로 구분했고 단언은 변경하지 않았다.
- 자료: [설정/판정/검증](saved-case-contract-validation.md), [실행 화면](saved-case-contract-result.jpg). 로그 /tmp/saved-contract-*.log. 임시 브라우저와 검증 서버 정상 종료.
- Git: server 변수·상대URL 커밋0de1fca 및 develop 병합a51c176 완료. 새 feature/saved-case-contract-validation은 a51c176 기준 미커밋/미병합이며 원격 푸시·원본 worktree 변경 없음. 배포·운영 공급자·전체 LT 및 기존 부하 실패/unknown은 별도다.

## 저장 케이스 OpenAPI 계약검증 시작 (2026-10-24)

- server 설정 커밋0de1fca·develop 병합a51c176 완료 후 feature/saved-case-contract-validation 생성. 이번 새 변경은 미커밋/미푸시다.
- 범위: 케이스 contract_validation opt-in 설정과 편집 UI, 저장된 프로젝트 명세의 실행당 snapshot, CLI/웹 공통 runner 응답 계약 판정. 같은 케이스를 실행하는 파이프라인에도 적용한다. 기존 status/body/assertion은 계속 검사한다.
- 실패 경계: 잘못된 명세/설정/operation은 호출 전에 configuration_error, 실제 응답 계약 불일치는 failed. 보고서는 valid·issueCount·명세digest만 남기며 body·token·변수값을 추가 저장하지 않는다.
- 검증: 단위/실HTTP·CLI·pipeline·재시도 snapshot·설정API/Workspace 경계·보고서 비노출·UI 저장/복원·전체 회귀/build/생성 및 브라우저.

## Server 설정 로컬 develop 병합 완료 (2026-10-24)

- 커밋 `0de1fcabc10a0f46324efd8bd2668313806ce1b0`를 충돌 없이 develop에 병합했다. 이 기록만 병합 커밋에 추가했으며 제품 코드가 기능 커밋과 동일하다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## Server 설정 커밋·병합 준비 (2026-10-24)

- serverVariables와 contractDocumentUrl 변경을 사용자 승인으로 커밋·로컬 develop 병합한다. 원격 develop fb75a46 확인, 푸시 없음.
- 계약/실HTTP 집중40개 재실행 및 diff 검사 통과. frontend 기본 병렬 실행은 기존 CaseList 삭제 후 첫 페이지 테스트1개 실패(134통과)였고 단독5개 및 worker2 전체135개는 통과했다. 단언/대기제한을 바꾸지 않았고 첫 실패 이력을 보존한다. 기존 전체 Python591개·build·생성검사 통과 기록도 확인했다.
- 다음 단계는 저장 케이스의 opt-in OpenAPI 응답 계약검증이며 공통 runner를 통해 파이프라인에도 적용한다. 새 단계는 미커밋으로 유지한다.

## OAS-2 상대 server 경로 해석 완료 (2026-10-24)

- 빠른 호출의 선택적 contractDocumentUrl UI/API를 추가했다. 변수 치환 뒤 문서 위치 기준 상대/상위 경로를 해석하며 metadata URL 다운로드와 실제 요청 URL 변경은 하지 않는다. 기준이 없으면 기존 상대 경로 거부를 유지한다.
- 검증: 계약/API 집중40개·실HTTP, 전체 Python591개(skip0,188.541초), frontend135개(31파일), production build·생성 최신성·diff 통과. 기준 입력경계·scope·끝 슬래시·변수 결합·alias 우회 금지·값 비노출·기준 URL 미접속을 포함한다.
- 실제 브라우저: 기준 없는 상대 server는 실패, 기준+default v1 및 명시값v2 통과. 잘못된 기준/file URL 거부 후에도 대상 카운터3회 그대로이고 문서 경로 조회0건. 프로젝트 변경 초기화·콘솔 오류/경고0 확인. [상세 계약](openapi-contract-validation.md), [화면](openapi-relative-server-browser.jpg).
- 첫 공식 명세 조회 연결 실패는 재조회로 해결했다. 구현 테스트 실패 없음. 다중 외부 문서별 기준 추적/저장 케이스 자동 계약검증·운영 배포·전체 부하는 별도이며 과거 실패/unknown은 유지한다.
- 기존 serverVariables 미커밋 작업을 보존하고 feature/openapi-server-variables에서 이어갔다. HEAD/develop d5dd592 유지, 이번 커밋·병합·푸시 없음. 원본 worktree 변경 없음. 브라우저 탭은 종료했고 임시 서버도 정리한다.

## OAS-2 상대 server 경로 해석 시작 (2026-10-24)

- 다음 단계: 빠른 호출의 선택적 contractDocumentUrl로 문서 위치에 상대적인 server URL을 해석한다. 기준 URL은 다운로드하지 않고 실제 호출 URL도 바꾸지 않는다. 원격 참조/명세 가져오기·저장 케이스 자동 검증은 비범위다.
- 기존 feature/openapi-server-variables의 미커밋 명시값 변경을 보존하고 같은 OAS server 설정 작업으로 이어간다. 커밋·병합·푸시 없음.
- 기준: OpenAPI Server Object의 문서 위치 기준 상대 URL 규칙(https://spec.openapis.org/oas/v3.1.0.html#server-object). 변수 치환 후 RFC3986 URL 해석, 명시적 기준이 있으면 project base alias로 우회하지 않는다. 기준 URL이 없으면 이전의 상대 경로 거부 정책을 유지한다.
- 검증 계획: 3.0/3.1·상대/상위/루트/절대 경로·server 우선순위·변수·기준 입력 제한·비노출·실HTTP·UI·전체 회귀/build 및 실제 브라우저.

## OAS-2 server 변수 명시값 완료 (2026-10-24)

- server 매칭 커밋b47709b·로컬 develop 병합d5dd592 완료. 새 feature/openapi-server-variables에서 빠른 호출 serverVariables map 및 JSON 입력 UI를 구현했다. 실제 URL은 변경하지 않고 응답 경로 매칭에만 적용한다.
- validateContract=true에서만 지정한다. 최대32개 문자열, 이름1~128자·값512자 이하이며 제어문자는 거부한다. 미지정 변수는 default, 빈 map도 기존 동작이다. 사용되지 않는 변수·enum 위반·매칭 실패·형식 오류는 입력값 없는400으로 대상 호출 전에 차단한다. 명시값 사용 시 project base alias로 우회하지 않는다.
- UI에서 검증 해제 시 전송하지 않고 프로젝트/환경 변경 시 초기화한다. 프로젝트/케이스/이력에 값을 추가 저장하지 않는다. 소유권·인증 정책은 기존대로 적용하며 일반 상대 server 해석과 저장 케이스 자동 계약검증은 후속이다.
- 검증: 계약/API 집중34개(실제 loopback HTTP 포함), 전체 Python585개(skip0,104.414초), frontend133개(31파일), production build·생성 최신성·diff 검사 통과. 부분 치환·변수 scope·모호함·값 비노출·입력경계·UI 초기화를 포함한다.
- 실제 브라우저: 격리 로컬 fixture에서 default v1 및 명시값v2의 HTTP200/계약 통과, v3/API400·잘못된JSON/UI 차단을 확인했다. 대상 카운터는 성공2회 이후 증가하지 않았다. 프로젝트 전환 초기화 및 콘솔 오류/경고0 확인. [화면](openapi-server-variables-browser.jpg).
- 실패/보완: 모호함 fixture가 실제 중복이 아닌 v1 기본값을 사용해1개 실패했고 v2로 바로잡았다. 신규 UI2개 label 조회 실패는 textarea의 명시적 접근성 이름으로 수정했다. npm root 실행은 web/에서 재실행했다. 모두 수정 후 위 검증을 통과했다. 문서 쓰기 자동검토 시간초과는 같은 작업을 재요청했다.
- 로그: /tmp/server-vars-focused-python.log, /tmp/server-vars-python-all.log, /tmp/server-vars-web-all.log, /tmp/server-vars-build.log, /tmp/server-vars-generated-check.log.
- 반영: 새 기능은 d5dd592 기준 미커밋/미병합, 원격 푸시 및 원본 worktree 변경 없음. 운영 배포·전체 부하 캠페인·기존 실패/unknown은 변경하지 않는다.

## OAS-2 server 변수 명시값 시작 (2026-10-24)

- server 매칭 커밋b47709b·develop 병합d5dd592 완료. 새 feature/openapi-server-variables에서 명시값 UI/API를 개발하며 새 변경은 미커밋/미푸시로 남긴다.
- 범위: 빠른 호출 validateContract의 선택적 serverVariables 문자열 map, 실제 URL 자동 변경 없이 effective server 매칭에만 사용. 미지정 변수는 default, enum 위반/사용되지 않는 변수/형식 오류는 값 비노출 오류로 거부한다. 기본값 기존 호출은 호환 유지한다.
- 검증: 분리된 operation/server의 변수 scope, 입력경계·원문 비노출·실HTTP 및 API 호출 전 차단, UI 전송·프로젝트/환경 변경 초기화, 전체 회귀/build/생성 및 브라우저 검증.

## OAS-2 server 매칭 로컬 병합 완료 (2026-10-24)

- 커밋 `b47709b420713ab99d60269b7ec767fb92d82f2b`를 충돌 없이 로컬 develop에 병합했다. 완료 문서만 추가했으며 제품 코드는 검증한 기능 커밋과 같다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## OAS-2 server 매칭 커밋·병합 준비 (2026-10-24)

- 사용자 승인으로 server 매칭 변경을 커밋하고 로컬 develop에 병합한다. 중단된 요청에서 추가 Git 반영은 없었다. 계약/실HTTP 집중28개 재검증·diff 검사 통과, 기존 전체579개 기록 확인. 원격 develop fb75a46 확인, 푸시 없음.
- 다음은 빠른 호출의 server 변수 명시값 UI/API이며 호출 URL 자동 변경 없이 매칭에 적용한다. 새 단계 변경은 별도 기능 브랜치에 미커밋으로 유지한다.

## OAS-2 server 경로 매칭 보완 완료 (2026-10-23)

- 변경: operation→path→root 서버 우선순위, 변수 default 치환, operation별 prefix·경계 처리, 빈 override·모호함·해석 불가 서버의 명시적 실패를 구현했다. project base alias는 명시적 하위 override가 없을 때만 적용한다.
- 검증: 집중28개, 실제 loopback HTTP 호출, 전체 Python579개(skip0,83.573초), 생성 최신성·diff 통과. React 변경 없음; 복구 시 frontend131개/build 통과. 실제 브라우저에서 JSON HTTP200의 올바른 경로 통과/상위 경로 실패와 콘솔 오류0을 확인했다.
- 환경 이력: tmp 원본 소실을 Git 기준 및 기록에서 복구·지속 경로로 이전한 뒤 파이프라인 재검증570개/131개와 브라우저 확인을 완료했다. 기록 스크립트 직접 replay는 자동 검토에 거절돼 scratch 결과와 SHA를 확인한 patch 적용으로 해결했다. 임시 OAS fixture의 구문 및 route 순서는 제품 코드와 별개로 수정하고 재검증했다.
- 범위: 변수 default 외 사용자 선택, 문서 위치 기반 상대 server, 저장 케이스 자동 계약검증, 전체 부하/배포는 남아 있다. 과거 부하 실패/unknown을 바꾸지 않는다. [상세 계약/검증](openapi-contract-validation.md).
- Git: 파이프라인 커밋9d63751·develop 병합f6b890f 완료. 현재 feature/openapi-server-matching은 f6b890f 기준 미커밋이다. 원격 푸시·원본 저장소 변경 없음. 작업 경로는 `/Users/kwondaehoon/Desktop/Project/api-develop-studio-worktrees/pipeline-list`이다.

## OAS-2 server 경로 매칭 보완 시작 (2026-10-23)

- 기준: 파이프라인 커밋9d63751·로컬 develop 병합f6b890f에서 feature/openapi-server-matching 생성. 새 변경은 미커밋, 원격 푸시 없음.
- 범위: 빠른 호출 응답 계약 검사에서 operation→path→root server 우선순위 및 선언된 변수 기본값 치환, prefix 경계·모호함 차단. project base URL alias는 명시적 operation/path override가 없는 경우에만 사용한다.
- 비범위: 사용자 지정 server 변수 선택 UI/API, 문서 위치 기준 상대 URL 해석, 원격 명세 호출, 저장 케이스/파이프라인 자동 계약검증. 현재 함수에 문서 위치가 없으므로 `/`로 시작하지 않는 상대 server는 안전하게 실패한다. host/origin 검증과 실제 호출 소유권 정책은 별도다.
- 계획: OpenAPI3.0/3.1·각 override/default/모호함/민감값 비노출 fixture와 실제 HTTP 빠른 호출 계약 검사, 전체 Python 회귀를 수행한다. [명세](https://spec.openapis.org/oas/v3.1.0#operation-object)를 기준으로 한다.

## 파이프라인 로컬 develop 병합 완료 (2026-10-23)

- 통합 커밋 `9d63751afa29c64da13d6839a31d4218ccedc256`를 충돌 없이 로컬 develop에 병합했다. 이 기록은 병합 커밋에 포함한다. 제품 코드는 검증한 통합 커밋과 동일하다. 원격 푸시·원본 worktree 변경·브랜치 삭제 없음.

## 파이프라인 복구·커밋 전 재검증 (2026-10-23)

- 이전 /tmp worktree의 연결 파일과 소스가 없어져 Git index의 기준508개 파일을 누락 위치에만 복구하고 지속 경로 `/Users/kwondaehoon/Desktop/Project/api-develop-studio-worktrees/pipeline-list`로 이동했다. 원본 저장소의 미커밋 P1 변경은 건드리지 않았다.
- 자동 승인 검토가 기록 스크립트 직접 재실행을 거절했다. 별도 scratch에서 이전 편집 결과를 재구성하고 대상 SHA/깨끗한 기준/diff를 확인한17개 파일 patch만 적용했다. 생성 코드는 원본 OpenAPI로 재생성했다. 이전 PNG는 소실되어 새 로컬모드/임시 DB 화면 증거로 교체했다.
- 새 검증: Python570개(skip0,90.170초), frontend131개·production build 통과. 브라우저에서45개 중 첫20개·다음 페이지·reload 및 검색7개 확인. 과거 OIDC/두 Workspace 검증은10월16일 기록이며 오늘 다시 실행한 것으로 표시하지 않는다.
- 사용자 승인에 따라 파이프라인을 커밋하고 develop에 병합한다. 원격 푸시 없음. 다음 OAS-2 server 경로 매칭 보완은 새 브랜치에 미커밋으로 남긴다.

## 파이프라인 목록 개발·검증 완료 (2026-10-16)

- 구현: 프로젝트/Workspace 내 bounded keyset 페이지, 이름/파일명 검색, 파일명 양방향·최신 생성순·페이지 크기·URL reload/back 복원. 단계/secret은 목록에 반환하지 않고 기존 편집·실행/전체 케이스 선택을 보존했다.
- 보완: 프로젝트 로딩 중 빠른 섹션 이동에서 아직 갱신되지 않은 선택 상태를 사용할 수 있어 URL project를 우선하도록 수정하고 App 회귀를 추가했다.
- 검증: 최종 Python570개(skip0,148.693초, PostgreSQL 포함), frontend131개(31파일), production build, 생성 최신성·diff 검사 통과. 집중 목록12개·화면16개 통과.
- 실제 브라우저: 팀A45개20→20→5·이전/reload·검색7개·정렬/크기/Enter/back, 기존 편집기 케이스 선택·단계 저장, 다른 프로젝트1개와 삭제 후0개, 팀B3개/검색1개 격리 확인. 초기11개 요청은 모두 bounded 목록이며 콘솔 오류/경고0개. 단계 이름 없는 저장은 정상 거부 후 이름을 입력해 저장했고 삭제 CDP 지연은 재클릭 없이 완료 화면으로 확인했다.
- 자료: [계약·검증](pipeline-list-pagination.md), [화면](pipeline-list-pagination-browser.jpg). 실제 파이프라인 실행 성공·부하 캠페인·운영 배포를 이번 검증으로 주장하지 않는다. 기존 부하 실패/unknown은 보존한다.
- 반영: 케이스 커밋49a842f·develop 병합e83778e 완료. 새 feature/pipeline-list-pagination은 e83778e 기준 미커밋이며 커밋/병합·원격 푸시 없음. 원본 worktree 보존. 검증용 인증 로그아웃·탭 종료 후 임시 서버를 정리한다.

## 파이프라인 목록 페이지네이션·검색·정렬 시작 (2026-10-16)

- 케이스 목록 커밋49a842f·로컬 develop 병합e83778e 완료. 새 feature/pipeline-list-pagination은 이 develop 기준이며 새 변경은 미커밋으로 유지한다. 원격 푸시 없음.
- 범위: 프로젝트 내 파이프라인 DB keyset 페이지, 이름/파일명 검색, 파일명 양방향·최신 생성순, URL 페이지 크기/커서 및 reload/back. 기존 편집·실행·케이스 선택·예제 읽기전용은 유지한다.
- 계획: 공통 조회에 pipelines scope 추가, 목록 초기 전체 case/pipeline 요청 제거, 선택 화면으로 이동할 때 기존 목록 유지. SQLite/PostgreSQL/API·화면 회귀, 전체 테스트/build/생성, 실제 브라우저 검증을 수행한다.

## 케이스 목록 로컬 develop 병합 완료 (2026-10-16)

- 케이스 목록 커밋 `49a842faabf160ce1df69b9f19c4b3912ff69299`를 로컬 develop에 충돌 없이 병합했다. 완료 기록은 병합 커밋에 포함한다. 검증 코드와 동일하며 문서만 추가했다.
- 원격 푸시·원본 worktree 변경·브랜치 삭제 없음. 다음 파이프라인 목록은 이 기준에서 새 기능 브랜치로 진행한다.

## 케이스 목록 커밋·병합 준비 (2026-10-16)

- 사용자 승인으로 케이스 목록 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시 없음.
- 현재 변경과 기존 전체 Python566개/build/생성 검증 기록을 확인하고 목록 집중9개·frontend전체124개·diff 검사를 다시 통과했다. 원격 develop은 fb75a46이다.
- 다음은 프로젝트 내 파이프라인 목록 페이지네이션·검색·정렬이며 새 브랜치에 미커밋으로 유지한다.

## API 케이스 목록 검증 완료 (2026-10-15)

- 구현: 선택 프로젝트/Workspace 내 DB keyset 페이지, 이름/API 검색, 정확한 태그 필터, 파일명 양방향·최신생성순, 페이지 크기, URL reload/back 복원을 구현했다. 프로젝트와 공통인 조회만 공유하고 기존 project cursor 형식은 보존했다.
- 기존 흐름 보존: 케이스 목록 초기 전체 조회 제거, import/export 패널을 열 때 전체 export 후보 지연 조회, 저장/삭제 후 페이지와 후보 갱신, 파이프라인 편집기 전체 케이스 선택 유지. 예제 읽기 전용·기존 케이스 경로/실행 계약 유지.
- 최종 검증: Python566개(skip0,85.568초), frontend124개(30파일), production build, 생성 최신성·diff 검사 통과. 집중 SQLite/API9개·PostgreSQL2개·화면19개·P1호환9개 통과.
- 실패/보완: 첫 전체 Python565개 중 P1 테스트1개는 대역 요청의 query_params 누락으로 오류였다. 대역 구조를 맞추고 진단 래퍼의 새 페이지 handler 위임을 추가한 뒤 전체566개 통과. 기존 부하 계측 결과는 바꾸지 않는다.
- 실제 브라우저: 케이스45개20→20→5·이전/reload·한글+auth4개·정렬/크기/Enter/back, 전체45개 export/cURL, preview/apply 후 최신순 추가와 삭제 갱신, 편집기 진입/back, pipeline45개 선택, 타 프로젝트1개/팀B3개·auth2개 격리 확인. 페이지조작10회 동안 전체 케이스 조회0회. 삭제 클릭 CDP timeout 후 재클릭 없이 완료 상태를 확인했고 콘솔 오류/경고0개였다.
- 자료: [계약·검증 기록](case-list-pagination.md), [화면 증거](case-list-pagination-browser.jpg). 로그 `/tmp/case-pagination-*.log`. 임시 인증 로그아웃·탭 종료·검증 서버 정리 완료.
- Git: 프로젝트 목록 커밋8939e2e 및 develop 병합ff6f18c 완료. 새 `feature/case-list-pagination`은 develop ff6f18c 기준 미커밋 변경이다. 새 변경 커밋/병합·전체 원격 푸시·원본 브랜치 삭제는 수행하지 않았다.

## API 케이스 목록 페이지네이션·검색·정렬 시작 (2026-10-15)

- 기준: 프로젝트 목록 병합 `ff6f18c`의 로컬 develop에서 `feature/case-list-pagination` 생성. 프로젝트 목록 커밋8939e2e·병합ff6f18c 완료, 원격 푸시 없음. 새 단계는 미커밋으로 유지한다.
- 범위: 선택 프로젝트 내 케이스 DB keyset 페이지, 케이스/API 이름 검색, 정확한 태그 필터, 케이스 파일명 양방향/최신생성순 정렬, URL 새로고침/뒤로가기 복원. 기존 실행·pipeline 선택·import/export 계약을 보존한다.
- 구현 계획: 프로젝트와 공통인 bounded 조회를 공유하되 case cursor는 Workspace·project·조건에 묶는다. 케이스 화면의 초기 전체 조회를 제거하고 import/export를 열 때에만 기존 전체 export 선택 목록을 읽는다. 파이프라인 편집기 전체 선택 목록은 유지한다.
- 검증 계획: SQLite/PostgreSQL 순회·동률·변경·격리·입력경계, React 조건/응답경합/삭제/import/export, 전체 회귀/build/생성 최신성 및 실제 브라우저를 확인한다.

## 프로젝트 목록 로컬 develop 병합 완료 (2026-10-15)

- 프로젝트 목록 커밋 `8939e2ef580913116fad4cc8ff385872f3b77bde`를 로컬 develop에 충돌 없이 병합했다. 이 기록은 병합 커밋에 포함한다. 검증한 제품 코드와 병합 결과는 동일하며 완료 문서만 추가했다.
- 원격 푸시·기존 원본 worktree 수정·브랜치 삭제 없음. 다음 API 케이스 목록 개발은 이 병합 이후 새 기능 브랜치에서 진행한다.

## 프로젝트 목록 커밋·develop 병합 준비 (2026-10-15)

- 사용자 승인으로 프로젝트 목록 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 제외한다.
- 현재 HEAD/develop `407983a`, 원격 develop `fb75a46` 확인. 변경 내용·diff 검사·기존 전체 Python560개/build/생성 검사 로그를 확인했으며 커밋 직전 프로젝트 집중5개와 frontend 전체117개를 재실행해 통과했다.
- 이어서 API 케이스 목록의 페이지·검색·태그·정렬을 새 feature 브랜치에서 개발한다. 새 단계 변경은 미커밋 상태로 남긴다.

## 프로젝트 목록 페이지네이션·검색·정렬 검증 완료 (2026-10-15)

- 구현: `feature/project-list-pagination`에서 프로젝트 전용 bounded DB 조회, 이름/파일명 검색, 파일명 오름/내림·최신생성순, Workspace/조회조건별 양방향 커서 및 URL 복원을 구현했다. 기존 전체 조회·편집기 선택·케이스/파이프라인 API는 호환 유지한다.
- 검증: SQLite/HTTP 집중5개 및 PostgreSQL 집중1개, 전체 Python560개(skip0,121.865초), 최종 전체 frontend117개(29파일) 및 build, 생성 최신성·diff 검사 통과.
- 브라우저: 팀A46개20→20→6 페이지·이전 이동·reload, 한글 검색7개, 내림/최신순·크기, Enter/빈 결과, 프로젝트 진입 후 back, 팀B4개/검색1개 격리 확인. 최종 reload와 콘솔 오류/경고0도 확인했다. 초기 프로젝트 화면은 전체 조회를 하지 않았다.
- 실패/보완: 첫 신규 화면 테스트3개는 DOM의 합쳐진 카드 accessible name을 공백 구분으로 가정해 실패했다. 명시된 수정 버튼 aria-label로 검증 대상을 고쳐 집중11개를 통과했다. 테스트 파일 작성의 첫 상대경로 오류는 실제 web/ 디렉터리에 맞춰 해소했다. 화면 검증에서 필드/페이지 버튼 스타일과 삭제 안내 보존을 보완했다. 최종 흐름 점검에서 프로젝트 목록의 전체 조회 제거 후 대시보드 selector가 비는 경로를 발견해 탭 이동 시 필요한 공통 목록을 로딩하고 App 회귀1개를 추가했다. 최종 브라우저에서도 대시보드47개 선택 항목 및 back 후 프로젝트20개를 확인했다.
- 경계: keyset은 live 목록이며 동시 변경 전체 snapshot이나 대규모 검색 SLO를 보장하지 않는다. 기존 selector 전체 조회 확장과 전체 부하 캠페인은 별도다.
- 정리: 임시 인증 로그아웃·브라우저 탭 종료·테스트 서버 정상 종료. 작업 경로 `/tmp/api-studio-develop-20261015`에서 미커밋 상태로 유지한다.
- 자료: [API/화면 계약과 검증](project-list-pagination.md), [브라우저 증거](project-list-pagination-browser.jpg). 기준 develop/HEAD `407983aaeba9dbc28db9f6a332040e4e17b18417` 유지. 커밋·푸시·병합 없음.

## 프로젝트 목록 페이지네이션·검색·정렬 시작 (2026-10-15)

- 기준: 로컬 develop `407983a`에서 `feature/project-list-pagination` 생성. 기존 원본 worktree 보존, 커밋·푸시 없음.
- 계획: 프로젝트 화면만 bounded DB keyset 조회로 전환하고 이름/파일명 검색·파일명 양방향/최신생성순 정렬·페이지 크기·이전/다음 커서를 URL에 저장한다. 기존 비페이지 프로젝트 선택 API와 케이스/파이프라인 목록은 유지한다.
- 검증 기준: SQLite/PostgreSQL Workspace 격리·조건별 커서·순회 중복/누락·잘못된 입력, React 비동기 응답 경합·URL 새로고침/뒤로가기, production build·생성 최신성 및 실제 브라우저 검증.
- 변경: DB에 LIMIT을 적용하고 페이지에 필요한 public name/base_url만 응답한다. 조회 cursor는 workspace·검색·정렬·크기·예제 표시 조건에 묶는다. 최신순은 변경 가능한 수정일 대신 생성일과 reference를 사용한다.

## 통합 커밋·로컬 develop 병합 완료 (2026-10-15)

- 사용자 승인으로 통합 커밋 `2c54a41b406bf90c6a9da039011ca3cc79148a3d`를 만들고 로컬 `develop`에 `--no-ff` 병합했다. 이 완료 기록은 병합 커밋에 포함한다. 원격 푸시는 수행하지 않았다.
- 검증: 커밋 전 Python 554개(skip 0, 137.740초), OAuth 집중5개·frontend111개·production build·생성 최신성·diff 검사 통과. 병합은 충돌 없고 검증한 통합 커밋과 제품 코드/테스트가 동일하며 완료 기록 문서만 추가했다.
- 보존: 작업 시작 당시 원본521개 파일 SHA와 대조해 변경0개를 확인했다. 통합 기능 브랜치와 원본 worktree는 모두 보존했다.
- checkout: 통합은 기존 roadmap-integration 경로, 로컬 develop은 `/tmp/api-studio-develop-20261015`이다. 기존 원본 저장소의 미커밋 변경은 그대로 유지했다.
- 범위: 이 기록은 로컬 Git 반영이다. 운영 인증/배포·전체 LT 캠페인·공통 pagination 등 잔여 개발 및 2026-10-13 브라우저 검증 범위를 변경하지 않는다.

## 통합 커밋 전 검증 완료 (2026-10-15)

- 전체 Python 554개(skip 0, 137.74초), OAuth 집중 5개, frontend 전체 111개, production build, OpenAPI 생성 최신성 및 diff 검사 통과.
- 실패/보완: 최초 frontend 110개 통과·1개 실패는 OAuth 초기 조회 중 비활성 연결 버튼을 클릭한 테스트 경합이었다. `OAuthProfileStatus.test.jsx`에서 버튼 활성화를 기다린 뒤 클릭하도록 보완했다. 관련 및 전체 재검증 통과, runtime 코드 변경 없음.
- 사용자 승인 범위는 통합 커밋과 로컬 develop 병합이며 원격 푸시 및 원본 브랜치 삭제는 제외한다. 실제 브라우저 증거는 2026-10-13 기록을 유지한다.

## 통합 커밋·로컬 develop 병합 시작 (2026-10-15)

- 승인: 사용자 요청으로 통합 변경을 커밋하고 로컬 develop에 병합한다. 원격 푸시는 수행하지 않는다.
- 기준 확인: 통합 HEAD·로컬 develop·읽기 전용 조회한 원격 develop이 모두 `fb75a467fba8c430f6da4a8e215d1c0f3b995470`이다. 기존 통합 변경 307개 파일과 원본 521개 파일의 현재 SHA를 확인했다.
- 검증: 현재 통합 소스의 전체 Python, frontend test/build, 생성 코드 최신성을 재실행 중이다. 기존 브라우저 증거는 2026-10-13 실행 기록이며 이번에 재실행한 것으로 표기하지 않는다.
- 병합 방식: 원본 worktree를 전환하거나 초기화하지 않고 별도 develop checkout에서 병합한다. 모든 원본 변경과 기능 브랜치를 보존한다.

## 실제 브라우저 통합 검증 및 최종 회귀 완료 (2026-10-13)

- 브라우저: 같은 5182 주소의 정상 in-app browser에서 임시 OIDC 로그인·로그아웃·재로그인 및 팀 A/B 전환을 확인했다. 과거 도구 차단은 재현되지 않았으며 사용자 설정 오류로 단정하지 않는다. 우회 없음.
- 가져오기: 팀 A에서 로컬 테스트 공급자의 공개 metadata GET을 cURL preview→항목 저장→새로고침 후 케이스 1개 유지로 확인했다. 팀 B에는 케이스 0개였다.
- 릴리스: `1.0.0-browser` 초안→발행(release revision 2)→고정 원본 조회를 수행했다. 포털 명세 revision 1과 source digest가 같고 뒤로 가기·새로고침·재로그인 후 보존됐다. 팀 B에는 발행 릴리스 및 팀 A SDK job이 없었다.
- 실제 다운로드: 포털 Python 릴리스 ZIP 32,707 bytes(SHA `602bcee3e7a59bfa78e6d58c93150dd021935c7cc24f8239c5703bb002e56bfc`), 일반 TypeScript ZIP 9,619 bytes(SHA `3feb07d9304a4356925049d345b7a1a4268da356b9dd2cc147978767e8952ba8`)를 브라우저 download 완료 이벤트와 Downloads 파일로 확인했다. 두 ZIP CRC 통과, 릴리스 manifest의 revision/source digest/릴리스 ID 일치. 일반 SDK 동일 job ID의 새로고침 복원도 통과.
- 실행 복원 경계: 가져온 케이스의 Run ID `cdfeef4b-b047-4294-9da4-0ce09b9d0a66`과 terminal 오류가 새로고침 후 복원됐다. fixture는 대상 소유권 증명이 없어 `configuration_error`로 정상 차단됐다. 이를 성공 API 실행으로 표시하지 않으며 앞선 실제 HTTP 성공 증거와 구분한다.
- 최종 검증: shutdown 수정 후 현재 통합 상태에서 **Python 554개(skip 0, 142.777초)**, 프런트엔드 **111개/27파일**, production build, OpenAPI 생성 최신성, `git diff --check` 통과. 과거 552개 결과는 수정 전 이력으로 보존했다. 로그는 `/tmp/roadmap-integration-final-{python,web,build,generated}.log`.
- 원본 확인: 이전 manifest 521개 중 P1 진행 문서 2개만 앞선 사용자 요청의 재검증 기록으로 달랐다. 이번 통합 계속 작업에서는 원본 worktree를 수정하지 않았다. 기존 통합 코드는 보존했고 발견된 제품 결함 및 제품 코드 수정 없음.
- 정리/반영: 임시 계정 로그아웃·브라우저 탭 종료·검증 서버 정상 종료(exit 0). 증거/계획/두 진행 문서와 스크린샷만 갱신했다. 브랜치 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 유지, 커밋·병합·푸시 없음.
- 남은 범위: 운영 공급자·배포·전체 LT 캠페인/SLO·공통 pagination 등은 여전히 별도다. 이번 결과는 지정된 로컬 통합 브라우저 흐름 검증이며 전체 로드맵 완료가 아니다.

## 새 채팅 브라우저 통합 검증 시작 (2026-10-13)

- 시작: 지정 통합 worktree의 `feature/roadmap-integration`, HEAD `fb75a467fba8c430f6da4a8e215d1c0f3b995470` 및 미커밋 통합 변경을 확인했다. 기존 변경과 원본 worktree를 보존한다.
- 환경: 기존 임시 스크립트와 Python 환경을 확인하고, 사용자 데이터와 분리된 새 임시 DB/두 Workspace/OIDC 공급자를 같은 5182·5183 포트로 실행했다.
- 접근: 정상 `cua_repl` in-app browser로 5182 로그인 화면과 SSO 로그인 후 팀 A 프로젝트 목록을 확인했다. 이전 저장 권한 정책 거절은 이번 세션에서 재현되지 않았다. 다른 포트/브라우저/직접 명령 우회 없음.
- 기록 정정: 과거 기록의 사용자 설정 변경 필요 단정은 확인된 원인이 아니다. 사용자는 이미 항상 허용을 확인했으며 이번 정상 도구 접근은 성공했다.
- 진행: Workspace·import·release·portal·SDK 다운로드 및 새로고침/뒤로 가기/실행 복원을 실제 브라우저로 검증한다. 기존 552개 전체 Python은 마지막 shutdown 수정 전 결과임을 유지한다.

## 브라우저 차단 사유 재확인

- 사용자 재개 요청 후 기존 검증 주소 `http://127.0.0.1:5182`를 확인했으며, 브라우저 도구가 저장된 사용자 권한 설정에 의한 차단이라고 명시했다. 일반 채팅 승인이 부족한 상태가 아니라 저장된 사이트 차단 설정의 변경이 필요하다.
- 차단 해제 여부를 사용자에게 요청했다. 해제 답변 전 재접속·다른 브라우저·주소 변경·직접 브라우저 명령으로 우회하지 않는다. 제품 코드 변경·테스트 재실행·Git 게시 없음.

## 통합 SDK 실제 Java 취소·시간 초과 확인 (2026-10-13)

- 시작: 통합 계획의 실제 generator lifecycle 근거를 현재 feature/roadmap-integration에서 확인했다. 제품 코드는 변경하지 않았다.
- 검증: 임시3500 operation 명세의 Java 프로세스 실행을 관측한 뒤 취소(0.497초), 별도2초 deadline으로 timeout(2.062초)을 확인했다. 각 작업의 준비/Java 프로세스2개 모두 종료, 작업 임시 디렉터리0개, 게시 ZIP 없음.
- 관측 이력: 최초5초 제한은 생성이 제한 전에 정상 완료돼 timeout fixture 조건을 만족하지 않았다. 제한을2초로 명시해 별도 실행했으며 제품 timeout 실패로 해석하지 않는다.
- 결과/남은 게이트: [통합 검증 JSON](roadmap-integration-validation.json)에 기록했다. 실제 브라우저 검증은 도구 접근 거절로 대기, 운영 issuer/client 정보도 미제공 상태다. Git 게시 없음.

## 7개 작업 로컬 통합·검증 (2026-10-13)

- 승인/기준: 사용자 `승인`에 따라 원격 develop `fb75a46`과 같은 기준으로 `feature/roadmap-integration`을 생성했다. 7개 원본 worktree의521개 파일 항목을 snapshot/hash로 보존했고 완료 시 원본 변경0개를 확인했다. commit/develop merge/push는 하지 않았다.
- 변경: P0/P1·OAS-1·API-3·RUN-2·IOP-1·COL-1/2·GOV-1/DOC-1을 결합했다. OpenAPI route/model102개를 재생성하고 인증 gate·import·release·portal·SDK 화면과 스타일을 함께 연결했다.
- 통합 수정: OAuth 실행 Vault를 현재 사용자/Workspace에 연결, Runner의 OAuth 발급 허용, SDK queue 시작 전 membership 재확인, portal ZIP에도 authenticatedFetch 적용, API OAuth callback query 로그 제거, P1 계측의 Workspace case root 사용, shutdown 시 영구 commit을 끝낸 release job의 성공 상태 보존을 반영했다.
- 저장소: identity/release 독립 migration과 OAuth v6를 결합했다. 계정·감사·release·SDK ZIP은 이관하고 session/pending 및 OAuth token은 제외한다. 하나의 SQLite source에 모든 기능을 넣어 PostgreSQL parity·ZIP bytes·migration version·원본 DB 불변을 확인했다.
- 자동 검증: 전체 Python552개(skip0,78.093초), frontend111개·production build, 생성 최신성·diff 검사 통과. 이후 shutdown commit 경계 수정은 job/SDK/portal/교차 기능45개(8.685초), 결합 PostgreSQL 이관 신규1개(0.299초)로 검증했다. 전체552개를 최종 shutdown 수정 후 재실행한 것으로 표기하지 않는다.
- 실제 HTTP: 테스트 인증 어댑터와 독립 loopback 서버에서 두 Workspace의 OAuth 발급→빠른 호출→실제 Python 자식 runner→파이프라인→이력 및 import/export 격리 확인. 실제 Java 생성기로 Python SDK·release Go SDK를 생성해 ZIP CRC/SHA·원본 revision/digest·타 Workspace404·작업 관리자 재시작 후 동일 파일을 확인했다.
- 실제 HTTPS: 임시 CA 검증을 켠 OIDC 공급자와 Uvicorn에서 로그인·PKCE·CSRF·Workspace 전환·logout·replay 거부·token 미저장 fixture를 통합 코드로 다시 실행해 통과했다. 운영 공급자를 사용한 결과는 아니다.
- 실패 이력: 첫 Python 통합 실행547개는 기존 TestClient host/identity fixture 불일치13실패·3오류였다. loopback Host·임시 identity DB·trusted adapter로 fixture를 수정했다. 추가 실제 runner 검증의 첫 실행은 임시 fixture ROOT에 CLI entrypoint가 없어 실패했으며 repo 실행 root와 임시 data root를 구분해 해소했다.
- 완료 경계: 로컬 코드 통합과 위 검증까지. 실제 브라우저 접근은 사용자 허용 후에도 도구 정책 거절 상태로 남아 있다. 운영 issuer 등록·외부 배포·전체 LT campaign·공통 pagination 등은 미완료이며 이전 실패/unknown을 변경하지 않는다.
- 자료: [통합 검증 JSON](roadmap-integration-validation.json), [원본 파일 해시](roadmap-integration-source-manifest.json), [통합 계획](roadmap-integration-plan.md).

## 통합 시작 (2026-10-13)

사용자 승인으로 `feature/roadmap-integration`에서 7개 작업을 통합한다. 원본 worktree는 보존하고 commit/develop merge/push는 하지 않는다. 인증·저장소·job·화면 계약을 결합하고 전체 회귀 및 교차 Workspace 통합 검증을 수행한다. 브라우저 접근 제한은 별도다.

### 원본 단계별 기록

- [COL 기존 기록](archive/integration-sources/COL/api-development-progress.md)
- [P1 기존 기록](archive/integration-sources/P1/api-development-progress.md)
- [OAS 기존 기록](archive/integration-sources/OAS/api-development-progress.md)
- [API 기존 기록](archive/integration-sources/API/api-development-progress.md)
- [RUN 기존 기록](archive/integration-sources/RUN/api-development-progress.md)
- [IOP 기존 기록](archive/integration-sources/IOP/api-development-progress.md)
- [GOV 기존 기록](archive/integration-sources/GOV/api-development-progress.md)
