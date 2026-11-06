# 로컬 출시 후보 검증

2026-11-06의 로컬 출시 판정은 **보류**다. 기본 동기 실행 슬롯 2개에서 목표 혼합 부하가 거부됐고, Windows 실기기 결과가 대기 중이다. 스레드 회복은 시험 조건별로 기록했다. [수치와 근거](local-release-validation.json)

## 검증 환경과 기준

로컬 macOS에서 앱과 k6를 같은 호스트에 실행했다. 확인하는 후보는 `858f0e990e1712d3f6142e14e3a551492c8f0793`이며 각 실행은 같은 seed의 별도 SQLite 스냅샷을 사용한다. 운영 서비스와 테스트 PC의 성능은 측정 대상 밖이다.

- 잠정 통과 기준은 일반 읽기 p95 300ms·p99 1초, 고유 저장 p95 1초, 예기치 않은 오류율 1% 미만, 정상 입력 5xx·리비전 유실·고아 프로세스 각각 0건이다.
- 목표 혼합 부하는 20→50 VU, 급증은 5→100→5 VU, 장시간 부하는 35 VU·7,200초다. 급증 후 5분 내 기준선 p95와 자원이 120% 안으로 돌아와야 한다. 동기 실행은 기본 worker 2개로 시험하며 접수 한도와 성공한 동시 실행을 구분한다.
- k6 2.3.0 macOS arm64 바이너리 SHA-256은 `efb8282e24ffe18f54ce3679eaa71d72e0645bbb97b14e2a05cc8b192abf48e3`이다. Small은 프로젝트 1·케이스 10·파이프라인 2개, Medium은 20·2,000·100개, Large는 100·20,000·0개다. 리비전 깊이는 모두 1이다.

## 부하 측정 결과

| 시험 | 관측 결과 | 판정 |
| --- | --- | --- |
| Small Smoke | HTTP 216건, 예상 밖 오류 0건 | 통과 |
| Medium 읽기 | 5 VU·300초 3회, 756·756·755건. 실행별 중앙값 p95 40.23ms, 2.438 RPS | 통과 |
| Small·Large 읽기 | 5 VU·300초 각 1회, 전체 p95 11.72ms·79.73ms, 예상 밖 오류 0건 | 통과 |
| Medium Target | 기본 설정 20→50 VU를 3회 시도. 첫 20 VU에서 각각 129·138·130건 후 중단. run 429가 2·1·2건, HTTP 5xx 0건 | 실패 |
| 고유 저장 | 5·20·50명에서 각각 20·80·200 PUT 성공. p95 43.81·288.92·745.86ms, 모든 최종 revision 4 | 통과 |
| 동일 리비전 경합 | 5·20·50명에서 업데이트는 매번 한 건 성공, 예상 409는 4·19·49건. 초기 생성 PUT 1건씩은 별도 | 통과 |
| 단일 동기 실행 묶음 | 1·2명은 전부 성공. 5명 중 3건, 10명 중 8건이 429. 같은 서버의 사후 회복 통과 | 전원 성공 최대 관측값 2 |
| 반복 실행·비동기 큐 | 60초 1 VU 194회, 2 VU 각각 182회 성공. 비동기 5건 모두 terminal passed. 평균 스레드 2.98→4.76, p95 43.28→42.93ms, 자식·임시 파일 0 | 접수 통과, 스레드 회복 실패 |
| 장애 주입 | 의도한 stub 500 구간은 1분 이동 오류율 중단 조건에 도달. 지연 주입에서 15건을 관측했고 장애 해제 후 실제 실행과 5분 사후 회복이 통과 | 장애 재현·해제 후 회복 확인 |
| Stress | 첫 단계 50 VU에서 run 429 10건, profile 약 5.4초 후 중단. 사전·사후 p95 46.41→41.10ms | 부하 실패, 회복 통과 |
| Spike | 100 VU로 상승 중 관측 최대 51 VU에서 run 429 5건, 약 15.5초 후 중단. 사전·사후 p95 40.06→43.33ms | 부하 실패, 회복 통과 |
| 기본 Soak | 35 VU에서 run 429 6건, 약 5.3초 후 중단. 사전·사후 p95 44.74→38.47ms | 35 VU·2시간 미충족, 회복 통과 |

Target 3회에서 관측한 예기치 않은 오류율은 1.55%·0.72%·1.54%였다. 두 번째도 동기 실행 성공 검사에서 실패했다. 세 번 모두 첫 단계에서 짧게 종료되어 Target 5분 지속 자원 기준과 50 VU의 지연은 판정할 표본이 없다. 부하 발생기의 50 VU 할당량과 실제 관측한 20 VU는 구분했다. 일회성 묶음이나 60초 실험으로 지속 가능한 최대 동시성 또는 최대 RPS를 확정할 수 없다.

### 별도 2 VU 장시간 관측

같은 후보와 Medium fixture에서 실행 슬롯 2개·실제 k6 혼합 모델·중단 기준을 유지해 동시 사용자만 2명으로 설정했다. 2 VU 표본 7,201개의 처음부터 마지막까지 간격은 7,199.96초였다. 7,978건(200 7,666건, 예상한 409 312건)을 처리했다. 예기치 않은 오류는 0건, 전체 p95는 65.99ms, p99는 275.43ms였다. 혼합 요청 중 실제 저장 케이스 실행은 394건이었다.

서버 자원 표본 1,423개에서 RSS는 78.56→45.02 MiB(최대 123.11), 스레드는 3→2(범위 2~7), 관측 WAL 크기는 0바이트였다. 사후 5분 읽기 p95는 39.78→44.07ms로 기준선의 120% 안이었다. 원본 지문·리비전·투영 무결성 및 자식 프로세스·임시 파일 0건을 확인했다. 이 관측이 성립한 부하는 2 VU다.

### 스레드 회복 대조

별도 Medium 스냅샷에서 기존 P1 회복 진단을 기본 시간으로 실행했다. 사전 기준선을 측정하기 전에 실제 작업으로 worker를 준비하고, 비동기 5건씩 두 묶음을 실행했다. 10건 모두 성공하고 child/tmp는 각 묶음 뒤 0이었다. 평균 스레드 4.75→5.00, p95 39.48→38.00ms로 두 값 모두 120% 기준을 통과했다. 전후 `ps` 값은 5→5였고 Studio worker의 native ID도 유지됐다. 예열하지 않은 반복 실행에서 관측한 2.98→4.76 실패는 별도로 유지한다. 두 실험만으로 스레드 증가 원인을 단정할 수 없다.

## 최종 후보 회귀

- 일회용 PostgreSQL·Redis를 쓴 전체 Python 718개가 138.491초에 통과했다. 전체 프런트엔드 169개(38개 파일), production build, 서버 생성 최신성, LT-5 보고서 재생성 검사, k6 모델 5개도 통과했다. build에는 기존 chunk 크기 경고가 있었다.
- 실제 브라우저에서 합성 계정으로 로그인하고 팀 A에서 cURL 미리보기·저장·새로고침·실행을 확인했다. 저장한 케이스를 다시 열어 편집기의 현재 값으로 실행했다. 자식 runner가 합성 loopback `/health`에서 HTTP 200을 받았고, 새로고침 후 Run ID `1a01f817-9852-4b9d-b28c-e11a76e96dc9`와 완료 결과가 복원됐다. 이 시험에만 문서화된 로컬 대상 소유권 생략 설정을 사용했다. 최초 fixture 준비에서 viewer의 쓰기가 거절된 뒤, 별도 합성 owner가 데이터를 준비하고 실제 로그인 계정의 viewer 권한을 유지해 다시 실행했다.
- 릴리스 `1.0.0-rc.2`의 초안·발행 단계를 거쳐 revision 1의 고정 원본을 조회했다. 포털에서 생성한 Python SDK ZIP을 실제 다운로드하고 CRC, SHA-256, 내장 manifest의 릴리스 ID와 원본 지문을 대조했다. ZIP은 32,525바이트, SHA-256은 `1882872937d7059b7062e97d529824c592021c04e642f8d27a308810400789c7`이었다. 새로고침·뒤로 가기 후 같은 릴리스의 다운로드가 복원됐다. 조회 전용 팀 B의 같은 프로젝트에서 A의 케이스와 릴리스가 보이지 않았고, 로그아웃 후 로그인 화면이 복원됐다. [포털 화면](local-release-portal.jpg)
- 브라우저 회귀는 5182·5183에서 테스트 OIDC와 루프백 HTTP를 사용했다. 별도 로컬 HTTPS 검증은 [인증 기록](oidc-login.md)에 있다.

## Windows PC에서 이어서 검증

검증 대상은 `858f0e990e1712d3f6142e14e3a551492c8f0793`이다. Windows 경로는 NTFS를 사용하는 실제 Windows의 PowerShell에서 확인한다. 로컬 전달용 소스 ZIP의 지문과 Mac에서 기록한 SHA-256을 먼저 대조한다. 전달용 파일 `studio-858f0e9.zip`의 SHA-256은 `f74d267cb8678726690c20e8dee62c69c79972e32adcf8adc13ad897e978069c`이다. 같은 폴더에 둔 `verify-windows.ps1`을 Windows PowerShell에서 실행하면 ZIP 검증, 새 폴더 압축 해제, 아래 검사와 transcript 저장을 수행한다. 스크립트 SHA-256은 `e2dd529822ddefce66ee399fabd301d58d8389f86e8b05763c7987a79f5a140b`이다. PowerShell의 `Get-FileHash -Algorithm SHA256 .\studio-858f0e9.zip`으로 대조할 수 있다.

기존 환경에 같은 커밋이 있으면 해당 checkout을 사용할 수 있다. 소스를 ZIP으로 전달한 경우 파일을 NTFS의 새 디렉터리에 풀고 PowerShell에서 `requirements.txt`가 있는 디렉터리로 이동한다. 아래 명령은 임시 가상환경과 합성 Small DB를 새 폴더에 만든다. Python 3.13과 프로젝트 의존성 설치 경로가 필요하다.

```powershell
$ErrorActionPreference = 'Stop'
$rcDir = Join-Path $env:TEMP ("studio-rc-" + [guid]::NewGuid())
$null = New-Item -ItemType Directory $rcDir
Start-Transcript -Path (Join-Path $rcDir 'windows-result.txt')
try {
  py -3.13 -m venv (Join-Path $rcDir 'venv')
  if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
  $python = Join-Path $rcDir 'venv/Scripts/python.exe'
  function Check-Python([string[]]$Arguments) {
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python failed ($LASTEXITCODE)" }
  }
  Check-Python @('-c', "import platform,sys; print(platform.platform()); assert sys.platform == 'win32'")
  Check-Python @('-m','pip','install','-r','requirements.txt')
  foreach ($file in @('test_contract_local_paths.py','test_contract_json_pointer.py','test_load_test_mutations.py')) {
    Check-Python @('-m','unittest','discover','-s','tests','-p',$file,'-v')
  }
  Check-Python @('-m','unittest','discover','-s','tests','-p','test_sdk_generation.py','-k','test_bundle_source_windows_unsafe_name_is_rejected_before_archive','-v')
  $fixture = Join-Path $rcDir '경로 검증 100%/fixture'
  Check-Python @('-m','api_test.load_test_harness','generate','--dataset','small','--root',$fixture)
  Check-Python @('-m','api_test.load_test_harness','verify','--root',$fixture)
} finally {
  Stop-Transcript
}
```

결과에는 Windows 버전, 테스트별 성공 여부, fixture 건수·지문·무결성, 실행한 소스 ZIP의 SHA-256을 남긴다. `windows-result.txt`를 확인한 뒤 이번 임시 폴더를 정리한다. 다른 PC가 꺼져 있어 현재 Windows 판정은 대기다.

## 측정 자료와 재현 방법

각 실행의 k6 원본 JSONL, 요약, 서버·k6 로그, 자원 표본, phase와 fixture 검증 결과는 로컬 자료 폴더 `data/load-test-evidence/rc-858f0e9-20261106/`에 실행별로 보존한다. 실행 묶음 21개를 포함한 파일 지문 48개를 `sha256.json`에서 확인할 수 있다. 색인 자체의 SHA-256은 `3d8306c71e119466bebf4deccf43be5daf5a4470190faacb2d04cb7699d18c5d`이다. Git에는 [측정 요약](local-release-validation.json)과 브라우저 화면을 보존한다.

기본 시험은 [격리 하네스](load-test-harness.md)의 기본 시간과 VU를 사용했다. 동일 서버의 Medium 3회 기준선은 `api_test.load_test_baseline repeat-baseline`을 사용했고, 각 Target과 각 저장·실행·회복 시험은 새로운 출력 경로에 실행했다. 추가 2 VU 관측은 후보 checkout에서 `python <자료폴더>/validation/observed-soak.py <Medium-fixture> <새-출력> <k6-실행파일>`로 재현할 수 있다. CPU는 논리 코어 8개 기준의 프로세스 트리 관측값이고 디스크 장치 IOPS·지연은 미수집이다.
