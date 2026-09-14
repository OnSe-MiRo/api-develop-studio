# FND-4 저장소 운영 계약

## 적용 범위

Docker의 영구 저장소는 PostgreSQL 17이며 프로젝트·케이스·파이프라인·revision·audit·ownership·실행 metadata를 저장한다. Redis 7은 revision 목록의 `revision`, `created_by`, `created_at`, `content_hash`만 60초 동안 캐시한다. 문서 본문, secret, 인증 header, 원문 request/response, ownership·membership 판정은 캐시하지 않는다. 프로젝트 목록과 OpenAPI는 DB에서 읽는다. 캐시 대상을 늘릴 때는 각 필드의 민감정보 계약을 먼저 정한다.

`STUDIO_DATABASE_URL_FILE` 또는 `STUDIO_DATABASE_URL`을 지정하면 PostgreSQL을 사용한다. URL 파일을 우선하며 빈 파일은 설정 오류다. 설정된 PostgreSQL의 장애를 SQLite로 우회하지 않는다. 두 설정이 없는 native 실행은 기존 SQLite 호환 모드이며 `STUDIO_DB_PATH`와 `STUDIO_OWNERSHIP_DB_PATH`를 사용한다.

## 서버 문맥과 저장 계약

- 저장소 인스턴스는 불변 `RequestContext`에 바인딩되며 모든 문서·실행·ownership query가 해당 workspace 범위로 동작한다. 기본 인스턴스는 서버가 정한 로컬 시스템 문맥이다. 기존 ID를 보존하기 위해 local workspace의 내부 ID는 `default`, 시스템 사용자는 `local-user`를 유지한다.
- `users`, `user_identities`, `workspaces`, `memberships`가 사용자·외부 identity·workspace·활성 membership 계약을 제공한다. `memberships`는 로드맵의 `workspace_members`에 해당하는 기존 테이블명이다. provider와 subject 조합은 unique다. 사용자와 membership 삭제가 업무 데이터를 cascade 삭제하지 않는다.
- PostgreSQL 문서 조회는 활성 사용자·workspace·membership을 확인한다. 문서 변경에는 owner/admin/editor가 필요하다. 작성자는 context에서 결정하며 `X-Studio-Actor`나 저장 body의 주체 필드를 신뢰하지 않는다. 실행 이력과 ownership도 활성 membership을 확인한다.
- 생성·수정의 revision, hash, 작성자와 audit, 투영 작업은 같은 transaction에 기록한다. soft-delete는 `deleted_at`, `deleted_by`를 남긴다. PostgreSQL audit은 UPDATE/DELETE 차단 trigger를 갖는다. audit의 request ID는 context 값이 있으면 사용하고 없으면 작업 UUID를 생성한다.
- 로그인, 검증된 service token, HTTP request별 사용자 선택, runner/viewer 실행 RBAC와 전체 파일·artifact 접근 격리는 COL-2/COL-1 범위다. 현재 HTTP는 고정 로컬 시스템 문맥만 제공한다. 이 구현만으로 외부 다중 사용자 서비스를 공개하지 않는다.
- 다른 workspace의 JSON 투영은 각 root의 `_workspaces/{workspace_id}/` 아래로 분리한다. 기본 CLI의 `case/{tag}/{api_name}/{case_file}.json` 경로는 유지한다.

## 트랜잭션과 연결

프로세스당 connection pool은 최소 1개, 최대 5개다. 획득 대기 10초, 접속 5초, statement 15초, lock 대기 5초, idle transaction 15초, 전체 transaction 30초다. PostgreSQL 17 이상이 필요하다. pool은 대여 시 연결을 확인하고 끊긴 연결을 재생성한다.

초기 전환에서는 PostgreSQL transaction advisory lock으로 기존 SQLite의 직렬 write 의미를 유지한다. 기존 문서 수정뿐 아니라 동시 신규 생성도 같은 경계에서 처리한다. read는 이 lock을 취하지 않는다. workspace/reference unique, document/project, revision, 실행 workspace/시각 index를 사용한다. subprocess와 JSON 투영이 남아 있으므로 Uvicorn은 여전히 단일 worker다.

업무 transaction은 자동 재시도하지 않는다. DB commit 응답이 유실되었을 때 중복 revision이나 실행을 만들지 않기 위해 최신 revision을 조회한 후 사용자가 다시 시도한다. cache 장애는 DB 조회로 대체하며, DB 장애는 일반 API에서 민감한 SQL을 노출하지 않는 503으로 처리한다. 기존 dashboard 오류 계약은 유지하고, 실행 이후 history 기록 실패는 기존 `historyWarning`으로 구분한다.

연결 동작은 [Psycopg pool 문서](https://www.psycopg.org/psycopg3/docs/advanced/pool.html), timeout은 [PostgreSQL 설정 문서](https://www.postgresql.org/docs/17/runtime-config-client.html)를 참고한다.

## JSON 투영과 복구

DB commit 후 현재 revision을 JSON으로 쓴다. 파일 쓰기에 실패해도 DB 저장은 유지되고 `projection_jobs.status=failed`가 남는다. 저장 응답의 `_storage.projectionPending=true`로 이 상태를 구분한다. 서버 초기화와 실행 전 pending 투영을 다시 처리하며, 복구되지 않으면 CLI 실행을 시작하지 않는다. 동일 내용 재저장도 pending 투영을 다시 처리한다.

PostgreSQL에서 기존 문서가 있으면 파일을 다시 import하지 않는다. 오래된 파일이 DB revision을 덮어쓰거나 삭제 문서를 부활시키지 않는다. 빈 DB만 JSON bootstrap을 허용하며, SQLite 문서 이력이 발견되면 먼저 정식 이관을 요구한다.

```sh
# Docker 안에서 미완료 투영 복구
docker compose exec api python -m api_test.repair_projections --root /app
# JSON volume 유실 또는 DB 복원 후 전체 재생성
docker compose exec api python -m api_test.repair_projections --root /app --all
```

업로드 바이너리, 실행 로그, SDK artifact와 암호화 key는 JSON 투영으로 재생성되지 않는다. 별도 보존 정책과 백업이 필요하다.

## Docker 설정과 기존 SQLite 이관

1. 기존 API와 CLI writer를 중지한다. SQLite DB뿐 아니라 기존 JSON, 업로드와 암호화 key를 백업한다.
2. 저장소 밖의 비밀 파일에 PostgreSQL password와 `postgresql://studio:<password>@postgres:5432/studio`를 각각 제공한다. 비밀번호의 URL 예약 문자는 percent-encode한다. `.env`에는 내용 대신 `POSTGRES_PASSWORD_FILE`, `STUDIO_DATABASE_URL_FILE` 경로만 넣는다. production에서는 플랫폼 secret manager로 이 파일을 주입한다.
3. `docker compose up -d postgres redis encryption`으로 저장소를 먼저 시작하고 `docker compose build api`로 이미지를 준비한다. PostgreSQL·Redis에 host port를 열지 않는다.
4. 기존 `data/studio.db`와 `data/ownership.db`를 같은 중지 시점 기준으로 준비한 뒤 다음 명령을 실행한다. ownership 파일이 없는 설치는 빈 ownership DB를 SQLite 호환 모드의 `OwnershipStore.db()`로 먼저 생성한다. 도구가 누락된 원본을 임의로 새 파일로 만들지는 않는다.

```sh
docker compose run --rm --no-deps api python -m api_test.migrate_postgres \
  --studio /app/data/studio.db --ownership /app/data/ownership.db
```

이관 도구는 원본을 `mode=ro`로 열고 SQLite backup API로 메모리 snapshot을 만든다. schema 보정은 snapshot에만 적용한다. PostgreSQL schema 준비 후 모든 데이터 복사와 검증은 하나의 transaction이다. 테이블별 row 수와 전체 row digest, document ID·revision·hash·soft-delete를 비교하고 content hash를 다시 계산한다. 충돌/추가 row 또는 불일치가 있으면 데이터 전체를 rollback한다. 같은 snapshot을 그대로 재실행하면 같은 manifest가 나온다. API를 먼저 띄워 초기 데이터를 만든 대상과 기존 snapshot을 자동 병합하지 않는다. 이 경우 새 빈 대상 DB로 다시 이관한다.

5. 출력 manifest를 검토하고 `docker compose up -d api web`을 실행한다. `/api/projects`, `/api/cases`, `/api/dashboard`와 대표 revision을 확인한다. 실패 시 writer를 계속 중지한 상태에서 기존 SQLite 설정으로 되돌릴 수 있다. PostgreSQL에서 신규 write를 시작한 뒤에는 자동 역이관을 제공하지 않는다.

## 백업과 복원

PostgreSQL은 `postgres_data` 영구 volume을 사용한다. Redis는 persistence 없이 128 MB LRU 캐시로 실행한다. Redis 재시작으로 인증이나 영구 데이터가 사라지지 않는다.

```sh
# 접근 통제된 백업 경로에 저장
docker compose exec -T postgres pg_dump -U studio -d studio -Fc > /secure-backup/studio.dump
# 새 빈 DB로 검증 복원
docker compose exec postgres createdb -U studio studio_restore
docker compose exec -T postgres pg_restore -U studio -d studio_restore < /secure-backup/studio.dump
```

복원 대상의 row 수와 revision/hash를 확인하고 연결 secret을 복원 DB로 전환한 뒤 전체 투영을 재생성한다. encryption key, 업로드 파일과 artifact 백업은 PostgreSQL dump와 별도로 관리한다. 백업 파일도 문서와 같은 민감도를 가진다.

## 검증 명령

```sh
python3 -m unittest discover -s tests -v
# 테스트 전용 PostgreSQL 연결(CREATEDB 권한)과 Redis를 제공한다.
# 각 테스트는 무작위 이름의 새 DB만 만들고 제거한다.
FND4_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55434/studio_test \
FND4_TEST_REDIS_URL=redis://127.0.0.1:56384/0 \
python3 -m unittest discover -s tests -p test_postgres_storage.py -v
```

일반 실행에서는 외부 서비스 통합 테스트가 명시적으로 skip된다. 완료 판단에는 서비스 URL을 제공한 실행 결과가 필요하다.
