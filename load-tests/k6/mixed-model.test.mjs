import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const readSource = await readFile(new URL("./read-model.js", import.meta.url), "utf8");
const readUrl = `data:text/javascript;base64,${Buffer.from(readSource).toString("base64")}`;
const source = (await readFile(new URL("./mixed-model.js", import.meta.url), "utf8")).replace("./read-model.js", readUrl);
const { categories, weights, targetConfiguration, targetOptions, operationBlock, operation, document, validSave, validConflict, validRun } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
let tests = 0;
function test(name, callback) { callback(); tests += 1; console.log(`${name}: passed`); }

test("Target holds20VU600s then switches instantly to50VU600s", () => {
  const config = targetConfiguration();
  assert.deepEqual(config.stageVus, [20, 50]);
  assert.deepEqual(targetOptions(config).stages, [{ duration: "600s", target: 20 }, { duration: "0s", target: 50 }, { duration: "600s", target: 50 }]);
  assert.equal(targetOptions(config).gracefulRampDown, "0s");
  assert.deepEqual(targetConfiguration("40", "2").stageVus, [1, 2]);
  for (const seconds of [1, 3, 1202, "NaN"]) assert.throws(() => targetConfiguration(seconds));
  assert.throws(() => targetConfiguration(undefined, "2"));
});
test("Completed blocks have exact HTTP weights and separate preparation traffic", () => {
  const block = operationBlock(42, 1, 0);
  assert.equal(block.length, 177);
  const costs = { list: 1, single: 1, revision: 1, unique: 4, contention: 5, run: 1 };
  const http = Object.fromEntries(categories.map((category) => [category, block.filter((item) => item === category).length * costs[category]]));
  assert.equal(Object.values(http).reduce((sum, count) => sum + count, 0), 200);
  for (const category of categories) assert.equal(http[category] / 200, weights[category] / 100);
  assert.equal(block.filter((item) => item === "contention").length, 2); // Two additional preparation PUTs are support traffic.
});
test("Short validation covers all categories and shuffle is deterministic", () => {
  assert.deepEqual(Array.from({ length: 6 }, (_, iteration) => operation(42, 1, iteration)), categories);
  assert.equal(new Set(Array.from({ length: 6 }, (_, vu) => operation(42, vu + 1, 0))).size, 6);
  assert.deepEqual(operationBlock(42, 2, 1), operationBlock(42, 2, 1));
  assert.notDeepEqual(operationBlock(42, 2, 1), operationBlock(43, 2, 1));
});
test("Unique revisions change content while staying within1KiB body", () => {
  const first = document("load-test/project-000.json", 42, "unique", 1, 0, 1);
  const fourth = document("load-test/project-000.json", 42, "unique", 1, 0, 4);
  assert.equal(JSON.stringify(first.request.body).length, 1024);
  assert.equal(first.loadTest.step, 1);
  assert.equal(fourth.loadTest.step, 4);
  assert.notDeepEqual(first, fourth);
  assert.ok(!Object.hasOwn(first, "_storage"));
});
test("Save validation rejects409 and wrong path or revision", () => {
  const path = "load-test/write/unique-vu-1-iteration-0.json";
  const body = { path: `case/${path}`, _storage: { revision: 4 } };
  assert.ok(validSave({ status: 200 }, body, path, 4));
  assert.equal(validSave({ status: 409 }, body, path, 4), false);
  assert.equal(validSave({ status: 200 }, body, path, 3), false);
  assert.equal(validSave({ status: 200 }, body, "wrong", 4), false);
});
test("Expected409 requires exact current revision and error body", () => {
  assert.ok(validConflict({ status: 409 }, { currentRevision: 2, error: "conflict" }, 2));
  assert.equal(validConflict({ status: 409 }, { currentRevision: 3, error: "conflict" }, 2), false);
  assert.equal(validConflict({ status: 500 }, { currentRevision: 2, error: "conflict" }, 2), false);
  assert.equal(validConflict({ status: 409 }, null, 2), false);
});
test("Run validatesexitCode and exact saved target;429 remainsfailure", () => {
  const runCase = "load-test/runtime/health.json";
  const body = { runId: "run", exitCode: 0, result: { status: "passed", exitCode: 0, targets: [{ caseReference: runCase, status: "passed", httpStatus: 200 }] } };
  assert.ok(validRun({ status: 200 }, body, runCase));
  assert.equal(validRun({ status: 429 }, body, runCase), false);
  assert.equal(validRun({ status: 200 }, { ...body, exitCode: 1 }, runCase), false);
  assert.equal(validRun({ status: 200 }, body, "different-case.json"), false);
});
console.log(`mixed-model regressions: ${tests} passed`);
