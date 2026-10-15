# SDK 생성 작업과 ZIP 수명주기

SDK 생성은 저장된 프로젝트의 **원본 OpenAPI 문서**와 프로젝트 revision을 접수 시점에 고정하고, 기존 기능 테스트와 같은 `app.state.jobs`의 worker slot·queue·사용자/프로젝트 한도를 사용한다. 다른 요청으로 프로젝트 문서가 바뀌어도 이미 접수된 작업은 새 문서를 다시 읽지 않는다. 프로젝트 변수·secret·인증 프로필·환경은 스냅샷이나 생성기 입력에 포함하지 않는다.

```json
POST /api/generations
{"project":"team/api.json","language":"python","projectRevision":4}
```

지원 언어는 `python`, `javascript`, `typescript`, `java`, `kotlin`, `go`, `csharp`이다. 저장 문서 revision 누락·불일치는 409, 형식/언어/원본 오류는 400, queue·사용자/프로젝트 접수 한도 초과는 429이다. 정상 접수는 즉시 **202**와 `runId`, `status:queued`, `kind:sdk_generation`, `generation` metadata를 반환한다. `generation`에는 project, language, projectRevision, sourceKind, sourceDigest, fetchedAt, artifactReady와 artifact(sizeBytes/SHA-256/expiresAt)만 둔다. 원본 ZIP·파일 경로나 JAR 출력은 job JSON에 담지 않는다.

기존 `GET /api/runs/{runId}`로 작업을 조회하고 `POST /api/runs/{runId}/cancel`로 취소한다. 선택 언어와 작업 ID는 프로젝트·언어 범위의 sessionStorage에 유지하여 같은 탭의 새로고침과 프로젝트 전환 후 복원한다. 브라우저 연결이 끊겨도 접수된 process-local 작업은 기존 run retention 안에서 추적한다. URL로 등록된 명세는 redirect를 따르지 않는 준비 subprocess에서 **한 번만** 가져오며 `fetchedAt`과 받은 원본의 digest를 완료 metadata에 남긴다. 저장된 file/bundle은 접수 즉시 digest가 있다. URL에서 가져온 문서는 다른 프로젝트 revision과 동일하다고 가정하지 않는다.

`GET /api/generations/{runId}/artifact`는 작업 owner·종류·성공 상태와 ZIP 보존을 확인한 뒤 `application/zip` attachment를 보낸다. 대기·실행·실패·취소·timeout은 409, 없는 run·다른 종류·보존 기한 경과 또는 메모리 quota로 퇴거된 ZIP은 404이다. 다운로드는 사용자가 명시적으로 시작하며 자동 재제출/다운로드를 하지 않는다.

생성 과정은 기존 로컬 고정 OpenAPI Generator 7.24 JAR과 Java만 실행한다. 사용자 template, postprocess 명령, dependency download를 인자로 제공하지 않는다. Swagger 2.0과 OpenAPI 3.x의 file/bundle/URL 원본을 임의로 펼치지 않는다. 분할 bundle 외부 schema의 자기 전체 참조는 고정 JAR의 해석 차이를 피하기 위해 생성기 입력 사본에서만 의미가 같은 자기 파일 상대 참조로 바꾸고, ZIP에는 원본 파일 byte를 그대로 보존한다. 원본 bundle·inline의 모든 `$ref`를 먼저 검사해 remote/file, 디렉터리 밖, 빠진 대상을 거부하고 재귀적인 **로컬** 참조는 유지한다. URL의 로컬 참조도 단일 파일 안에서만 허용한다.

작업 한도는 `RUN_TIMEOUT_SECONDS`(기본 300초), 입력 bundle 5 MiB·200파일, 생성 작업 10,000파일/128 MiB, ZIP 32 MiB이다. Java는 작업 전용 임시 디렉터리와 최소 subprocess 환경에서 별도 process group으로 실행한다. 취소·timeout·오류 시 그룹과 하위 프로세스를 종료하고 임시 원본/출력/로그를 제거한 뒤 terminal 상태를 게시한다. JAR stderr와 원본 example은 API·job 상태로 돌려주지 않는다.

ZIP은 별도 private in-memory cache에만 둔다. artifact당 32 MiB, cache 전체 128 MiB, 동시에 전송 중인 ZIP 4개/128 MiB로 한정한다. 전송이 취소되면 ASGI 응답의 `finally`에서 전송 lease를 해제한다. 기존 `RUN_RETENTION`(기본 600초)과 `RUN_MAX_COMPLETED` 상한, cache quota에서 오래된 artifact를 제거하며 조회는 `artifactReady:false`로 바뀐다. hard crash·process restart에서는 현재 process-local 작업과 ZIP을 복구하지 않는다. 이것은 분산/영속 job이 아니며 운영상의 재생성 절차가 필요하다.

기존 `POST /api/generate`는 즉시 ZIP 응답을 유지하지만 같은 worker `legacy_slot`, 시간/파일/ZIP 한도, Java process-tree 정리 경계를 사용한다. queue를 자동으로 우회하거나 비동기 작업으로 조용히 전환하지 않는다.

[개발 진행 기록](api-development-progress.md)에 구현과 검증 범위를 남긴다.
