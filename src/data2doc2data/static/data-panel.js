// Data source settings: demo scenarios, local paths, rules, and the source profile.

import { request } from "./api.js";
import { demoState } from "./state.js";
import { setMessage } from "./ui.js";
import { renderPipeline, resetPipeline } from "./pipeline.js";

const profileForm = document.querySelector("#profile-form");
const dataMode = document.querySelector("#data-mode");
const demoScenarioFields = document.querySelector("#demo-scenario-fields");
const demoScenario = document.querySelector("#demo-scenario");
const demoScenarioSummary = document.querySelector("#demo-scenario-summary");
const demoScenarioObjective = document.querySelector("#demo-scenario-objective");
const localFields = document.querySelector("#local-source-fields");
const dataPath = document.querySelector("#data-path");
const knowledgePath = document.querySelector("#knowledge-path");
const rulesPath = document.querySelector("#rules-path");
const profileMessage = document.querySelector("#profile-message");
const activeSourceStatus = document.querySelector("#active-source-status");
const sourceRecordCount = document.querySelector("#source-record-count");
const sourceMetricCount = document.querySelector("#source-metric-count");
const sourceDocumentCount = document.querySelector("#source-document-count");
const sourceProfileLabel = document.querySelector("#source-profile-label");

function syncSourceMode() {
  const isLocal = dataMode.value === "local";
  demoScenarioFields.hidden = isLocal;
  localFields.hidden = !isLocal;
  demoScenario.required = !isLocal;
  dataPath.required = isLocal;
  knowledgePath.required = isLocal;
}

function selectedScenario() {
  return demoState.scenarios.find((scenario) => scenario.id === demoScenario.value) || null;
}

function renderScenarioDetails(updateQuestion = false) {
  const scenario = selectedScenario();
  if (!scenario) {
    demoScenarioSummary.textContent = "演示场景暂不可用。";
    demoScenarioObjective.textContent = "";
    return;
  }
  demoScenarioSummary.textContent = scenario.summary;
  demoScenarioObjective.textContent = `学习目标：${scenario.learning_objective}`;
}

export async function loadProfile() {
  try {
    const payload = await request("/api/profile");
    const profile = payload.profile;
    if (profile) {
      dataMode.value = profile.mode;
      dataPath.value = profile.data_path;
      knowledgePath.value = profile.knowledge_path;
      rulesPath.value = profile.rules_path || "";
      if (demoState.scenarios.some((scenario) => scenario.id === profile.demo_scenario)) {
        demoScenario.value = profile.demo_scenario;
      }
    }
    renderScenarioDetails();
    syncSourceMode();
  } catch (error) {
    setMessage(profileMessage, error.message, "error");
  }
}

export async function loadSourceProfile() {
  try {
    const profile = await request("/api/source-profile");
    renderSourceProfile(profile);
  } catch (error) {
    activeSourceStatus.textContent = "数据源不可用";
    sourceProfileLabel.textContent = error.message;
    sourceRecordCount.textContent = "—";
    sourceMetricCount.textContent = "—";
    sourceDocumentCount.textContent = "—";
  }
}

function renderSourceProfile(profile) {
  const metrics = Array.isArray(profile.metrics) ? profile.metrics : [];
  sourceRecordCount.textContent = String(profile.record_count ?? "—");
  sourceMetricCount.textContent = String(metrics.length);
  sourceDocumentCount.textContent = String(profile.document_count ?? "—");
  sourceProfileLabel.textContent = profile.label || "当前数据集";
  activeSourceStatus.textContent = `${profile.label || "当前数据"} · ${profile.record_count || 0} 条`;
  renderPipeline(profile, null);
}

export async function loadDemoScenarios() {
  try {
    const payload = await request("/api/demo-scenarios");
    demoState.scenarios = Array.isArray(payload.scenarios) ? payload.scenarios : [];
    demoState.defaultId = payload.default || "";
    demoScenario.replaceChildren();
    demoState.scenarios.forEach((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = scenario.label;
      demoScenario.appendChild(option);
    });
    if (demoState.scenarios.some((scenario) => scenario.id === demoState.defaultId)) {
      demoScenario.value = demoState.defaultId;
    }
    demoScenario.disabled = demoState.scenarios.length === 0;
    renderScenarioDetails();
  } catch (error) {
    demoScenario.disabled = true;
    demoScenario.replaceChildren();
    setMessage(profileMessage, error.message, "error");
  }
}

export async function initializeWorkspace() {
  await loadDemoScenarios();
  await Promise.all([loadProfile(), loadSourceProfile()]);
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = profileForm.querySelector("button");
  button.disabled = true;
  setMessage(profileMessage, "正在保存数据源");
  try {
    await request("/api/profile", {
      method: "PUT",
      body: JSON.stringify({
        mode: dataMode.value,
        data_path: dataPath.value.trim(),
        knowledge_path: knowledgePath.value.trim(),
        rules_path: dataMode.value === "local" ? rulesPath.value.trim() : "",
        demo_scenario: demoScenario.value,
      }),
    });
    setMessage(profileMessage, "数据源已保存至本机。", "success");
    resetPipeline();
    await loadSourceProfile();
  } catch (error) {
    setMessage(profileMessage, error.message, "error");
  } finally {
    button.disabled = false;
  }
});

function markSourceDirty() {
  activeSourceStatus.textContent = "保存后更新数据";
}

dataMode.addEventListener("change", () => {
  syncSourceMode();
  markSourceDirty();
});
demoScenario.addEventListener("change", () => {
  renderScenarioDetails(true);
  markSourceDirty();
});
dataPath.addEventListener("input", markSourceDirty);
knowledgePath.addEventListener("input", markSourceDirty);
