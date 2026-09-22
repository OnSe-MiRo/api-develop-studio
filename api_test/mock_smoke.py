"""Concurrent HTTP load smoke harness for OpenAPI mock server verification."""
from __future__ import annotations
import concurrent.futures
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def send_http_request(url: str, method: str = "GET", payload: Optional[dict] = None, timeout: float = 5.0) -> Tuple[int, float, Optional[str]]:
    start_time = time.perf_counter()
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    status = 0
    error_msg = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            _ = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        _ = exc.read()
    except Exception as exc:
        status = 0
        error_msg = str(exc)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return status, elapsed_ms, error_msg


def run_mock_smoke(
    base_url: str,
    total_requests: int = 100,
    concurrency: int = 10,
    timeout_seconds: float = 10.0,
    deadline_seconds: float = 30.0,
    endpoints: Optional[List[Tuple[str, str, Optional[dict], int]]] = None,
) -> Dict[str, Any]:
    """Execute concurrent HTTP smoke test against the mock server with per-request timeout and global deadline.
    endpoints: list of (method, path, body, expected_status)
    """
    if type(total_requests) is not int or not 1 <= total_requests <= 10000:
        raise ValueError("total_requests must be an integer between 1 and 10000")
    if type(concurrency) is not int or not 1 <= concurrency <= 100:
        raise ValueError("concurrency must be an integer between 1 and 100")
    for value in (timeout_seconds, deadline_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 60:
            raise ValueError("Timeouts must be finite numbers between 0 and 60 seconds")
    clean_base = base_url.rstrip("/")
    if endpoints is None:
        endpoints = [
            ("GET", "/__mock/health", None, 200),
        ]
    if not endpoints:
        raise ValueError("At least one endpoint is required")

    start_all = time.perf_counter()
    latencies: List[float] = []
    success_count = 0
    failure_count = 0
    status_counts: Dict[int, int] = {}
    errors: List[str] = []

    tasks = []
    for i in range(total_requests):
        method, path, body, expected_status = endpoints[i % len(endpoints)]
        url = f"{clean_base}/{path.lstrip('/')}"
        tasks.append((method, url, body, expected_status))

    deadline = start_all + deadline_seconds
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    pending = {}
    submitted = 0
    completed = 0

    def send_before_deadline(method, url, body):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return 0, 0.0, "Global smoke deadline exceeded"
        return send_http_request(url, method, body, min(5.0, timeout_seconds, remaining))

    try:
        while completed < total_requests:
            while submitted < total_requests and len(pending) < concurrency and time.perf_counter() < deadline:
                method, url, body, expected = tasks[submitted]
                pending[executor.submit(send_before_deadline, method, url, body)] = expected
                submitted += 1
            remaining = deadline - time.perf_counter()
            if remaining <= 0 or not pending:
                break
            done, _ = concurrent.futures.wait(pending, timeout=remaining, return_when=concurrent.futures.FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                expected_status = pending.pop(future)
                status, latency_ms, error_msg = future.result()
                completed += 1
                latencies.append(latency_ms)
                status_counts[status] = status_counts.get(status, 0) + 1
                if error_msg or (expected_status is not None and status != expected_status):
                    failure_count += 1
                    if len(errors) < 10:
                        errors.append(error_msg or f"Expected status {expected_status}, got {status}")
                else:
                    success_count += 1
        if completed < total_requests:
            failure_count += total_requests - completed
            if len(errors) < 10:
                errors.append(f"Global smoke deadline ({deadline_seconds}s) exceeded; unfinished requests counted as failures")
    finally:
        for future in pending:
            future.cancel()
        # Do not wait for queued work after the deadline. In-flight requests have
        # bounded socket timeouts and cannot submit further requests.
        executor.shutdown(wait=False, cancel_futures=True)

    total_time = time.perf_counter() - start_all
    sorted_latencies = sorted(latencies) if latencies else [0.0]

    def percentile(p: float) -> float:
        if not sorted_latencies:
            return 0.0
        k = (len(sorted_latencies) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_latencies) - 1)
        d = k - f
        return sorted_latencies[f] + d * (sorted_latencies[c] - sorted_latencies[f])

    rps = total_requests / total_time if total_time > 0 else 0.0

    result = {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "total_time_seconds": round(total_time, 3),
        "rps": round(rps, 2),
        "success_count": success_count,
        "failure_count": failure_count,
        "completed_requests": completed,
        "unfinished_requests": total_requests - completed,
        "status_distribution": status_counts,
        "latency_ms": {
            "min": round(sorted_latencies[0], 2) if sorted_latencies else 0.0,
            "avg": round(statistics.mean(sorted_latencies), 2) if sorted_latencies else 0.0,
            "p50": round(percentile(50), 2),
            "p95": round(percentile(95), 2),
            "p99": round(percentile(99), 2),
            "max": round(sorted_latencies[-1], 2) if sorted_latencies else 0.0,
        },
        "errors": errors,
    }
    return result


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8880"
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    print(f"Running mock smoke: {base_url} (total={total}, concurrency={concurrency})")
    result = run_mock_smoke(base_url, total_requests=total, concurrency=concurrency)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
