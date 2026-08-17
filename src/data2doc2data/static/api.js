// Local-only HTTP helpers. Every route stays on 127.0.0.1; no external origins.

import { agentState } from "./state.js";

export async function request(path, options = {}) {
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

export async function agentRequest(path, options = {}) {
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
