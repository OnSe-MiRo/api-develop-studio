export function campaignOptions(config) {
  if (config.phase === "baseline") return { executor: "constant-vus", vus: 5, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: "baselineRead" };
  if (config.phase === "run") return { executor: "per-vu-iterations", vus: config.vus, iterations: 1, maxDuration: "30s", gracefulStop: "10s", exec: "runOnce" };
  if (config.phase === "fault") return { executor: "constant-vus", vus: 1, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: "faultOnce" };
  if (config.mode === "soak") return { executor: "constant-vus", vus: config.vus, duration: `${config.durationSeconds}s`, gracefulStop: "10s", exec: "mixed" };
  return { executor: "ramping-vus", startVUs: config.startVus, stages: config.stages, gracefulStop: "10s", gracefulRampDown: "10s", exec: "mixed" };
}
