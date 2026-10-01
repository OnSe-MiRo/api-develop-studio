import { selection } from "./read-model.js";
export const categories = ["list", "single", "revision", "unique", "contention", "run"];
export const weights = { list: 35, single: 35, revision: 10, unique: 10, contention: 5, run: 5 };

export function targetConfiguration(seconds, validationVus) {
  const validation = seconds !== undefined;
  const duration = validation ? Number(seconds) : 1200;
  if (!Number.isInteger(duration) || duration < 2 || duration > 1200 || duration % 2 !== 0) throw new Error("target duration must be an even bounded number");
  if (validationVus !== undefined && (!validation || ![1, 2].includes(Number(validationVus)))) throw new Error("reduced VU needs target validation mode");
  return { durationSeconds: duration, stageSeconds: duration / 2, stageVus: validationVus === undefined ? [20, 50] : [1, Number(validationVus)], validationMode: validation };
}

export function targetOptions(config) {
  return { executor: "ramping-vus", startVUs: config.stageVus[0], stages: [
    { duration: `${config.stageSeconds}s`, target: config.stageVus[0] },
    { duration: "0s", target: config.stageVus[1] },
    { duration: `${config.stageSeconds}s`, target: config.stageVus[1] },
  ], gracefulStop: "10s", gracefulRampDown: "0s", exec: "mixed" };
}

export function operationBlock(seed, vu, cycle) {
  // 177 logical operations produce 200 workload HTTP requests per completed block.
  const counts = { list: 70, single: 70, revision: 20, unique: 5, contention: 2, run: 10 };
  const prefix = categories.slice();
  const rest = [];
  for (const category of categories) for (let count = 1; count < counts[category]; count += 1) rest.push(category);
  let value = (Number(seed) ^ (vu * 65537) ^ cycle) >>> 0;
  for (let position = rest.length - 1; position > 0; position -= 1) {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    const selected = value % (position + 1);
    [rest[position], rest[selected]] = [rest[selected], rest[position]];
  }
  return prefix.concat(rest);
}

export function operation(seed, vu, iteration) {
  const block = operationBlock(seed, vu, Math.floor(iteration / 177));
  return block[(iteration + (vu - 1) % 6) % block.length];
}

export function selected(index, iteration, vu, stride) { return selection(index, iteration, vu, stride); }
export function reference(kind, vu, iteration) { return `load-test/write/${kind}-vu-${vu}-iteration-${iteration}.json`; }
export function document(project, seed, kind, vu, iteration, step, winner = 0) {
  const body = { fixture: seed, padding: "" };
  body.padding = "x".repeat(1024 - JSON.stringify(body).length);
  return { project, request: { method: "GET", url: "/example-api/health", body },
    expected: { status: 200, body: { status: "ok", service: "example-api" }, strict: true },
    loadTest: { kind, vu, iteration, step, winner } };
}
export function validSave(response, body, path, revision) { return response.status === 200 && !!body && body.path === `case/${path}` && !!body._storage && body._storage.revision === revision; }
export function validConflict(response, body, revision) { return response.status === 409 && !!body && body.currentRevision === revision && typeof body.error === "string"; }
export function validRun(response, body, runCase) {
  return response.status === 200 && !!body && body.exitCode === 0 && typeof body.runId === "string" && !!body.result
    && body.result.status === "passed" && body.result.exitCode === 0 && Array.isArray(body.result.targets) && body.result.targets.length === 1
    && body.result.targets[0].caseReference === runCase && body.result.targets[0].status === "passed" && body.result.targets[0].httpStatus === 200;
}
