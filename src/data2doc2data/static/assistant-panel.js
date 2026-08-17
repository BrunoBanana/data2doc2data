// Assistant rail: local agent detection, session, event stream, and approvals.

import { agentRequest, request } from "./api.js";
import { agentState } from "./state.js";
import { agentLabel, formatAgentOption, formatObject, setMessage } from "./ui.js";

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
const agentContextStatus = document.querySelector("#agent-context-status");
const contextSnapshotId = document.querySelector("#context-snapshot-id");
const contextContractVersion = document.querySelector("#context-contract-version");
const contextRecordCount = document.querySelector("#context-record-count");
const contextExcerptCount = document.querySelector("#context-excerpt-count");
const contextCompressionState = document.querySelector("#context-compression-state");

let announceTimer = null;

export async function loadAgents() {
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
    agentState.lastEventId = 0;
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
  const eventsRoute = `/api/agent-sessions/${sessionId}/events`;
  const eventSource = new EventSource(`${eventsRoute}?after=${agentState.lastEventId}`);
  agentState.eventSource = eventSource;
  let reconnectTimer = null;

  const clearReconnectTimer = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  eventSource.onopen = clearReconnectTimer;

  eventSource.onmessage = (event) => {
    try {
      const eventId = Number.parseInt(event.lastEventId, 10);
      if (Number.isFinite(eventId)) agentState.lastEventId = Math.max(agentState.lastEventId, eventId);
      handleAgentEvent(JSON.parse(event.data));
    } catch (_error) {
      finishTurn("助手返回了无法读取的事件。", "error");
    }
  };

  eventSource.onerror = () => {
    if (agentState.eventSource !== eventSource) return;
    // 让浏览器基于 Last-Event-ID 自动重连，服务端会从断点续传，因此不主动关闭。
    // 仅在活动 turn 期间持续断线时兜底提示，避免用户无限等待。
    if (agentState.turnActive && !reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (agentState.eventSource === eventSource && agentState.turnActive) {
          closeEventStream();
          finishTurn("助手连接持续中断，请重新发送。", "error");
        }
      }, 15000);
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
    case "context.attached":
      renderContextSummary(payload);
      break;
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

function renderContextSummary(payload) {
  contextRecordCount.textContent = String(payload.record_count ?? "—");
  contextExcerptCount.textContent = String(payload.excerpt_count ?? "—");
  contextCompressionState.textContent = payload.compressed ? "已压缩" : "完整证据包";
  const snapshotId = typeof payload.snapshot_id === "string" ? payload.snapshot_id : "";
  contextSnapshotId.textContent = snapshotId ? snapshotId.slice(0, 12) : "—";
  contextContractVersion.textContent = payload.contract_version != null ? `v${payload.contract_version}` : "—";
  agentContextStatus.textContent = "已附带";
}

export function resetContextSummary(status = "等待提问") {
  agentContextStatus.textContent = status;
  contextRecordCount.textContent = "—";
  contextExcerptCount.textContent = "—";
  contextCompressionState.textContent = "未建立";
  contextSnapshotId.textContent = "—";
  contextContractVersion.textContent = "—";
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
  // 流式增量期间抑制 aria-live 播报，避免屏幕阅读器被逐字打断。
  conversationLog.setAttribute("aria-busy", "true");
  agentState.activeAssistant.textContent += text;
  if (announceTimer) clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    announceTimer = null;
    conversationLog.setAttribute("aria-busy", "false");
  }, 400);
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
  if (announceTimer) {
    clearTimeout(announceTimer);
    announceTimer = null;
  }
  conversationLog.setAttribute("aria-busy", "false");
  setTurnControls(false);
  closeEventStream();
  setMessage(agentMessageStatus, message, state);
}
