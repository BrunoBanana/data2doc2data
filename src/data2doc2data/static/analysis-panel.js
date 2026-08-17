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

export function invalidateAnalysisPresentation() {
  analysisState.result = null;
  analysisResult.hidden = true;
  analysisEmpty.hidden = false;
  analysisStatusTop.textContent = "等待分析";
}
