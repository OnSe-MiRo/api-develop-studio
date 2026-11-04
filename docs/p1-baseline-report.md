# P1 동일 조건 기준선·회복 진단

이 보고서는 격리된 같은 서버에서 수집한 P1 결과다. 과거 LT-2의 fresh-server 단일 Baseline과 합쳐 중앙값을 계산하지 않는다.

- 상태: passed; mode=repeat-baseline; validation=False
- 동일 서버 PID: 53274; 원본 fixture SHA256: a83c873f2f2961b7a7e20eb7a04a8aa7c4ae5cf781385270d6dcfb49181702a9

- 실행 1: passed, 756요청, 2.437879 RPS, p95 30.2825 ms, case-list trace passed (108건)
- 실행 2: passed, 756요청, 2.437863 RPS, p95 30.8635 ms, case-list trace passed (108건)
- 실행 3: passed, 756요청, 2.437929 RPS, p95 36.12325 ms, case-list trace passed (108건)

**실제 3×300초 실행별 중앙값:** RPS 2.437879, p95 30.8635 ms. Percentile의 원본 표본을 합산하거나 평균하지 않았다.

`/api/cases`의 추적 값은 list_references(connect·query·rows), 경로 확인, 파일 읽기, UTF-8 해독, JSON 파싱, 필드 선택, json_response 직렬화의 handler 내부 exclusive 구간이다. trace 기록·ASGI 전송·네트워크·클라이언트 시간은 제외한다. 서로 다른 구간의 p95를 더하지 않는다.
서버 CPU와 k6 발생기 CPU/RSS는 각각의 현재 관측 가능한 process tree를 논리 CPU 수로 나눈 sample이다. 종료 사이 자식의 CPU, 장치 IOPS/latency와 host 전체 CPU는 미수집이다.
최대 안정 RPS와 지속 안정 run 동시성은 이 P1 기준선 또는 짧은 진단에서 판정하지 않는다. 과거 Target 429·Spike/Stress 회복 실패·Soak unknown을 덮어쓰지 않는다.
