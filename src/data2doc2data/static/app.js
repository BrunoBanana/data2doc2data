const profileForm = document.querySelector("#profile-form");
const analysisForm = document.querySelector("#analysis-form");
const dataMode = document.querySelector("#data-mode");
const localFields = document.querySelector("#local-source-fields");
const dataPath = document.querySelector("#data-path");
const knowledgePath = document.querySelector("#knowledge-path");
const profileState = document.querySelector("#profile-state");
const profileMessage = document.querySelector("#profile-message");
const analysisMessage = document.querySelector("#analysis-message");
const analysisEmpty = document.querySelector("#analysis-empty");
const analysisResult = document.querySelector("#analysis-result");
const metricOverride = document.querySelector("#metric-override");
const agentConnectForm = document.querySelector("#agent-connect-form");
const agentProvider = document.querySelector("#agent-provider");
const permissionMode = document.querySelector("#permission-mode");
const agentConnect = document.querySelector("#agent-connect");
const agentStatus = document.querySelector("#agent-status");
const agentMessageForm = document.querySelector("#agent-message-form");
const agentMessage = document.querySelector("#agent-message");
const agentSend = document.querySelector("#agent-send");
const agentInterrupt = document.querySelector("#agent-interrupt");
const agentMessageStatus = document.querySelector("#agent-message-status");
const conversationLog = document.querySelector("#conversation-log");
const conversationEmpty = document.querySelector("#conversation-empty");
const operationQueue = document.querySelector("#operation-queue");
const agentState = {
  csrfToken: "",
  agents: [],
  session: null,
  eventSource: null,
  activeAssistant: null,
  turnActive: false,
};
const METRIC_LABELS = {
  retention_rate: "留存率",
  activation_rate: "激活率",
};
const VERIFICATION_STATUS_LABELS = {
  confirmed: "已验证",
  not_applicable: "不适用",
  unavailable: "数据缺失",
  not_confirmed: "未验证",
};
const VALIDATION_STATUS_LABELS = {
  supported: "获得数据支持",
  mixed: "证据有限",
  insufficient: "证据不足",
};

function setMessage(element, message = "", state = "") {
  element.textContent = message;
  element.dataset.state = state;
}

function syncSourceMode() {
  const isLocal = dataMode.value === "local";
  localFields.hidden = !isLocal;
  dataPath.required = isLocal;
  knowledgePath.required = isLocal;
}

async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const response = await fetch(path, {
    ...options,
    headers,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "本地服务暂时无法完成此请求。");
  }
  return payload;
}

async function agentRequest(path, options = {}) {
  if (!agentState.csrfToken) {
    throw new Error("本地助手授权已失效，请刷新页面后重试。");
  }
  return request(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      "X-CSRF-Token": agentState.csrfToken,
    },
  });
}

async function loadProfile() {
  try {
    const payload = await request("/api/profile");
    const profile = payload.profile;
    profileState.textContent = payload.configured ? "工作区已配置" : "正在使用内置演示";
    if (profile) {
      dataMode.value = profile.mode;
      dataPath.value = profile.data_path;
      knowledgePath.value = profile.knowledge_path;
    }
    syncSourceMode();
  } catch (error) {
    profileState.textContent = "工作区暂不可用";
    setMessage(profileMessage, error.message, "error");
  }
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = profileForm.querySelector("button");
  button.disabled = true;
  setMessage(profileMessage, "正在保存本地工作区");
  try {
    const profile = await request("/api/profile", {
      method: "PUT",
      body: JSON.stringify({
        mode: dataMode.value,
        data_path: dataPath.value.trim(),
        knowledge_path: knowledgePath.value.trim(),
      }),
    });
    profileState.textContent = profile.profile.mode === "demo" ? "已保存内置演示" : "工作区已配置";
    setMessage(profileMessage, "工作区已保存至本机。", "success");
  } catch (error) {
    setMessage(profileMessage, error.message, "error");
  } finally {
    button.disabled = false;
  }
});

analysisForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = analysisForm.querySelector("button");
  const question = document.querySelector("#analysis-question").value.trim();
  const override = metricOverride.value.trim();
  button.disabled = true;
  setMessage(analysisMessage, "正在读取本地证据");
  try {
    const result = await request("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ question, metric_override: override || null }),
    });
    renderResult(result);
    setMessage(analysisMessage, "分析完成。", "success");
  } catch (error) {
    setMessage(analysisMessage, error.message, "error");
  } finally {
    button.disabled = false;
  }
});

function renderResult(result) {
  analysisEmpty.hidden = true;
  analysisResult.hidden = false;
  document.querySelector("#result-signal-title").textContent = formatMetric(result.signal.metric);
  document.querySelector("#result-signal-copy").textContent = result.signal.summary;
  document.querySelector("#result-context-copy").textContent = result.context.excerpt;
  document.querySelector("#result-context-source").textContent = result.context.source;
  const verificationStatus = formatStatus(result.verification.status, VERIFICATION_STATUS_LABELS);
  document.querySelector("#result-verification-title").textContent = result.verification.metric
    ? `${formatMetric(result.verification.metric)} · ${verificationStatus}`
    : verificationStatus;
  document.querySelector("#result-verification-copy").textContent = result.verification.summary;
  const validationStatus = document.querySelector("#result-validation-status");
  validationStatus.textContent = formatStatus(result.validation.status, VALIDATION_STATUS_LABELS);
  validationStatus.dataset.status = result.validation.status;
  document.querySelector("#result-validation-copy").textContent = result.validation.summary;
  document.querySelector("#result-limitation").textContent = result.limitation;

  const evidence = document.querySelector("#result-evidence");
  evidence.replaceChildren();
  result.evidence.forEach((item) => {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    evidence.appendChild(listItem);
  });
}

function formatMetric(metric) {
  return METRIC_LABELS[metric] || metric.replaceAll("_", " ");
}

function formatStatus(status, labels) {
  return labels[status] || status.replaceAll("_", " ");
}

async function loadAgents() {
  try {
    const payload = await request("/api/agents");
    agentState.csrfToken = payload.csrf_token;
    agentState.agents = Array.isArray(payload.agents) ? payload.agents : [];
    renderAgentOptions();
  } catch (error) {
    agentStatus.textContent = "助手检测失败";
    setMessage(agentMessageStatus, error.message, "error");
  }
}

function renderAgentOptions() {
  agentProvider.replaceChildren();
  const selectable = agentState.agents.filter(
    (agent) => agent.available && agent.authenticated && agent.compatible,
  );
  agentState.agents.forEach((agent) => {
    const option = document.createElement("option");
    option.value = agent.name;
    option.disabled = !selectable.includes(agent);
    option.textContent = formatAgentOption(agent);
    agentProvider.appendChild(option);
  });
  if (agentState.agents.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "未配置本地助手";
    agentProvider.appendChild(option);
  }
  if (selectable.length > 0) {
    agentProvider.value = selectable[0].name;
    agentProvider.disabled = false;
    agentConnect.disabled = false;
    agentStatus.textContent = `已发现 ${selectable.length} 个可用助手`;
    return;
  }
  agentProvider.disabled = true;
  agentConnect.disabled = true;
  agentStatus.textContent = "未发现可用助手";
  setMessage(agentMessageStatus, "确定性证据分析仍可正常使用。", "");
}

function formatAgentOption(agent) {
  const name = agentLabel(agent.name);
  const version = agent.version ? ` · ${agent.version}` : "";
  if (!agent.available) return `${name} · 未安装`;
  if (!agent.authenticated) return `${name} · 未登录`;
  if (!agent.compatible) return `${name} · 版本不兼容`;
  return `${name}${version}`;
}

function agentLabel(name) {
  if (name === "workbuddy") return "腾讯 WorkBuddy";
  if (name === "codex") return "Codex";
  return name;
}

agentConnectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  agentConnect.disabled = true;
  setMessage(agentMessageStatus, "正在连接本地助手");
  closeEventStream();
  try {
    const payload = await agentRequest("/api/agent-sessions", {
      method: "POST",
      body: JSON.stringify({
        provider: agentProvider.value,
        permission_mode: permissionMode.value,
      }),
    });
    agentState.session = payload.session;
    conversationLog.replaceChildren();
    operationQueue.replaceChildren();
    agentMessage.disabled = false;
    agentSend.disabled = false;
    permissionMode.disabled = true;
    agentProvider.disabled = true;
    agentStatus.textContent = `${agentLabel(payload.session.provider)} 已连接`;
    setMessage(agentMessageStatus, `工作目录：${payload.session.workspace}`, "success");
    startEventStream();
    agentMessage.focus();
  } catch (error) {
    agentConnect.disabled = false;
    setMessage(agentMessageStatus, error.message, "error");
  }
});

agentMessageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!agentState.session || agentState.turnActive) return;
  const message = agentMessage.value.trim();
  if (!message) return;
  agentState.turnActive = true;
  agentState.activeAssistant = null;
  setTurnControls(true);
  appendMessage("你", message, "user");
  agentMessage.value = "";
  startEventStream();
  try {
    const sessionId = encodeURIComponent(agentState.session.id);
    await agentRequest(`/api/agent-sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    setMessage(agentMessageStatus, "助手正在处理");
  } catch (error) {
    finishTurn(error.message, "error");
  }
});

agentInterrupt.addEventListener("click", async () => {
  if (!agentState.session || !agentState.turnActive) return;
  agentInterrupt.disabled = true;
  try {
    const sessionId = encodeURIComponent(agentState.session.id);
    await agentRequest(`/api/agent-sessions/${sessionId}/interrupt`, {
      method: "POST",
      body: "{}",
    });
    setMessage(agentMessageStatus, "正在停止当前任务");
  } catch (error) {
    agentInterrupt.disabled = false;
    setMessage(agentMessageStatus, error.message, "error");
  }
});

function startEventStream() {
  if (!agentState.session || agentState.eventSource) return;
  const sessionId = encodeURIComponent(agentState.session.id);
  const eventSource = new EventSource(`/api/agent-sessions/${sessionId}/events`);
  agentState.eventSource = eventSource;
  eventSource.onmessage = (event) => {
    try {
      handleAgentEvent(JSON.parse(event.data));
    } catch (_error) {
      finishTurn("助手返回了无法读取的事件。", "error");
    }
  };
  eventSource.onerror = () => {
    if (agentState.eventSource !== eventSource) return;
    closeEventStream();
    if (agentState.turnActive) {
      finishTurn("助手事件连接已断开，可以重新发送。", "error");
    }
  };
}

function closeEventStream() {
  if (!agentState.eventSource) return;
  const eventSource = agentState.eventSource;
  agentState.eventSource = null;
  eventSource.close();
}

function handleAgentEvent(event) {
  const payload = event && typeof event.payload === "object" ? event.payload : {};
  switch (event.kind) {
    case "message.delta":
      appendAssistantDelta(payload.text || "");
      break;
    case "plan.delta":
      appendOperation("计划", payload.text || "", "plan-card");
      break;
    case "command.output":
      appendOperation("命令输出", payload.text || "", "output-card");
      break;
    case "file.diff":
      appendOperation(`文件差异 · ${payload.path || "未知文件"}`, payload.diff || "", "diff-card");
      break;
    case "tool.call":
      appendOperation(`工具调用 · ${payload.name || "工具"}`, formatObject(payload.arguments), "tool-card");
      break;
    case "tool.result":
      appendOperation(payload.error ? "操作失败" : "操作完成", formatObject(payload.result), "tool-card");
      break;
    case "approval.request":
      renderApproval(payload);
      break;
    case "turn.completed":
      finishTurn("助手任务已完成。", "success");
      break;
    case "turn.cancelled":
      finishTurn("助手任务已停止。", "");
      break;
    case "turn.error":
    case "provider.error":
      finishTurn(payload.message || "助手暂时不可用。", "error");
      break;
    default:
      break;
  }
}

function appendMessage(author, text, kind) {
  if (conversationEmpty && conversationEmpty.isConnected) conversationEmpty.remove();
  const article = document.createElement("article");
  article.className = `message-card message-${kind}`;
  const label = document.createElement("p");
  label.className = "message-author";
  label.textContent = author;
  const copy = document.createElement("p");
  copy.className = "message-copy";
  copy.textContent = text;
  article.append(label, copy);
  conversationLog.appendChild(article);
  article.scrollIntoView({ block: "nearest" });
  return copy;
}

function appendAssistantDelta(text) {
  if (!agentState.activeAssistant) {
    agentState.activeAssistant = appendMessage("助手", "", "assistant");
  }
  agentState.activeAssistant.textContent += text;
}

function appendOperation(title, content, className) {
  const card = document.createElement("article");
  card.className = `operation-card ${className}`;
  const heading = document.createElement("h4");
  heading.textContent = title;
  const copy = document.createElement("pre");
  copy.textContent = content;
  card.append(heading, copy);
  operationQueue.appendChild(card);
  return card;
}

function renderApproval(payload) {
  const card = appendOperation("等待批准", "", "approval-card");
  const details = document.createElement("dl");
  appendApprovalDetail(details, "操作", payload.operation || "未知操作");
  appendApprovalDetail(details, "命令", payload.command || "未提供");
  appendApprovalDetail(details, "工作目录", payload.working_directory || agentState.session.workspace);
  const paths = Array.isArray(payload.target_paths) ? payload.target_paths.join("\n") : "";
  appendApprovalDetail(details, "目标路径", paths || "未提供");
  if (payload.diff) appendApprovalDetail(details, "文件差异", payload.diff);

  const actions = document.createElement("div");
  actions.className = "approval-actions";
  const approveButton = document.createElement("button");
  approveButton.type = "button";
  approveButton.textContent = "批准";
  const rejectButton = document.createElement("button");
  rejectButton.type = "button";
  rejectButton.className = "button-danger";
  rejectButton.textContent = "拒绝";
  approveButton.addEventListener("click", () => decideApproval(payload.request_id, true, card, actions));
  rejectButton.addEventListener("click", () => decideApproval(payload.request_id, false, card, actions));
  actions.append(approveButton, rejectButton);
  card.replaceChildren(card.firstChild, details, actions);
}

function appendApprovalDetail(list, label, value) {
  const group = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  group.append(term, detail);
  list.appendChild(group);
}

async function decideApproval(approvalId, approved, card, actions) {
  Array.from(actions.querySelectorAll("button")).forEach((button) => {
    button.disabled = true;
  });
  try {
    const sessionId = encodeURIComponent(agentState.session.id);
    await agentRequest(
      `/api/agent-sessions/${sessionId}/approvals/${encodeURIComponent(approvalId)}`,
      { method: "POST", body: JSON.stringify({ approved }) },
    );
    card.dataset.decision = approved ? "approved" : "rejected";
    const result = document.createElement("p");
    result.className = "approval-result";
    result.textContent = approved ? "已批准" : "已拒绝";
    actions.replaceChildren(result);
  } catch (error) {
    const result = document.createElement("p");
    result.className = "approval-result error-copy";
    result.textContent = error.message;
    actions.replaceChildren(result);
  }
}

function setTurnControls(active) {
  agentSend.disabled = active;
  agentMessage.disabled = active;
  agentInterrupt.disabled = !active;
}

function finishTurn(message, state) {
  agentState.turnActive = false;
  agentState.activeAssistant = null;
  setTurnControls(false);
  closeEventStream();
  setMessage(agentMessageStatus, message, state);
}

function formatObject(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return "无法显示此操作的详细内容。";
  }
}

dataMode.addEventListener("change", syncSourceMode);
loadProfile();
loadAgents();
