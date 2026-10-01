"""Incremental client stop gates and nullable live-server resource sampling."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def cpu_seconds(value):
    days, _, clock = value.rpartition("-")
    parts = [float(part) for part in (clock or value).split(":")]
    if len(parts) not in (2, 3):
        raise ValueError("unsupported process CPU clock")
    seconds = parts[-1] + parts[-2] * 60
    if len(parts) == 3:
        seconds += parts[0] * 3600
    return seconds + (int(days) * 86400 if days else 0)


class RawTail:
    def __init__(self, path: Path, window_seconds=60):
        self.path, self.window_seconds, self.offset = path, window_seconds, 0
        self.requests = deque()
        self.run_failures = deque()
        self.statuses = {}
        self.run_exit_failures = self.capacity429 = self.fault_observations = self.correctness_failures = 0

    def poll(self, now):
        if self.path.exists():
            with self.path.open() as source:
                source.seek(self.offset)
                while True:
                    position = source.tell()
                    line = source.readline()
                    if not line or not line.endswith("\n"):
                        source.seek(position)
                        break
                    try:
                        event = json.loads(line)
                    except ValueError as exc:
                        raise ValueError("client raw stream contains invalid complete JSON") from exc
                    if event.get("type") == "Point":
                        data = event["data"]
                        timestamp = datetime.fromisoformat(data["time"].replace("Z", "+00:00")).timestamp()
                        metric = event.get("metric")
                        if metric == "http_req_failed":
                            status = int((data.get("tags") or {}).get("status", "0"))
                            self.statuses[str(status)] = self.statuses.get(str(status), 0) + 1
                            self.capacity429 += int(status == 429 and (data.get("tags") or {}).get("name") == "/api/run")
                            self.requests.append((timestamp, status == 0 or status >= 500))
                        elif metric == "studio_run_exit_failures":
                            value = int(data["value"])
                            self.run_exit_failures += value
                            if value:
                                self.run_failures.append((timestamp, value))
                        elif metric == "studio_correctness_failures":
                            self.correctness_failures += int(data["value"])
                        elif metric == "studio_fault_observations":
                            self.fault_observations += int(data["value"])
                    self.offset = source.tell()
        cutoff = now - self.window_seconds
        while self.requests and self.requests[0][0] < cutoff:
            self.requests.popleft()
        while self.run_failures and self.run_failures[0][0] < cutoff:
            self.run_failures.popleft()
        return {"windowRequests": len(self.requests), "networkOr5xxRate": sum(value for _, value in self.requests) / len(self.requests) if self.requests else None,
                "runExitFailures": self.run_exit_failures, "capacity429": self.capacity429, "httpStatuses": dict(self.statuses), "faultObservations": self.fault_observations, "correctnessFailures": self.correctness_failures}


class StopPolicy:
    def __init__(self, started, window_seconds=60, sustain_seconds=120):
        self.started, self.window_seconds, self.sustain_seconds = started, window_seconds, sustain_seconds
        self.exceeded_since = {"cpu": None, "memory": None}

    def evaluate(self, now, client, resource):
        if client.get("correctnessFailures", 0):
            return "semantic_correctness_failure"
        if client.get("capacity429", 0):
            return "run_capacity_limit_429_before_further_increase"
        if now - self.started >= self.window_seconds and client.get("networkOr5xxRate") is not None and client["networkOr5xxRate"] > .05:
            return "network_or_5xx_rate_above_5_percent_in_full_window"
        for name, field, limit in (("cpu", "cpuPercent", 95), ("memory", "memoryPercent", 90)):
            value = resource.get(field)
            if value is None or value <= limit:
                self.exceeded_since[name] = None
            elif self.exceeded_since[name] is None:
                self.exceeded_since[name] = now
            elif now - self.exceeded_since[name] >= self.sustain_seconds:
                return f"{name}_above_limit_for_sustained_interval"
        return None


class ResourceSampler:
    def __init__(self, pid, root: Path, memory_mb=None):
        self.pid, self.root, self.memory_mb = pid, root, memory_mb
        self.last_at = None
        self.last_cpu = {}

    def sample(self):
        now = time.monotonic()
        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "cpuPercent": None, "memoryMb": None, "memoryPercent": None,
                  "threads": None, "handles": None, "childProcesses": None, "dbBytes": None, "walBytes": None,
                  "diskIops": None, "diskLatencyMs": None, "cpuScope": "sampled live server tree / logical host CPUs", "threadHandleScope": "server process", "warnings": []}
        try:
            rows = subprocess.run(["ps", "-axo", "pid=,ppid=,rss=,time="], capture_output=True, text=True, timeout=2, check=True).stdout.splitlines()
            processes = {}
            for line in rows:
                parts = line.split()
                if len(parts) == 4:
                    processes[int(parts[0])] = (int(parts[1]), int(parts[2]), cpu_seconds(parts[3]))
            if self.pid not in processes:
                raise ValueError("server process is not observable")
            tree = {self.pid}
            while True:
                extended = tree | {pid for pid, (parent, _, _) in processes.items() if parent in tree}
                if extended == tree:
                    break
                tree = extended
            cpu = {pid: processes[pid][2] for pid in tree}
            if self.last_at is not None and os.cpu_count():
                elapsed = now - self.last_at
                delta = sum(max(0, value - self.last_cpu.get(pid, 0)) for pid, value in cpu.items())
                result["cpuPercent"] = min(100, delta / elapsed / os.cpu_count() * 100) if elapsed > 0 else None
            self.last_cpu, self.last_at = cpu, now
            result["memoryMb"] = sum(processes[pid][1] for pid in tree) / 1024
            result["memoryPercent"] = result["memoryMb"] / self.memory_mb * 100 if self.memory_mb else None
            result["childProcesses"] = len(tree) - 1
            proc = Path(f"/proc/{self.pid}")
            if proc.exists():
                result["threads"] = len(list((proc / "task").iterdir()))
                result["handles"] = len(list((proc / "fd").iterdir()))
            else:
                threads = subprocess.run(["ps", "-M", "-p", str(self.pid)], capture_output=True, text=True, timeout=2, check=True).stdout.splitlines()
                result["threads"] = len(threads) - 1 if len(threads) > 1 else None
                if shutil.which("lsof"):
                    handles = subprocess.run(["lsof", "-a", "-p", str(self.pid), "-F", "f"], capture_output=True, text=True, timeout=2).stdout.splitlines()
                    result["handles"] = len({line for line in handles if re.match(r"^f\d+", line)}) if handles else None
        except (OSError, ValueError, subprocess.SubprocessError):
            result["warnings"].append("some process resource metrics are unavailable")
        database = self.root / "data/studio.db"
        try:
            result["dbBytes"] = database.stat().st_size
        except FileNotFoundError:
            pass
        wal = Path(str(database) + "-wal")
        try:
            result["walBytes"] = wal.stat().st_size
        except FileNotFoundError:
            result["walBytes"] = 0 if result["dbBytes"] is not None else None
        try:
            result["tempEntries"] = sum(1 for _ in (self.root / "tmp").rglob("*")) if (self.root / "tmp").exists() else None
        except FileNotFoundError:
            result["tempEntries"] = None
        result["logFiles"] = sum(1 for _ in (self.root / "logs").rglob("*.log")) if (self.root / "logs").exists() else None
        result["warnings"].append("disk IOPS/latency and children exiting between samples are not measured")
        return result


def within_baseline(before, after, factor=1.2, absolute_zero=False):
    if before is None or after is None:
        return "unknown"
    if before == 0:
        return "passed" if after == 0 else "failed" if absolute_zero else "unknown"
    return "passed" if after <= before * factor else "failed"


def recovery_report(before, after, before_resources, after_resources):
    fields = {"p95Ms": (before.get("summary", {}).get("latencyMs", {}).get("p95"), after.get("summary", {}).get("latencyMs", {}).get("p95")),
              "errorRate": (before.get("summary", {}).get("errorRate"), after.get("summary", {}).get("errorRate"))}
    for field in ("cpuPercent", "memoryMb", "threads", "handles", "childProcesses"):
        fields[field] = (before_resources.get(field), after_resources.get(field))
    verdicts = {field: {"before": values[0], "after": values[1], "verdict": within_baseline(*values, absolute_zero=field in ("errorRate", "childProcesses"))} for field, values in fields.items()}
    states = [item["verdict"] for item in verdicts.values()]
    return {"comparison": verdicts, "status": "failed" if "failed" in states else "unknown" if "unknown" in states else "passed", "factor": 1.2}


def aggregate_resources(samples):
    fields = ("cpuPercent", "memoryMb", "threads", "handles", "childProcesses")
    return {field: sum(values) / len(values) if values else None for field in fields for values in [[sample[field] for sample in samples if sample.get(field) is not None]]}


def growth_report(samples):
    result = {}
    for field in ("memoryMb", "threads", "walBytes", "logFiles"):
        values = [sample[field] for sample in samples if sample.get(field) is not None]
        result[field] = {"samples": len(values), "first": values[0] if values else None, "last": values[-1] if values else None,
                         "delta": values[-1] - values[0] if values else None,
                         "continuouslyIncreasing": all(current >= previous for previous, current in zip(values, values[1:])) and values[-1] > values[0] if len(values) >= 3 else None}
    return {"metrics": result, "interpretation": "observed sample trend only; short validation cannot establish2-hourSoak stability"}


def stable_resource_window(samples, window_seconds):
    if not samples:
        return aggregate_resources([])
    end = datetime.fromisoformat(samples[-1]["timestamp"]).timestamp()
    return aggregate_resources([sample for sample in samples if datetime.fromisoformat(sample["timestamp"]).timestamp() >= end - window_seconds])
