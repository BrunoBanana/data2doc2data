// Local-only HTTP helpers. Every route stays on 127.0.0.1; no external origins.

import { agentState } from "./state.js";

let authorizationRefresh = null;

class ApiRequestError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const response = await fetch(path, {
    ...options,
    headers,
  });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (_error) {
    payload = {};
  }
  if (!response.ok) {
    throw new ApiRequestError(payload.error || "本地服务暂时无法完成此请求。", response.status);
  }
  return payload;
}

export async function agentRequest(path, options = {}) {
  if (!agentState.csrfToken) {
    await refreshAgentAuthorization();
  }
  const attemptedToken = agentState.csrfToken;
  try {
    return await requestWithAgentToken(path, options, attemptedToken);
  } catch (error) {
    if (!(error instanceof ApiRequestError) || error.status !== 403) throw error;
    if (agentState.csrfToken === attemptedToken) await refreshAgentAuthorization();
    return requestWithAgentToken(path, options, agentState.csrfToken);
  }
}

function requestWithAgentToken(path, options, token) {
  return request(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      "X-CSRF-Token": token,
    },
  });
}

async function refreshAgentAuthorization() {
  if (!authorizationRefresh) {
    authorizationRefresh = request("/api/agents")
      .then((payload) => {
        if (typeof payload.csrf_token !== "string" || !payload.csrf_token) {
          throw new Error("本地助手授权刷新失败，请刷新页面后重试。");
        }
        agentState.csrfToken = payload.csrf_token;
      })
      .finally(() => {
        authorizationRefresh = null;
      });
  }
  return authorizationRefresh;
}
