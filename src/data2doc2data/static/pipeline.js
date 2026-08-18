// Evidence pipeline panel: renders the five deterministic steps for the current turn.

import { VALIDATION_STATUS_LABELS, VERIFICATION_STATUS_LABELS, pipelineState } from "./state.js";
import { formatStatus } from "./ui.js";

const stepSource = document.querySelector('.pipeline-step[data-step="source"]');
const stepSignal = document.querySelector('.pipeline-step[data-step="signal"]');
const stepRetrieval = document.querySelector('.pipeline-step[data-step="retrieval"]');
const stepVerification = document.querySelector('.pipeline-step[data-step="verification"]');
const stepConclusion = document.querySelector('.pipeline-step[data-step="conclusion"]');

document.querySelectorAll(".pipeline-step").forEach((step) => {
  step.querySelector(".step-head").addEventListener("click", () => {
    const body = step.querySelector(".step-body");
    body.hidden = !body.hidden;
  });
});

function setStep(step, state, statusText, lines = []) {
  step.dataset.state = state;
  step.querySelector(".step-status").textContent = statusText;
  const body = step.querySelector(".step-body");
  body.replaceChildren();
  lines.filter(Boolean).forEach((line) => {
    const p = document.createElement("p");
    p.textContent = line;
    body.appendChild(p);
  });
  body.hidden = lines.length === 0;
}

function markActive() {
  [stepSignal, stepRetrieval, stepVerification, stepConclusion].forEach((step) => {
    if (step.dataset.state !== "done") step.dataset.state = "active";
  });
}

export function renderPipeline(source, analysis) {
  if (source) pipelineState.source = source;
  pipelineState.analysis = analysis ?? null;
  renderSource(pipelineState.source);
  renderAnalysis(pipelineState.analysis);
}

export function beginPipeline() {
  renderSource(pipelineState.source);
  markActive();
}

export function resetPipeline() {
  pipelineState.source = null;
  pipelineState.analysis = null;
  pipelineState.turns = {};
  [stepSource, stepSignal, stepRetrieval, stepVerification, stepConclusion].forEach((step) => {
    setStep(step, "", "—", []);
  });
}

function renderSource(source) {
  if (!source) return;
  const dates = Array.isArray(source.observation_dates) ? source.observation_dates : [];
  const range = dates.length > 0 ? `${dates[0]} → ${dates[dates.length - 1]}` : "—";
  const metrics = Array.isArray(source.metrics) ? source.metrics.length : 0;
  setStep(
    stepSource,
    "done",
    "完成",
    [
      `记录 ${source.record_count ?? "—"} · 指标 ${metrics} · 文档 ${source.document_count ?? "—"}`,
      `日期范围 ${range}`,
      source.label ? `来源 ${source.label}` : null,
    ],
  );
}

function renderAnalysis(analysis) {
  if (!analysis) {
    [stepSignal, stepRetrieval, stepVerification, stepConclusion].forEach((step) => {
      setStep(step, "", "—", []);
    });
    return;
  }
  if (analysis.signal) {
    setStep(stepSignal, "done", "完成", [analysis.signal.summary]);
  }
  if (analysis.context) {
    setStep(
      stepRetrieval,
      "done",
      "完成",
      [
        analysis.context.source ? `来源 ${analysis.context.source}` : null,
        analysis.context.excerpt ? `「${analysis.context.excerpt}」` : null,
      ],
    );
  }
  if (analysis.verification) {
    setStep(
      stepVerification,
      "done",
      formatStatus(analysis.verification.status, VERIFICATION_STATUS_LABELS),
      [
        analysis.verification.summary,
        analysis.verification.rule_name ? `规则：${analysis.verification.rule_name}` : null,
      ],
    );
  }
  if (analysis.validation) {
    const evidence = Array.isArray(analysis.evidence) ? analysis.evidence : [];
    const analysisId = analysis.provenance && analysis.provenance.analysis_id
      ? `分析 ID ${analysis.provenance.analysis_id}`
      : null;
    setStep(
      stepConclusion,
      "done",
      formatStatus(analysis.validation.status, VALIDATION_STATUS_LABELS),
      [
        analysis.validation.summary,
        ...evidence,
        analysis.limitation,
        analysisId,
      ],
    );
  }
}
