import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";
const readSource = await readFile(new URL("./read-model.js", import.meta.url), "utf8");
const readUrl = `data:text/javascript;base64,${Buffer.from(readSource).toString("base64")}`;
const model = (await readFile(new URL("./mixed-model.js", import.meta.url), "utf8")).replace("./read-model.js", readUrl);
const { validRun } = await import(`data:text/javascript;base64,${Buffer.from(model).toString("base64")}`);
const source = (await readFile(new URL("./run-admission.js", import.meta.url), "utf8"))
  .replace(/^import .*;$/gm, "").replace(/^export \{.*;$/gm, "").replace(/export /g, "");
function fixture(phase, overrides = {}) {
  const runtime = { baseUrl: "http://127.0.0.1:1234", runCase: "load-test/runtime/health.json" };
  let clock = 0, submitted = 0, polled = 0;
  const values = {}, checks = [], attempts = new Map();
  const payload = (runId, status = "passed") => ({ runId, status, exitCode: 0, result: { runId, status: "passed", exitCode: 0,
    targets: [{ caseReference: runtime.runCase, status: "passed", httpStatus: 200 }] } });
  const response = (status, data) => ({ status, json: () => data });
  const context = vm.createContext({ __ENV: { STUDIO_BASE_URL: runtime.baseUrl, STUDIO_RUNTIME_PATH: "runtime.json",
    STUDIO_CAMPAIGN_CONFIG: JSON.stringify({ phase, vus: 2, durationSeconds: 10, ...overrides }) }, __VU: 1,
    open: () => JSON.stringify(runtime), Date: { now: () => clock }, sleep: (seconds) => { clock += seconds * 1000; }, validRun,
    check: (value, conditions) => { checks.push(...Object.values(conditions).map((predicate) => predicate(value))); },
    Counter: class { constructor(name) { this.name = name; } add(value) { values[this.name] = (values[this.name] || 0) + value; } },
    http: { post: () => response(200, payload("sync-id")),
      batch: (requests) => { submitted += requests.length; return requests.map((_, index) => response(202, { runId: `${index}`.padStart(36, "0"), status: "queued" })); },
      get: (url) => { polled += 1; const id = url.split("/").at(-1); const count = (attempts.get(id) || 0) + 1; attempts.set(id, count);
        return response(200, payload(id, count === 1 ? "queued" : count === 2 ? "running" : "passed")); } },
  });
  vm.runInContext(source, context);
  return { context, values, checks, payload, response, counts: () => ({ submitted, polled }) };
}
let tests = 0;
function test(name, callback) { callback(); tests += 1; console.log(`${name}: passed`); }
test("finite duration and VU limits", () => {
  for (const change of [{ durationSeconds: 9 }, { durationSeconds: 121 }, { durationSeconds: 10.5 }, { vus: 5 }]) assert.throws(() => fixture("sustained", change));
});
test("sync logical success rejects mismatched report run ID", () => {
  const f = fixture("sustained"); f.context.sustained(); assert.equal(f.values.studio_sustained_runs, 1);
  f.context.http.post = () => f.response(200, { ...f.payload("sync-id"), result: f.payload("different").result });
  f.context.sustained(); assert.equal(f.values.studio_sustained_runs, 1); assert.equal(f.values.studio_correctness_failures, 1);
});
test("five explicit queue jobs are polled through actual queued and running observations", () => {
  const f = fixture("queue"); f.context.queueBatch(); assert.deepEqual(f.counts(), { submitted: 5, polled: 15 });
  for (const metric of ["accepted", "queued", "running", "passed"]) assert.equal(f.values[`studio_async_${metric}`], 5);
  assert.ok(f.checks.every(Boolean));
});
test("ambiguous submission never triggers retries or polling unknown ID", () => {
  const f = fixture("queue"); let calls = 0;
  f.context.http.batch = (requests) => { calls += requests.length; return requests.map(() => f.response(0, null)); };
  f.context.queueBatch(); assert.equal(calls, 5); assert.equal(f.counts().polled, 0); assert.equal(f.values.studio_correctness_failures, 5);
});
test("stuck accepted jobs have bounded polling and no resubmission", () => {
  const f = fixture("queue"); f.context.http.get = (url) => f.response(200, f.payload(url.split("/").at(-1), "queued"));
  f.context.queueBatch(); assert.equal(f.counts().submitted, 5); assert.equal(f.values.studio_async_passed || 0, 0); assert.equal(f.values.studio_correctness_failures, 1);
});
console.log(`admission workload:${tests} tests passed`);
