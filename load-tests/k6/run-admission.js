import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";
import { studioHandleSummary } from "./studio-summary.js";
import { validRun } from "./mixed-model.js";

const config = JSON.parse(__ENV.STUDIO_CAMPAIGN_CONFIG);
const runtime = JSON.parse(open(__ENV.STUDIO_RUNTIME_PATH));
const baseUrl = __ENV.STUDIO_BASE_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl || "") || runtime.baseUrl !== baseUrl) throw new Error("admission workload requires the prepared loopback target");
if (!["sustained", "queue"].includes(config.phase) || ![1, 2].includes(config.vus) || !Number.isInteger(config.durationSeconds) || config.durationSeconds < 10 || config.durationSeconds > 120) throw new Error("unsupported bounded admission configuration");
const successes = new Counter("studio_sustained_runs");
const accepted = new Counter("studio_async_accepted");
const queued = new Counter("studio_async_queued");
const running = new Counter("studio_async_running");
const completed = new Counter("studio_async_passed");
const correctnessFailures = new Counter("studio_correctness_failures");
const exitFailures = new Counter("studio_run_exit_failures");
const thresholds = { checks: ["rate==1"], http_req_failed: ["rate==0"] };
if (config.phase === "sustained") {
  thresholds.studio_sustained_runs = [`count>=${2 * config.vus}`];
} else {
  thresholds.studio_async_accepted = ["count==5"];
  thresholds.studio_async_passed = ["count==5"];
  thresholds.studio_async_queued = ["count>=1"];
  thresholds.studio_async_running = ["count>=1"];
}
export const options = { scenarios: { workload: config.phase === "sustained"
  ? { executor: "constant-vus", vus: config.vus, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: "sustained" }
  : { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "30s", gracefulStop: "5s", exec: "queueBatch" } }, thresholds,
  batch: 5, batchPerHost: 5, systemTags: ["method", "status", "name", "scenario", "expected_response"] };
export function setup() { accepted.add(0); queued.add(0); running.add(0); completed.add(0); correctnessFailures.add(0); exitFailures.add(0); }
function params(name) { return { tags: { name }, headers: { "Content-Type": "application/json" }, timeout: "5s", redirects: 0 }; }
function body(response) { try { return response.json(); } catch (_) { return null; } }
function verify(correct, label) {
  check(correct, { [label]: (value) => value === true });
  if (!correct) correctnessFailures.add(1);
  return correct;
}
export function sustained() {
  const response = http.post(baseUrl + "/api/run", JSON.stringify({ cases: [runtime.runCase] }), { ...params("/api/run"), timeout: "10s" });
  const parsed = body(response);
  const correct = validRun(response, parsed, runtime.runCase) && parsed.result.runId === parsed.runId;
  if (verify(correct, "sustained saved case passed")) successes.add(1, { vu: String(__VU) });
  if (response.status === 200 && parsed && parsed.exitCode !== 0) exitFailures.add(1);
  sleep(.1);
}
export function queueBatch() {
  // Exactly five explicit submissions; never resubmit after a failure or an ambiguous response.
  const responses = http.batch(Array.from({ length: 5 }, () => ({ method: "POST", url: baseUrl + "/api/runs",
    body: JSON.stringify({ cases: [runtime.runCase] }), params: params("/api/runs") })));
  const pending = new Set();
  for (const response of responses) {
    const parsed = body(response);
    const correct = response.status === 202 && parsed && typeof parsed.runId === "string"
      && /^[a-f0-9-]{36}$/.test(parsed.runId) && ["queued", "running"].includes(parsed.status) && !pending.has(parsed.runId);
    if (verify(!!correct, "async unique accepted job")) {
      accepted.add(1);
      pending.add(parsed.runId);
    }
  }
  const deadline = Date.now() + 15000;
  while (pending.size && Date.now() < deadline) {
    for (const runId of Array.from(pending)) {
      const response = http.get(baseUrl + `/api/runs/${runId}`, params("/api/runs/{runId}"));
      const parsed = body(response);
      if (!verify(response.status === 200 && !!parsed && parsed.runId === runId, "async existing job lookup")) { pending.delete(runId); continue; }
      if (parsed.status === "queued") { queued.add(1); continue; }
      if (parsed.status === "running") { running.add(1); continue; }
      const correct = parsed.status === "passed" && parsed.result && parsed.result.runId === runId && validRun(response, parsed, runtime.runCase);
      if (verify(!!correct, "async terminal saved case passed")) completed.add(1);
      if (parsed.exitCode !== 0) exitFailures.add(1);
      pending.delete(runId);
    }
    if (pending.size) sleep(.1);
  }
  verify(pending.size === 0, "all accepted jobs reached terminal state within deadline");
}
export { studioHandleSummary as handleSummary };
