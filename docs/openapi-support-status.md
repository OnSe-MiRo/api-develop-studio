# OpenAPI 계약 지원 현황

2026-11-06, `48459f7`에서 시작한 튜플 allOf 지원 포함. 아래는 현재 구현 범위이며 OpenAPI/JSON Schema 전체 지원 선언이 아니다. 상세 설정과 과거 단계별 검증은 [계약 안내](openapi-contract-validation.md)를 참고한다.

| 영역 | 지원 범위 | 남은 제한 |
| --- | --- | --- |
| 계약 연결 | 3.0/3.1 lint, operation/server 매칭·변수·상대URL, 빠른 호출·opt-in 저장 케이스·파이프라인 | 원격 참조 fetch 없음 |
| 응답 본문 | status/media/body schema, schema 없는 JSON 문법 검사, 중복키·비유한 숫자 거부 | 원문 없이 파싱된 값만 받으면 원래 JSON 문법 복원 불가 |
| 기본 헤더 | scalar, 동종 primitive 배열, 평면 객체, required | 중첩 simple 직렬화 미지원 |
| content 헤더 | JSON/+json, text/plain | XML/HTML/binary/wildcard 미지원 |
| 타입 결정 | nullable type 배열, enum/const, 동종 allOf/oneOf/anyOf | 혼합·모호한 타입을 임의로 변환하지 않음 |
| container 조합 | 배열 allOf/동종 union, 객체 allOf/동일 필드 타입 union | 서로 다른 필드 구조·조건부/패턴과 조합된 container는 제한 |
| tuple | 직접 및 allOf의 prefixItems, 분기별 items, 내부 참조, primitive·boolean·빈 schema | 튜플 oneOf/anyOf 타입 추론 및 중첩 항목 |
| 자유/금지 schema | 직접 배열 items 및 객체 properties의 true/false/빈 schema | boolean schema는3.1,3.0은 빈 schema만 지원 |
| 패턴 필드 | 직접 객체 patternProperties, properties와 모든 매칭 패턴의 제약 교집합 | container composition 간 패턴 합성 미지원 |
| 로컬 참조 | 루트/빈키/이스케이프/UTF-8 JSON Pointer, 파일 경로 단일 디코딩·루트 제한 | $id/anchor/dynamic reference/custom dialect 미지원 |
| 변경 비교 | 지원 규칙에 따른 breaking/review 분류와 승인 기록 | 모든 schema의 포함 관계를 증명하지 않음 |

## 완료와 잔여 작업의 경계

- 검증하지 못하는 직렬화와 타입을 성공으로 추정하지 않는다. 참조·직렬화·schema 오류를 구분한다.
- 브라우저 통합, 실제 운영 인증 공급자/배포, 전체 부하 캠페인·SLO·Windows 실환경은 별도 검증이다.
- 남은 구현 후보는 oneOf/anyOf 튜플과 조건부 객체 디코딩이다. 먼저 실제 사용하는 명세 fixture와 실패 사례로 우선순위를 정하고, 범용 schema flattening으로 제약을 삭제하지 않는다.

## 2026-11-06 튜플 allOf 검증

전체 Python 713개가 135.635초에 통과했다. 실제 HTTP runner에서 직접 선언과 조합 선언의 정상·실패 결과를 대조했고, OpenAPI 생성 코드 최신성을 확인했다.

## 2026-11-04 통합 검증

전체 Python707개(skip0,167.496초), frontend167개/37파일, build, 생성 최신성, k6모델5개 통과. 제품 코드 변경 없이 현재 기능들의 통합 상태를 확인했다. 실제 브라우저/운영 배포/전체 부하 캠페인은 재실행하지 않았다. build의 기존500kB 번들 경고는 남아 있다.
