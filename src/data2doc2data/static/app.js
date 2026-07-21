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
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "本地服务暂时无法完成此请求。");
  }
  return payload;
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

dataMode.addEventListener("change", syncSourceMode);
loadProfile();
