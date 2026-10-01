// Pure workload selection and response checks, shared by k6 and Node regressions.
export const endpoints = ["health", "projects", "cases", "pipelines", "project", "case", "revisions"];
export const names = ["/example-api/health", "/api/projects", "/api/cases", "/api/pipelines", "/api/projects/{id}", "/api/cases/{id}", "/api/cases/{id}/revisions"];

export function configuration(mode, seconds) {
  if (mode !== "smoke" && mode !== "baseline") throw new Error("read mode must be smoke or baseline");
  const maximum = mode === "smoke" ? 60 : 300;
  const duration = seconds === undefined ? maximum : Number(seconds);
  if (!Number.isInteger(duration) || duration < 2 || duration > maximum) throw new Error("read duration is outside its bounded range");
  return { mode, durationSeconds: duration, vus: mode === "smoke" ? 7 : 5, gracefulStopSeconds: 10, validationMode: duration !== maximum };
}

export function fixtureIndex(fixture) {
  const byProject = {};
  const pipelinesByProject = {};
  for (const project of fixture.projects) { byProject[project] = []; pipelinesByProject[project] = []; }
  for (const item of fixture.cases) byProject[item.project].push(item);
  // LT-1's generator assigns pipeline i to project i modulo the project count.
  fixture.pipelines.forEach((reference, index) => pipelinesByProject[fixture.projects[index % fixture.projects.length]].push(reference));
  return { fixture, byProject, pipelinesByProject };
}

export function selection(index, iteration, vu, concurrentVus = 1) {
  const offset = iteration * concurrentVus + vu - 1;
  const project = index.fixture.projects[offset % index.fixture.projects.length];
  const candidates = index.byProject[project];
  const item = candidates[Math.floor(offset / index.fixture.projects.length) % candidates.length];
  return { project, item, caseReferences: candidates.map((entry) => entry.reference), pipelineReferences: index.pipelinesByProject[project] };
}

export function thinkSeconds(seed, iteration, vu, endpoint) {
  let hash = 2166136261;
  for (const character of `${seed}:${iteration}:${vu}:${endpoint}`) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return 1 + ((hash >>> 0) % 3);
}

function sameReferences(actual, expected) {
  if (!Array.isArray(actual) || actual.length !== expected.length) return false;
  const values = new Set(actual);
  return values.size === expected.length && expected.every((value) => values.has(value));
}

export function requestSpec(endpoint, selected) {
  const project = selected.project;
  const reference = selected.item.reference;
  return { name: names[endpoint], path: ["/example-api/health", "/api/projects", `/api/cases?project=${encodeURIComponent(project)}`,
    `/api/pipelines?project=${encodeURIComponent(project)}`, `/api/projects/${project}`, `/api/cases/${reference}`, `/api/cases/${reference}/revisions`][endpoint] };
}

export function validBody(endpoint, body, selected, fixture) {
  if (!body || typeof body !== "object") return false;
  const { project, item, caseReferences, pipelineReferences } = selected;
  switch (endpoint) {
    case 0: return body.status === "ok" && body.service === "example-api";
    case 1: return sameReferences(body.items, fixture.projects);
    case 2: return sameReferences(body.items, caseReferences);
    case 3: return sameReferences(body.items, pipelineReferences);
    case 4: return !!body._storage && body._storage.revision === 1 && body.name === `Load test project ${project.match(/project-(\d+)\.json$/)[1]}`;
    case 5: return body.project === project && !!body._storage && body._storage.revision === item.revision
      && !!body.loadTest && body.loadTest.bodyBytes === item.bodyBytes && !!body.request && body.request.method === "GET"
      && body.request.url === "/example-api/health" && !!body.request.body && body.request.body.fixture === fixture.seed
      && typeof body.request.body.padding === "string" && /^x*$/.test(body.request.body.padding)
      && JSON.stringify(body.request.body).length === item.bodyBytes;
    case 6: return Array.isArray(body.items) && body.items.length === item.revision && body.items.every((revision, position) => revision.revision === item.revision - position);
    default: return false;
  }
}
