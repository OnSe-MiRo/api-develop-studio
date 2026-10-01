import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// Reproduce a summary context initialized after raw samples were collected.
const source = await readFile(new URL("./studio-summary.js", import.meta.url), "utf8");
const samplesStartedAt = new Date(Date.now() - 60_000).toISOString();
globalThis.__ENV = {
  STUDIO_STARTED_AT: samplesStartedAt,
  STUDIO_RUN_ID: "run_summary_start_regression",
  STUDIO_PROJECT: "load-test/project-000.json",
  STUDIO_SCENARIO: "harness-probe",
};
const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const summary = module.studioHandleSummary({ metrics: { checks: { thresholds: { "rate==1": { ok: true } } } } });
const manifest = JSON.parse(summary["studio-summary.json"]);
assert.equal(manifest.run.startedAt, samplesStartedAt);
assert.ok(Date.parse(manifest.run.endedAt) > Date.parse(manifest.run.startedAt));
assert.equal(manifest.thresholds[0].passed, true);
console.log("studio-summary start-time regression: passed");
