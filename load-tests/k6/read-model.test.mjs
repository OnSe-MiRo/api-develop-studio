import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./read-model.js", import.meta.url), "utf8");
const { configuration, fixtureIndex, selection, thinkSeconds, requestSpec, validBody } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const fixture = {
  seed: 42,
  projects: ["load-test/project-000.json", "load-test/project-001.json"],
  cases: [0, 1, 2, 3].map((number) => ({ reference: `load-test/health/case-${number}.json`, project: `load-test/project-00${number % 2}.json`, bodyBytes: 1024, revision: 3 })),
  pipelines: ["load-test/pipeline-0000.json", "load-test/pipeline-0001.json"],
};
const index = fixtureIndex(fixture);
const selected = selection(index, 0, 1);
let tests = 0;
function test(name, callback) { callback(); tests += 1; console.log(`${name}: passed`); }

test("default VU/duration and bounded validation mode", () => {
  assert.equal(configuration("smoke").durationSeconds, 60);
  assert.equal(configuration("smoke").vus, 7);
  assert.equal(configuration("baseline").durationSeconds, 300);
  assert.equal(configuration("baseline").vus, 5);
  assert.equal(configuration("baseline", "20").validationMode, true);
  for (const duration of [0, 1, -1, 61, 3.5, "abc", "Infinity"]) assert.throws(() => configuration("smoke", duration));
  assert.throws(() => configuration("target"));
});
test("rotation spans projects and cases with repeatable VU partition", () => {
  const samples = Array.from({ length: 4 }, (_, iteration) => selection(index, iteration, 1));
  assert.deepEqual(samples.map((item) => item.project), [fixture.projects[0], fixture.projects[1], fixture.projects[0], fixture.projects[1]]);
  assert.equal(new Set(samples.map((item) => item.item.reference)).size, 4);
  assert.deepEqual(selection(index, 2, 3, 5), selection(index, 2, 3, 5));
  const vus = Array.from({ length: 5 }, (_, vu) => selection(index, 0, vu + 1, 5).item.reference);
  assert.equal(new Set(vus).size, 4); // The tiny fixture wraps only after all four cases.
});
test("think time is seeded, repeatable and 1 to 3 seconds", () => {
  const first = Array.from({ length: 50 }, (_, iteration) => thinkSeconds(42, iteration, 1, 3));
  assert.deepEqual(first, Array.from({ length: 50 }, (_, iteration) => thinkSeconds(42, iteration, 1, 3)));
  assert.deepEqual([...new Set(first)].sort(), [1, 2, 3]);
  assert.notDeepEqual(first, Array.from({ length: 50 }, (_, iteration) => thinkSeconds(43, iteration, 1, 3)));
});
test("request metric names omit dynamic references and query", () => {
  for (let endpoint = 0; endpoint < 7; endpoint += 1) {
    const spec = requestSpec(endpoint, selected);
    assert.ok(!spec.name.includes("project-000") && !spec.name.includes("case-0") && !spec.name.includes("?"));
  }
  assert.ok(requestSpec(2, selected).path.includes("?project="));
});
test("health and exact list checks reject semantic errors", () => {
  assert.ok(validBody(0, { status: "ok", service: "example-api" }, selected, fixture));
  const malformedResponse = { status: 200, body: { status: "ok", service: "wrong" } };
  assert.equal(malformedResponse.status === 200, true);
  assert.equal(validBody(0, malformedResponse.body, selected, fixture), false);
  assert.ok(validBody(1, { items: fixture.projects }, selected, fixture));
  assert.equal(validBody(1, { items: [fixture.projects[0], fixture.projects[0]] }, selected, fixture), false);
  assert.ok(validBody(2, { items: selected.caseReferences }, selected, fixture));
  assert.equal(validBody(2, { items: [] }, selected, fixture), false);
  assert.ok(validBody(3, { items: selected.pipelineReferences }, selected, fixture));
  assert.equal(validBody(3, { items: [fixture.pipelines[1]] }, selected, fixture), false);
  for (let endpoint = 0; endpoint < 7; endpoint += 1) assert.equal(validBody(endpoint, null, selected, fixture), false);
});
test("project, body size, revision and request semantics are checked", () => {
  assert.ok(validBody(4, { name: "Load test project 000", _storage: { revision: 1 } }, selected, fixture));
  assert.equal(validBody(4, { name: "Load test project 001", _storage: { revision: 1 } }, selected, fixture), false);
  const body = { fixture: 42, padding: "" };
  body.padding = "x".repeat(1024 - JSON.stringify(body).length);
  const document = { project: selected.project, _storage: { revision: 3 }, loadTest: { bodyBytes: 1024 }, request: { method: "GET", url: "/example-api/health", body } };
  assert.ok(validBody(5, document, selected, fixture));
  assert.equal(validBody(5, { ...document, project: fixture.projects[1] }, selected, fixture), false);
  assert.equal(validBody(5, { ...document, request: { ...document.request, method: "PUT" } }, selected, fixture), false);
  assert.equal(validBody(5, { ...document, request: { ...document.request, body: { ...body, padding: body.padding.slice(1) } } }, selected, fixture), false);
  assert.ok(validBody(6, { items: [{ revision: 3 }, { revision: 2 }, { revision: 1 }] }, selected, fixture));
  assert.equal(validBody(6, { items: [{ revision: 3 }, { revision: 1 }] }, selected, fixture), false);
});
console.log(`read-model regressions: ${tests} passed`);
