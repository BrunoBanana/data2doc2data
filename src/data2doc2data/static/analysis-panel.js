// Analysis canvas: the deterministic evidence question and result rendering.

import { request } from "./api.js";
import { analysisState, VALIDATION_STATUS_LABELS, VERIFICATION_STATUS_LABELS } from "./state.js";
import { formatMetric, formatStatus, setMessage } from "./ui.js";

const analysisForm = document.querySelector("#analysis-form");
const analysisMessage = document.querySelector("#analysis-message");
const analysisEmpty = document.querySelector("#analysis-empty");
const analysisResult = document.querySelector("#analysis-result");
const analysisQuestion = document.querySelector("#analysis-question");
const metricOverride = document.querySelector("#metric-override");
const analysisStatusTop = document.querySelector("#analysis-status-top");
const analysisHistory = document.querySelector("#analysis-history");
const historyList = document.querySelector("#history-list");
const historyCount = document.querySelector("#history-count");
const resultSignalTitle = document.querySelector("#result-signal-title");
const resultSignalCopy = document.querySelector("#result-signal-copy");
const resultContextCopy = document.querySelector("#result-context-copy");
const resultContextSource = document.querySelector("#result-context-source");
const resultVerificationTitle = document.querySelector("#result-verification-title");
const resultVerificationCopy = document.querySelector("#result-verification-copy");
const resultValidationStatus = document.querySelector("#result-validation-status");
const resultValidationCopy = document.querySelector("#result-validation-copy");
const resultLimitation = document.querySelector("#result-limitation");
const resultEvidence = document.querySelector("#result-evidence");

const MAX_HISTORY = 10;

export function setQuestion(value) {
  analysisQuestion.value = value;
}

analysisForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = analysisForm.querySelector("button");
  const question = analysisQuestion.value.trim();
  const override = metricOverride.value.trim();
  button.disabled = true;
  setMessage(analysisMessage, "正在读取本地证据");
  analysisStatusTop.textContent = "分析中";
  try {
    const result = await request("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ question, metric_override: override || null }),
    });
    renderResult(result);
    analysisState.result = result;
    recordHistory(question, result);
    setMessage(analysisMessage, "分析完成。", "success");
    analysisStatusTop.textContent = formatStatus(result.validation.status, VALIDATION_STATUS_LABELS);
  } catch (error) {
    setMessage(analysisMessage, error.message, "error");
    analysisStatusTop.textContent = "分析失败";
  } finally {
    button.disabled = false;
  }
});

function renderResult(result) {
  analysisEmpty.hidden = true;
  analysisResult.hidden = false;
  resultSignalTitle.textContent = formatMetric(result.signal.metric);
  resultSignalCopy.textContent = result.signal.summary;
  resultContextCopy.textContent = result.context.excerpt;
  resultContextSource.textContent = result.context.source;
  const verificationStatus = formatStatus(result.verification.status, VERIFICATION_STATUS_LABELS);
  resultVerificationTitle.textContent = result.verification.metric
    ? `${formatMetric(result.verification.metric)} · ${verificationStatus}`
    : verificationStatus;
  resultVerificationCopy.textContent = result.verification.summary;
  resultValidationStatus.textContent = formatStatus(result.validation.status, VALIDATION_STATUS_LABELS);
  resultValidationStatus.dataset.status = result.validation.status;
  resultValidationCopy.textContent = result.validation.summary;
  resultLimitation.textContent = result.limitation;

  resultEvidence.replaceChildren();
  result.evidence.forEach((item) => {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    resultEvidence.appendChild(listItem);
  });
}

export function invalidateAnalysisPresentation() {
  analysisState.result = null;
  // 数据源切换后旧结论不再适用，但保留在历史中以便追溯"为何失效"。
  analysisState.history.forEach((entry) => {
    entry.stale = true;
  });
  renderHistory();
  analysisResult.hidden = true;
  analysisEmpty.hidden = false;
  analysisStatusTop.textContent = "等待分析";
}

function recordHistory(question, result) {
  analysisState.history.push({
    question,
    result,
    at: new Date().toISOString(),
    stale: false,
  });
  if (analysisState.history.length > MAX_HISTORY) {
    analysisState.history.shift();
  }
  renderHistory();
}

function renderHistory() {
  historyList.replaceChildren();
  if (analysisState.history.length === 0) {
    analysisHistory.hidden = true;
    return;
  }
  analysisHistory.hidden = false;
  historyCount.textContent = String(analysisState.history.length);
  analysisState.history.forEach((entry) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    if (entry.stale) button.classList.add("is-stale");
    const status = entry.stale
      ? "已失效（数据源已切换）"
      : formatStatus(entry.result.validation.status, VALIDATION_STATUS_LABELS);
    button.textContent = `${entry.question} · ${status}`;
    button.title = entry.stale ? "该结论基于旧数据源，仅作追溯参考。" : "点击查看该次分析结果";
    button.addEventListener("click", () => {
      renderResult(entry.result);
      analysisState.result = entry.result;
    });
    item.appendChild(button);
    historyList.appendChild(item);
  });
}
