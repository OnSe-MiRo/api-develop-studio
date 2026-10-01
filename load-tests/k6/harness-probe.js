// LT-1 wiring check only; full Smoke/Baseline load models belong to LT-2.
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import { studioHandleSummary } from "./studio-summary.js";

const fixtures = new SharedArray("fixture", () => [JSON.parse(open(__ENV.STUDIO_FIXTURE_PATH))]);
const fixture = fixtures[0];
const baseUrl = __ENV.STUDIO_BASE_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl || "")) {
  throw new Error("harness-probe requires the isolated loopback target");
}
export const options = {
  scenarios: { probe: { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "30s" } },
  thresholds: { checks: ["rate==1"], http_req_failed: ["rate==0"], http_reqs: ["count>=7"] },
  systemTags: ["method", "status", "name", "scenario", "expected_response"],
};

function get(path, name, validate) {
  const response = http.get(baseUrl + path, { tags: { name }, timeout: "5s", redirects: 0 });
  let body;
  try { body = response.json(); } catch (_) { body = null; }
  check(response, {
    [`${name}: status`]: (value) => value.status === 200,
    [`${name}: body`]: () => body !== null && validate(body),
  });
}

export default function () {
  // Allow k6 to emit its periodic VU gauge for this deliberately short run.
  sleep(1.1);
  const project = fixture.projects[0];
  const selected = fixture.cases.filter((item) => item.project === project);
  const item = selected[0]; // The seeded manifest fixes the sampling order.
  get("/example-api/health", "/example-api/health", (body) => body.status === "ok" && body.service === "example-api");
  get("/api/projects", "/api/projects", (body) => Array.isArray(body.items) && body.items.length === fixture.counts.projects && body.items.includes(project));
  get(`/api/cases?project=${encodeURIComponent(project)}`, "/api/cases", (body) => Array.isArray(body.items) && body.items.length === selected.length && body.items.includes(item.reference));
  get(`/api/pipelines?project=${encodeURIComponent(project)}`, "/api/pipelines", (body) => Array.isArray(body.items));
  get(`/api/projects/${project}`, "/api/projects/{id}", (body) => body._storage && body._storage.revision === 1 && typeof body.name === "string" && body.name.startsWith("Load test project "));
  get(`/api/cases/${item.reference}`, "/api/cases/{id}", (body) => body.project === project && body._storage && body._storage.revision === item.revision && body.loadTest && body.loadTest.bodyBytes === item.bodyBytes && body.request && body.request.url === "/example-api/health");
  get(`/api/cases/${item.reference}/revisions`, "/api/cases/{id}/revisions", (body) => Array.isArray(body.items) && body.items.length === item.revision && body.items[0].revision === item.revision);
}

export { studioHandleSummary as handleSummary };
