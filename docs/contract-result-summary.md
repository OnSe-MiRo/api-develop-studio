# 실행 결과·이력의 OpenAPI 계약 요약

## 표시 위치와 의미

케이스/파이프라인의 실시간 RunResult 단계별 결과와 대시보드 실행 상세에서 동일한 계약 요약을 표시한다. 기존 JSON report/이력의 `contract` metadata만 사용하며 새로운 응답/명세 원문 수집이나 API 호출을 추가하지 않는다.

- **OpenAPI 계약 통과 / 실패**: 계약 자체의 판정이다. status/body/assertion 등의 다른 검증 때문에 전체 실행은 별도로 실패할 수 있다.
- **문제 N개**: 검증기가 기록한 issueCount다. 실제 응답값이나 원문 진단은 표시하지 않는다.
- **검사 명세 SHA-256**: 키보드로 열 수 있는 details에서 전체 지문을 확인한다. 실행 당시 snapshot 식별자이며 현재 프로젝트 명세와 같다는 보장이나 원본 명세 보관 기능은 아니다.
- **OpenAPI 계약 요약 없음**: contract가 없거나 null인 이전/비활성/미수집 결과다. 검증이 통과했거나 반드시 비활성이었다고 추정하지 않는다.
- **OpenAPI 계약 요약 확인 불가**: metadata 형식이 잘못되거나 판정과 개수가 모순된 경우다. raw field를 출력하거나 통과로 간주하지 않는다.

표시 가능한 metadata는 boolean valid, 0~100 정수 issueCount, 64자리 hex documentDigest다. 통과는 count0, 실패는 count1 이상이어야 한다. 허용된 세 필드 외 내용은 렌더링하지 않는다. 긴 지문은 줄바꿈하며 focus 테두리와 텍스트 사이 간격을 유지한다.

실패 대상 재실행·준비/정리 단계·Workspace 권한은 기존 서버 endpoint를 그대로 사용한다. 2026-10-28 후속 작업에서 조회 조건과 상세 Run ID를 URL에 보존해 새로고침·뒤로 가기에서도 복원한다. [URL 복원 계약](dashboard-url-state.md)을 참조한다.

## 검증 (2026-10-24)

- 전체 Python598개(skip0,110.074초), 이력 집중10개 통과. 추가 테스트는 DB 재오픈/HTTP 상세에서 요약 보존, 관련 없는 body/token 필드 배제, 기존 실패 pipeline 재실행 경계를 확인했다.
- 전체 frontend143개(33파일, worker2), production build 통과. 마지막 focus 간격 보완 후 관련8개 및 build도 통과했다. 통과·실패·과거·malformed·모순 metadata, assertion 실패와 계약 통과의 분리, 다른 run의 지연 응답 거부를 포함한다.
- 실제 HTTP로 격리 로컬 프로젝트의 저장 pipeline 실패·성공·비활성3개 실행을 만들었다. 실제 브라우저에서 각각 계약 실패1개/통과0개/요약 없음, 명세 지문 펼침, 새로고침 재조회와 기존 실패 대상 재실행을 확인했다. 재실행의 실시간 결과와 원래 이력의 판정·개수·digest가 같았다.
- 최종 빌드에서 Enter로 명세 지문을 펼쳐 표시를 확인했다. 콘솔 오류/경고0개. [화면 증거](contract-result-summary-browser.jpg).
- 로그: `/tmp/contract-summary-history.log`, `/tmp/contract-summary-python-all.log`, `/tmp/contract-summary-web-final.log`, `/tmp/contract-summary-final-focused.log`, `/tmp/contract-summary-build.log`. 구현 테스트 실패 없음. 커밋 전 자동검토의 처음 시간초과는 명령 미실행 상태에서 한 번 재요청해 해소했다.

저장 케이스 계약검증은 커밋529e466·로컬 develop 병합8debdee로 반영했다. 이 화면 기능은 feature/contract-result-summary의 미커밋 변경이며 원격 푸시는 하지 않았다. 실제 운영 공급자/외부 배포/전체 부하 캠페인과 과거 실패·unknown을 이번 화면 검증으로 대체하지 않는다.
