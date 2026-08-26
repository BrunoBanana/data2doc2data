// Entry point: starts the assistant and workspace data loads in parallel.

import { initializeWorkspace } from "./data-panel.js";
import { loadAgents } from "./assistant-panel.js";
import { initIngestPanel } from "./ingest-panel.js";

async function initializeApplication() {
  await Promise.all([loadAgents(), initializeWorkspace()]);
  initIngestPanel();
}

initializeApplication();
