import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import { Counter } from "k6/metrics";
import { studioHandleSummary } from "./studio-summary.js";
import { configuration, endpoints, fixtureIndex, selection, thinkSeconds, requestSpec, validBody } from "./read-model.js";

const config = configuration(__ENV.STUDIO_READ_MODE, __ENV.STUDIO_DURATION_SECONDS);
const fixture = new SharedArray("read fixture", () => [JSON.parse(open(__ENV.STUDIO_FIXTURE_PATH))])[0];
const index = fixtureIndex(fixture);
const baseUrl = __ENV.STUDIO_BASE_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl || "")) throw new Error("read scenarios require the isolated loopback target");
const counters = endpoints.map((endpoint) => new Counter(`studio_read_${endpoint}_requests`));
const thresholds = {
  checks: [{ threshold: "rate==1", abortOnFail: true, delayAbortEval: "5s" }],
  http_req_failed: [{ threshold: "rate==0", abortOnFail: true, delayAbortEval: "5s" }],
};
endpoints.forEach((endpoint) => { thresholds[`studio_read_${endpoint}_requests`] = ["count>=1"]; });
const scenarios = {};
if (config.mode === "smoke") {
  endpoints.forEach((endpoint) => { scenarios[endpoint] = { executor: "constant-vus", vus: 1, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: endpoint }; });
} else {
  scenarios.baseline = { executor: "constant-vus", vus: 5, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: "baseline" };
}
export const options = { scenarios, thresholds, systemTags: ["method", "status", "name", "scenario", "expected_response"] };

export function setup() {
  // Declare all coverage counters even if a bounded/aborted run stops mid-flow.
  counters.forEach((counter) => counter.add(0));
}

function read(endpoint, selected) {
  const spec = requestSpec(endpoint, selected);
  const response = http.get(baseUrl + spec.path, { tags: { name: spec.name }, timeout: "5s", redirects: 0 });
  let body = null;
  try { body = response.json(); } catch (_) { /* Non-JSON responses fail the semantic check. */ }
  check(response, {
    [`${spec.name}: status`]: (value) => value.status === 200,
    [`${spec.name}: body`]: () => validBody(endpoint, body, selected, fixture),
  });
  counters[endpoint].add(1);
  sleep(thinkSeconds(fixture.seed, __ITER, __VU, endpoint));
}

function smoke(endpoint) { read(endpoint, selection(index, __ITER, 1)); }
export function health() { smoke(0); }
export function projects() { smoke(1); }
export function cases() { smoke(2); }
export function pipelines() { smoke(3); }
export function project() { smoke(4); }
export function caseRead() { smoke(5); }
export function revisions() { smoke(6); }
// "case" is a reserved JavaScript keyword, so map that scenario to caseRead.
if (scenarios.case) scenarios.case.exec = "caseRead";
export function baseline() {
  const selected = selection(index, __ITER, __VU, 5);
  for (let endpoint = 0; endpoint < endpoints.length; endpoint += 1) read(endpoint, selected);
}
export { studioHandleSummary as handleSummary };
