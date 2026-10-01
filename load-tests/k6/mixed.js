import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import { Counter } from "k6/metrics";
import { studioHandleSummary } from "./studio-summary.js";
import { fixtureIndex, requestSpec, validBody, thinkSeconds } from "./read-model.js";
import { campaignOptions } from "./campaign-model.js";
import { categories, targetConfiguration, targetOptions, operation, selected, reference, document, validSave, validConflict, validRun } from "./mixed-model.js";

const mode = __ENV.STUDIO_MUTATION_MODE;
const campaign = __ENV.STUDIO_CAMPAIGN_CONFIG ? JSON.parse(__ENV.STUDIO_CAMPAIGN_CONFIG) : null;
if (!["target", "unique", "contention"].includes(mode)) throw new Error("unsupported mutation workload");
const fixture = new SharedArray("mutation fixture", () => [JSON.parse(open(__ENV.STUDIO_FIXTURE_PATH))])[0];
const index = fixtureIndex(fixture);
const runtime = mode === "target" ? JSON.parse(open(__ENV.STUDIO_RUNTIME_PATH)) : null;
const baseUrl = __ENV.STUDIO_BASE_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl || "")) throw new Error("mutation workloads require the isolated loopback target");
const concurrency = Number(__ENV.STUDIO_CONTENTION_REQUESTS || 5);
const vus = Number(__ENV.STUDIO_CONFIGURED_VUS);
const stride = Number(__ENV.STUDIO_SELECTION_STRIDE);
if (![5, 20, 50].includes(concurrency)) throw new Error("contention requests must be5,20or50");
const counters = {};
for (const category of [...categories, "support"]) counters[category] = new Counter(`studio_mix_${category}_requests`);
const conflicts = new Counter("studio_expected_conflicts");
const correctnessFailures = new Counter("studio_correctness_failures");
const exitFailures = new Counter("studio_run_exit_failures");
const faultObservations = new Counter("studio_fault_observations");
const thresholds = {
  checks: [{ threshold: "rate==1", abortOnFail: true, delayAbortEval: "5s" }],
  http_req_failed: [{ threshold: "rate<0.01", abortOnFail: true, delayAbortEval: "5s" }],
};
if (campaign) {
  thresholds.checks = ["rate==1"];
  thresholds.http_req_failed = ["rate<0.01"];
}
const required = campaign ? campaign.phase === "baseline" ? ["list", "single", "revision"] : campaign.phase === "run" || campaign.phase === "fault" ? ["run"] : categories : mode === "target" ? categories : [mode];
for (const category of required) thresholds[`studio_mix_${category}_requests`] = ["count>=1"];
let scenario;
if (mode === "target") {
  const config = targetConfiguration(__ENV.STUDIO_TARGET_VALIDATION_SECONDS, __ENV.STUDIO_TARGET_VALIDATION_VUS);
  scenario = targetOptions(config);
} else if (mode === "unique") {
  scenario = { executor: "per-vu-iterations", vus, iterations: 1, maxDuration: "60s", gracefulStop: "10s", exec: "unique" };
} else {
  scenario = { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "30s", gracefulStop: "10s", exec: "contention" };
}
if (campaign) scenario = campaignOptions(campaign);
export const options = { scenarios: { workload: scenario }, thresholds, batch: 50, batchPerHost: 50,
  systemTags: ["method", "status", "name", "scenario", "expected_response"] };
export function setup() { for (const counter of Object.values(counters)) counter.add(0); conflicts.add(0); exitFailures.add(0); faultObservations.add(0); correctnessFailures.add(0); }
function body(response) { try { return response.json(); } catch (_) { return null; } }
function params(name) { return { tags: { name }, headers: { "Content-Type": "application/json" }, timeout: "5s", redirects: 0 }; }
function save(path, payload, expectedRevision, category) {
  const response = http.put(baseUrl + `/api/cases/${path}`, JSON.stringify(payload), params("/api/cases/{id}"));
  const parsed = body(response);
  const correct = validSave(response, parsed, path, expectedRevision);
  check(response, { "write status/revision/path": () => correct });
  if (!correct) correctnessFailures.add(1);
  counters[category].add(1);
  return correct ? parsed._storage.revision : null;
}
function uniqueFlow(chosen) {
  const path = reference("unique", __VU, __ITER);
  let revision = save(path, document(chosen.project, fixture.seed, "unique", __VU, __ITER, 1), 1, "unique");
  for (let step = 2; step <= 4 && revision !== null; step += 1) {
    const payload = document(chosen.project, fixture.seed, "unique", __VU, __ITER, step);
    payload._storage = { revision };
    revision = save(path, payload, step, "unique");
  }
  check(revision, { "unique created and updated three times": (value) => value === 4 });
}
function contentionFlow(chosen) {
  const path = reference("contention", __VU, __ITER);
  const baseline = save(path, document(chosen.project, fixture.seed, "contention", __VU, __ITER, 1), 1, "support");
  if (baseline === null) return;
  const requests = Array.from({ length: concurrency }, (_, request) => {
    const payload = document(chosen.project, fixture.seed, "contention", __VU, __ITER, 2, request + 1);
    payload._storage = { revision: baseline };
    return { method: "PUT", url: baseUrl + `/api/cases/${path}`, body: JSON.stringify(payload),
      params: { ...params("/api/cases/{id}"), responseCallback: http.expectedStatuses(200, 409) } };
  });
  const responses = http.batch(requests);
  let successes = 0;
  let expectedConflicts = 0;
  for (const response of responses) {
    const parsed = body(response);
    const success = validSave(response, parsed, path, baseline + 1);
    const conflict = validConflict(response, parsed, baseline + 1);
    check(response, { "contention success or current revision conflict": () => success || conflict });
    if (!success && !conflict) correctnessFailures.add(1);
    if (success) successes += 1;
    if (conflict) expectedConflicts += 1;
  }
  counters.contention.add(responses.length);
  conflicts.add(expectedConflicts);
  if (successes !== 1 || expectedConflicts !== concurrency - 1) correctnessFailures.add(1);
  check(responses, { "one winner and all other requests conflict": () => successes === 1 && expectedConflicts === concurrency - 1 });
}
function validList(endpoint, parsed, chosen) {
  if (!parsed || !Array.isArray(parsed.items)) return false;
  const original = endpoint === 1 ? fixture.projects : endpoint === 2 ? chosen.caseReferences : chosen.pipelineReferences;
  if (!original.every((item) => parsed.items.includes(item)) || new Set(parsed.items).size !== parsed.items.length) return false;
  return parsed.items.every((item) => original.includes(item) || (endpoint === 1 && item === runtime.runProject)
    || (endpoint === 2 && /^load-test\/write\/(unique|contention)-vu-\d+-iteration-\d+\.json$/.test(item)));
}
function readEndpoint(endpoint, category, chosen) {
  const spec = requestSpec(endpoint, chosen);
  const response = http.get(baseUrl + spec.path, params(spec.name));
  const parsed = body(response);
  const correct = response.status === 200 && (endpoint >= 1 && endpoint <= 3 ? validList(endpoint, parsed, chosen) : validBody(endpoint, parsed, chosen, fixture));
  if (!correct) correctnessFailures.add(1);
  check(response, { "read status": (value) => value.status === 200,
    "read semantic body": () => endpoint >= 1 && endpoint <= 3 ? validList(endpoint, parsed, chosen) : validBody(endpoint, parsed, chosen, fixture) });
  counters[category].add(1);
}
function read(category, chosen) {
  readEndpoint(category === "list" ? 1 + (__ITER % 3) : category === "single" ? 4 + (__ITER % 2) : 6, category, chosen);
}
function runCase(expectedFault = null) {
  const response = http.post(baseUrl + "/api/run", JSON.stringify({ cases: [runtime.runCase] }), { ...params("/api/run"), timeout: "10s" });
  const parsed = body(response);
  const observedFault = response.status === 200 && parsed && parsed.exitCode !== 0 && parsed.result
    && (expectedFault === "delay" ? parsed.result.status === "timeout" && Array.isArray(parsed.result.targets) && parsed.result.targets.some((item) => item.errorCategory === "request_timeout") : expectedFault === "error" ? parsed.result.status === "failed" : false);
  if (!(expectedFault ? observedFault : validRun(response, parsed, runtime.runCase)) && response.status !== 429) correctnessFailures.add(1);
  check(response, { "saved isolated case result": () => expectedFault ? !!observedFault : validRun(response, parsed, runtime.runCase) });
  exitFailures.add(response.status === 200 && parsed && parsed.exitCode !== 0 ? 1 : 0);
  if (expectedFault && observedFault) faultObservations.add(1);
  counters.run.add(1);
}
export function baselineRead() {
  const chosen = selected(index, __ITER, __VU, 5);
  for (let endpoint = 0; endpoint < 7; endpoint += 1) {
    readEndpoint(endpoint, endpoint === 0 ? "support" : endpoint <= 3 ? "list" : endpoint <= 5 ? "single" : "revision", chosen);
    sleep(thinkSeconds(fixture.seed, __ITER, __VU, endpoint));
  }
}
export function runOnce() { runCase(); sleep(1.1); }
export function faultOnce() {
  const response = http.get(baseUrl + runtime.runPath, params("/__load_test__/health"));
  check(response, { "controlled stub response": (value) => value.status === (campaign.fault === "error" ? 500 : 200) });
  counters.support.add(1);
  runCase(campaign.fault);
  sleep(1);
}
export function unique() { uniqueFlow(selected(index, __ITER, __VU, stride)); sleep(1.1); }
export function contention() { contentionFlow(selected(index, __ITER, __VU, stride)); sleep(1.1); }
export function mixed() {
  const chosen = selected(index, __ITER, __VU, stride);
  const category = operation(fixture.seed, __VU, __ITER);
  if (["list", "single", "revision"].includes(category)) read(category, chosen);
  else if (category === "unique") uniqueFlow(chosen);
  else if (category === "contention") contentionFlow(chosen);
  else runCase();
  sleep(thinkSeconds(fixture.seed, __ITER, __VU, categories.indexOf(category)));
}
export { studioHandleSummary as handleSummary };
