// Small, side-effect-free presentation helpers shared across modules.

import { METRIC_LABELS } from "./state.js";

export function setMessage(element, message = "", state = "") {
  element.textContent = message;
  element.dataset.state = state;
}

export function formatMetric(metric) {
  return METRIC_LABELS[metric] || metric.replaceAll("_", " ");
}

export function formatStatus(status, labels) {
  return labels[status] || status.replaceAll("_", " ");
}

export function formatObject(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return "无法显示此操作的详细内容。";
  }
}

export function agentLabel(name) {
  return name;
}

export function formatAgentOption(agent) {
  return agent.name;
}
