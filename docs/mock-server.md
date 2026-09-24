# OpenAPI 기반 Mock Server

Mock Server는 프로젝트의 OpenAPI 명세를 바탕으로 외부 API 없이 응답 예제, schema 기반 응답, 오류 응답과 선언형 CRUD 흐름을 재현한다. API 목록 화면의 **Mock Server** 패널에서 설정하고 시작할 수 있다.

## 사용 흐름

1. 프로젝트를 선택하고 API 목록 화면을 연다.
2. seed, scenario, 기본 지연시간과 operation별 status·media type·example·오류 응답을 설정한다.
3. Mock Server를 시작하고 화면에 표시된 loopback URL로 요청한다.
4. 상태 초기화가 필요하면 `reset`, 사용이 끝나면 `stop`을 실행한다.

새로고침 뒤에는 서버 상태와 설정을 다시 조회한다. 명세는 서버 시작 시점의 snapshot을 사용하므로 명세를 바꾼 뒤에는 서버를 다시 시작한다.

## 응답과 상태 정책

- 명시적으로 선택한 example과 media type을 우선 사용하고, 없으면 schema를 기반으로 결정적인 응답을 만든다.
- 같은 명세·seed·scenario·초기 상태와 요청 순서에서는 같은 결과를 재현한다.
- 기본 CRUD 동작은 collection별 상태와 증가하는 ID를 사용한다. resource, 상위 경로 parameter, 프로젝트 사이의 상태를 섞지 않는다.
- 명시적 example 재생과 400 이상 오류 응답은 CRUD 상태를 변경하지 않는다.
- 같은 seed와 scenario에서 latency나 override만 바꾸면 상태를 유지한다. seed 또는 scenario를 바꾸거나 reset하면 상태를 초기화한다.
- reset 또는 seed/scenario 변경 전에 시작된 변경 요청은 새 상태를 오염시키지 않도록 `409 STATE_CHANGED`로 거부할 수 있다.
- 지원할 수 없는 schema는 잘못된 성공 응답 대신 구조화된 오류로 거부한다.

## 보안과 실행 제한

- bind host는 `127.0.0.1`, `localhost`, `::1`만 허용한다. 외부 IP와 wildcard bind는 거부한다.
- 상태는 Studio 프로세스 메모리에만 존재한다. Mock Server 중지나 Studio 재시작 뒤에는 복구되지 않는다.
- 단일 Studio 프로세스에서 실행한다. 여러 replica 사이에 상태를 공유하지 않는다.
- 요청 body·응답·단일 상태 항목은 1MiB, 전체 상태는 10MiB·10,000개 항목으로 제한한다.
- 기본 지연시간은 0~5000ms 범위다. 중지 시 진행 요청은 제한 시간 안에서 취소하고 task·event loop·socket을 정리한다.

## 관리 API

| Method | Path | 용도 |
| --- | --- | --- |
| `GET` | `/api/projects/{reference}/mock` | 상태와 설정 조회 |
| `POST` | `/api/projects/{reference}/mock/start` | 서버 시작 |
| `POST` | `/api/projects/{reference}/mock/config` | 실행 설정 변경 |
| `POST` | `/api/projects/{reference}/mock/reset` | 상태 초기화 |
| `POST` | `/api/projects/{reference}/mock/stop` | 서버 중지 |

정확한 request·response schema는 `/api/schema.json` 또는 `openapi/paths/mock.yaml`과 `openapi/components/schemas/mock.yaml`을 기준으로 한다.

## 검증

저장소 루트에서 테스트용 PostgreSQL·Redis를 먼저 기동한 뒤 검증한다.

```bash
docker compose -f docker-compose.test.yml up -d --wait
.venv/bin/python -m unittest discover -s tests -p 'test_mock*.py' -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/generate_server.py --check
cd web
npm test
npm run build
```

개발 과정의 상세 인계·리뷰·검증 증거는 [MOCK-1 보관 기록](archive/mock-1/README.md)에 있다.

2026-09-25 로컬 완료 검증: 전체 Python 300개(skip 0), frontend 28개·build·생성 검사 및 실제 브라우저 명세 소스 3종 확인. [완료 보고서](archive/mock-1/completion-report.md)를 참고한다. 이번 보완의 Git 반영은 개발 완료 판정과 별도다.
