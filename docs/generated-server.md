# OpenAPI Generator 기반 Studio 서버

Studio 자체 API 명세는 `openapi/studio.yaml`에서 관리한다. 테스트 대상 API를 가져오거나 클라이언트 SDK ZIP을 만드는 기존 기능과 별개다. Generator 7.24.0의 `python-fastapi`와 저장소의 Mustache 템플릿으로 라우터·Pydantic 모델·라우터 목록을 생성한다.

## 구조와 요청 흐름

```text
openapi/studio.yaml                 Studio 계약, 29 operations / 41 named schemas
openapi/generator-config.yaml       고정 생성 옵션
openapi/templates/                  라우터·모델·등록 목록 템플릿
scripts/generate_server.py           생성 및 --check
api_test/generated/apis/            생성 APIRouter, 직접 수정 금지
api_test/generated/models/          생성 Pydantic DTO, 직접 수정 금지
api_test/generated/main.py           생성 라우터 목록
api_test/main.py                     앱 구성, 오류 응답, SPA fallback, 서버 실행
api_test/dependencies.py             요청별 origin 검사, 업로드 제한, thread pool
api_test/implementations/            생성 operation과 서비스의 명시적 연결
api_test/services/                   직접 작성하는 업무 로직
api_test/services/studio.py          기존 공유 검증·암호화·전송·문서 도우미와 요청 응답 도우미
api_test/collaboration_store.py      기존 versioned 저장소
api_test/ownership.py                기존 소유권 정책과 저장소
react_server.py                     기존 실행 및 import 호환 진입점
api_test/asgi.py                     기존 app factory import 호환
api_test/routes/                     기존 호출자용 dispatch 어댑터
```

요청은 생성된 APIRouter → 요청 문맥 dependency → implementation → service → 기존 저장소/runner로 흐른다. 실제 운영 경로에서는 기존 문자열 parts dispatch를 사용하지 않는다. SQLite/PostgreSQL 저장소 구현과 암호화 경계는 유지한다.

공유 도우미는 아직 `services/studio.py`에 모여 있다. 이번 전환은 생성 서버 구조와 도메인별 operation 서비스를 분리한 것이며, 모든 도우미를 독립적인 repository/service 클래스나 DI 컨테이너로 다시 작성한 것은 아니다.

## 생성과 실행

requirements.txt의 고정 Generator 버전과 Java 런타임이 필요하다.

```sh
python -m pip install -r requirements.txt
python scripts/generate_server.py
python scripts/generate_server.py --check
python -m api_test.main
```

`python react_server.py`, `python -m react_server`, `react_server:app`도 호환된다. Docker 기본 진입점은 `python -m api_test.main`이다. `API_TEST_HOST`, `API_TEST_PORT`, loopback 제한과 단일 worker 정책을 유지한다.

생성은 임시 디렉터리에서 진행한 뒤 `api_test/generated/`의 Python 파일만 동기화한다. Generator가 기본으로 만드는 Dockerfile, requirements, 테스트 스텁과 구현 스텁은 애플리케이션에 복사하지 않는다. `--check`는 작업 트리를 쓰지 않고 실제 재생성 결과와 비교한다. 구현 파일은 생성 폴더 밖에 둔다.

## 계약과 호환성

- `/api/schema.json`은 기준 명세를 반환한다. 내부 implementation 이름 등 `x-studio-*` 확장은 공개 응답에서 제외한다.
- `operationId`와 `tags`는 생성 함수·모듈을 결정한다. `x-studio-handler`는 직접 작성하는 구현 함수와 연결하고, `x-studio-route`는 슬래시가 포함된 reference를 받는 FastAPI 경로를 지정한다.
- suffix 경로를 greedy reference보다 먼저 등록하여 `/revisions`, `/openapi/operations`가 파일명에 포함되지 않도록 한다.
- 생성 DTO는 필드 타입·별칭·enum을 제공하며 `to_dict()`는 명시적 null, 추가 필드와 `_storage` 별칭을 보존한다.
- **HTTP 입력의 업무 검증은 기존 서비스가 수행한다.** 생성 DTO로 원문을 강제 변환하거나 요청을 먼저 422로 거부하지 않는다. 이 선택으로 기존 메시지·400/409·revision 검사 순서와 JSON 숫자/추가 필드 보존을 유지한다. 향후 DTO 검증을 HTTP 입력에 강제 적용하려면 별도의 API 계약 변경과 회귀 검증이 필요하다.
- 서비스는 기존 Response를 반환하므로 생성 응답 모델이 응답을 필터링하거나 secret을 자동으로 마스킹한다고 가정하면 안 된다. secret 조회·보존·마스킹은 기존 서비스 정책이 담당한다.
- 업로드는 stream을 읽는 동안 25MB 제한을 적용한다. 동기 저장소·네트워크·subprocess 작업은 thread pool에서 실행한다.
- `.github/workflows/server-contract.yml`은 재생성 검사와 Python 계약 테스트를 실행한다. 외부 PostgreSQL/Redis 테스트는 별도 서비스 설정이 필요하다.

## 변경 절차

1. 명세의 요청·응답과 operation을 변경한다.
2. `python scripts/generate_server.py`로 생성 파일을 갱신한다.
3. `api_test/implementations/`와 `api_test/services/`에 필요한 업무 로직을 구현한다.
4. Python 계약 테스트와 `--check`를 실행한다. React 변경이 있으면 web/ 테스트와 build도 실행한다.
5. 생성 파일을 수동 수정하지 않는다. 생성 형태를 바꾸려면 템플릿을 수정하고 전체를 재생성한다.

검증: 기존 FastAPI HTTP 계약 테스트, 모든 명세 operation의 생성/구현 연결 검사, DTO null·추가 필드·secret read/write 검사, 실제 임시 Uvicorn CRUD 및 빠른 HTTP 호출을 포함한다.
