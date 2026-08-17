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
  if (name === "workbuddy") return "腾讯 WorkBuddy";
  if (name === "codex") return "Codex";
  return name;
}

export function formatAgentOption(agent) {
  const name = agentLabel(agent.name);
  const version = agent.version ? ` · ${agent.version}` : "";
  if (!agent.available) return `${name} · 未安装`;
  if (!agent.authenticated) return `${name} · 未登录`;
  if (!agent.compatible) return `${name} · 版本不兼容`;
  return `${name}${version}`;
}
