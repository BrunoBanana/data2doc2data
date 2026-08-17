// Shared, mutable application state and display constants.
// Modules import these objects by reference, so updates are visible everywhere.

export const agentState = {
  csrfToken: "",
  agents: [],
  session: null,
  eventSource: null,
  activeAssistant: null,
  turnActive: false,
  lastEventId: 0,
};

export const analysisState = { result: null };

export const demoState = {
  scenarios: [],
  defaultId: "",
};

export const METRIC_LABELS = {
  retention_rate: "留存率",
  activation_rate: "激活率",
};

export const VERIFICATION_STATUS_LABELS = {
  confirmed: "已验证",
  not_applicable: "不适用",
  unavailable: "数据缺失",
  not_confirmed: "未验证",
};

export const VALIDATION_STATUS_LABELS = {
  supported: "获得数据支持",
  contradicted: "与策略矛盾",
  mixed: "证据有限",
  insufficient: "证据不足",
};
