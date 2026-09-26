const startedAt = new Date().toISOString();

function environment() {
  return globalThis.__ENV || {};
}

function required(name) {
  const value = environment()[name];
  if (!value) {
    throw new Error(`${name} is required for the Studio load-test summary`);
  }
  return value;
}

function optional(name) {
  return environment()[name] || null;
}

function thresholdResults(data) {
  const metrics = [];
  if (data && data.metrics && !Array.isArray(data.metrics)) {
    for (const [name, metric] of Object.entries(data.metrics)) {
      metrics.push({ name, ...metric });
    }
  }
  if (data && data.results && Array.isArray(data.results.metrics)) {
    metrics.push(...data.results.metrics);
  }
  const results = [];
  for (const metric of metrics) {
    if (!metric || !metric.name || !metric.thresholds || Array.isArray(metric.thresholds)) {
      continue;
    }
    for (const [condition, verdict] of Object.entries(metric.thresholds)) {
      if (verdict && typeof verdict.ok === "boolean") {
        results.push({ metric: metric.name, condition, passed: verdict.ok });
      }
    }
  }
  return results;
}

function k6Version(data) {
  return optional("STUDIO_K6_VERSION")
    || (data && data.metadata && (data.metadata.k6Version || data.metadata.k6_version))
    || null;
}

export function studioHandleSummary(data) {
  const thresholds = thresholdResults(data);
  const requestedStatus = environment().STUDIO_STATUS;
  const status = requestedStatus || (thresholds.some((item) => !item.passed) ? "failed" : "passed");
  const memory = optional("STUDIO_MEMORY_MB");
  const memoryMb = memory === null ? null : Number(memory);
  if (memoryMb !== null && (!Number.isFinite(memoryMb) || memoryMb < 0)) {
    throw new Error("STUDIO_MEMORY_MB must be a non-negative number");
  }
  const manifest = {
    formatVersion: 1,
    run: {
      id: required("STUDIO_RUN_ID"),
      project: required("STUDIO_PROJECT"),
      scenario: required("STUDIO_SCENARIO"),
      startedAt,
      endedAt: new Date().toISOString(),
      status,
      appVersion: optional("STUDIO_APP_VERSION"),
      commitSha: optional("STUDIO_COMMIT_SHA"),
      environment: {
        os: environment().STUDIO_OS || "unknown",
        cpu: environment().STUDIO_CPU || "unknown",
        memoryMb,
        executionMode: environment().STUDIO_EXECUTION_MODE || "local",
        k6Version: k6Version(data),
      },
    },
    thresholds,
  };
  return {
    [environment().STUDIO_SUMMARY_PATH || "studio-summary.json"]: `${JSON.stringify(manifest, null, 2)}\n`,
  };
}
