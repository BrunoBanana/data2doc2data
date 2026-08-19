// Side data ingestion: probe local files / API snapshots and map them to metric rows.

import { request } from "./api.js";
import { setMessage } from "./ui.js";
import { loadProfile, loadSourceProfile } from "./data-panel.js";

let currentPath = "";
let currentMode = "local";
let currentPreview = null;

const tabs = Array.from(document.querySelectorAll(".ingest-tab"));
const panels = Array.from(document.querySelectorAll("[data-ingest-panel]"));
const fileInput = document.querySelector("#ingest-file");
const localMessage = document.querySelector("#ingest-local-message");
const apiUrl = document.querySelector("#ingest-api-url");
const apiHeaders = document.querySelector("#ingest-api-headers");
const apiFetchButton = document.querySelector("#ingest-api-fetch");
const apiMessage = document.querySelector("#ingest-api-message");
const previewBox = document.querySelector("#ingest-preview");
const planForm = document.querySelector("#ingest-plan-form");
const dateField = document.querySelector("#ingest-date-field");
const metricField = document.querySelector("#ingest-metric-field");
const valueField = document.querySelector("#ingest-value-field");
const recordsPath = document.querySelector("#ingest-records-path");
const sheetField = document.querySelector("#ingest-sheet");
const dateFormat = document.querySelector("#ingest-date-format");
const planMessage = document.querySelector("#ingest-plan-message");
const knowledgePath = document.querySelector("#ingest-knowledge-path");
const proposeRow = document.querySelector("#ingest-propose-row");
const proposeButton = document.querySelector("#ingest-propose");
const resultBox = document.querySelector("#ingest-result");
const useAgent = document.querySelector("#ingest-use-agent");
const localPathInput = document.querySelector("#ingest-local-path");
const localPathUseButton = document.querySelector("#ingest-local-path-use");
const localPathMessage = document.querySelector("#ingest-local-path-message");

function setIngestTab(tab) {
  currentMode = tab;
  tabs.forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.ingestTab === tab));
  });
  panels.forEach((panel) => {
    panel.hidden = panel.dataset.ingestPanel !== tab;
  });
}

function hidePreviewAndPlan() {
  previewBox.hidden = true;
  previewBox.replaceChildren();
  proposeRow.hidden = true;
  planForm.hidden = true;
  resultBox.hidden = true;
  resultBox.replaceChildren();
}

function populateSelect(select, values, selected) {
  select.replaceChildren();
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value || "（无）";
    select.appendChild(option);
  });
  if (selected && values.includes(selected)) {
    select.value = selected;
  }
}

function renderPreview(payload, agentPlan = null) {
  currentPreview = payload.preview;
  const preview = payload.preview;
  const suggestion = agentPlan || payload.agent_plan || payload.suggestion;
  const usedAgent = Boolean(agentPlan || payload.agent_plan);

  previewBox.replaceChildren();
  const heading = document.createElement("p");
  heading.className = "ingest-preview-title";
  heading.textContent = `已识别：${preview.format.toUpperCase()} · ${preview.row_count ?? "?"} 行`;
  previewBox.appendChild(heading);

  const fieldsLine = document.createElement("p");
  fieldsLine.className = "quiet-copy";
  fieldsLine.textContent = `字段：${preview.fields.join("、")}`;
  previewBox.appendChild(fieldsLine);

  if (preview.sheets && preview.sheets.length) {
    const sheetLine = document.createElement("p");
    sheetLine.className = "quiet-copy";
    sheetLine.textContent = `工作表：${preview.sheets.join("、")}`;
    previewBox.appendChild(sheetLine);
  }

  if (preview.sample_rows && preview.sample_rows.length) {
    const sample = document.createElement("dl");
    sample.className = "context-metadata";
    const row = preview.sample_rows[0];
    Object.entries(row).forEach(([key, value]) => {
      const term = document.createElement("dt");
      term.textContent = key;
      const detail = document.createElement("dd");
      detail.textContent = String(value);
      sample.append(term, detail);
    });
    previewBox.appendChild(sample);
  }

  previewBox.hidden = false;

  populateSelect(dateField, preview.fields, suggestion ? suggestion.date_field : "");
  populateSelect(metricField, preview.fields, suggestion ? suggestion.metric_field : "");
  populateSelect(valueField, preview.fields, suggestion ? suggestion.value_field : "");
  populateSelect(sheetField, ["", ...preview.sheets], suggestion ? suggestion.sheet : "");
  recordsPath.value = (suggestion && suggestion.records_path) || "";
  dateFormat.value = (suggestion && suggestion.date_format) || "";

  const settingsKnowledge = document.querySelector("#knowledge-path");
  knowledgePath.value = settingsKnowledge ? settingsKnowledge.value.trim() : "";

  proposeRow.hidden = false;
  if (usedAgent) {
    setMessage(planMessage, "助手已根据数据结构给出映射建议，可调整后应用。", "");
  } else if (suggestion) {
    setMessage(planMessage, "已根据字段名给出建议，可调整后应用，或让助手重新推断。", "");
  } else {
    setMessage(planMessage, "未能自动推断映射，请手动选择字段，或让助手尝试推断。", "warn");
  }
  planForm.hidden = false;
}

async function handlePropose() {
  if (!currentPath || !currentPreview) {
    setMessage(planMessage, "请先上传文件或拉取 API 快照。", "error");
    return;
  }
  setMessage(planMessage, "正在请助手理解数据结构并推断映射");
  try {
    const res = await request("/api/ingest/propose", {
      method: "POST",
      body: JSON.stringify({ path: currentPath }),
    });
    const plan = res.agent_plan;
    const fields = currentPreview.fields || [];
    if (plan && fields.includes(plan.date_field) && fields.includes(plan.metric_field) && fields.includes(plan.value_field)) {
      populateSelect(dateField, fields, plan.date_field);
      populateSelect(metricField, fields, plan.metric_field);
      populateSelect(valueField, fields, plan.value_field);
      populateSelect(sheetField, ["", ...(currentPreview.sheets || [])], plan.sheet);
      recordsPath.value = plan.records_path || "";
      dateFormat.value = plan.date_format || "";
      setMessage(planMessage, "助手已根据数据结构给出映射建议，确认后应用。", "");
    } else {
      setMessage(planMessage, (res.reason || "助手暂不可用，已保留内置建议。"), "warn");
    }
  } catch (error) {
    setMessage(planMessage, error.message, "error");
  }
}

async function uploadAndPreview(base64Content, filename, useAgentFlag = false) {
  setMessage(localMessage, "正在上传并解析文件");
  try {
    const upload = await request("/api/ingest/upload", {
      method: "POST",
      body: JSON.stringify({ filename, content: base64Content }),
    });
    currentPath = upload.path;
    const preview = await request("/api/ingest/preview", {
      method: "POST",
      body: JSON.stringify({ path: currentPath, use_agent: useAgentFlag }),
    });
    hidePreviewAndPlan();
    renderPreview(preview, useAgentFlag ? preview.agent_plan : null);
    setMessage(localMessage, "文件已解析，请确认字段映射。");
  } catch (error) {
    setMessage(localMessage, error.message, "error");
  }
}

function handleFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = String(reader.result);
    const comma = dataUrl.indexOf(",");
    const base64Content = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    uploadAndPreview(base64Content, file.name, useAgent.checked);
  };
  reader.onerror = () => setMessage(localMessage, "文件读取失败，请重试。", "error");
  reader.readAsDataURL(file);
}

async function handleLocalPathUse() {
  const raw = localPathInput.value.trim();
  if (!raw) {
    setMessage(localPathMessage, "请填写本机文件绝对路径。", "error");
    return;
  }
  setMessage(localPathMessage, "正在解析本机文件");
  try {
    const preview = await request("/api/ingest/preview", {
      method: "POST",
      body: JSON.stringify({ path: raw, validate_local: true, use_agent: useAgent.checked }),
    });
    currentPath = raw;
    currentMode = "local";
    hidePreviewAndPlan();
    renderPreview(preview, useAgent.checked ? preview.agent_plan : null);
    setMessage(localPathMessage, "文件已解析，请确认字段映射。");
  } catch (error) {
    setMessage(localPathMessage, error.message, "error");
  }
}

async function handleApiFetch() {
  const url = apiUrl.value.trim();
  if (!url) {
    setMessage(apiMessage, "请填写 API 地址。", "error");
    return;
  }
  let headers = null;
  const rawHeaders = apiHeaders.value.trim();
  if (rawHeaders) {
    try {
      headers = JSON.parse(rawHeaders);
    } catch (_error) {
      setMessage(apiMessage, "请求头必须是合法 JSON。", "error");
      return;
    }
  }
  setMessage(apiMessage, "正在拉取快照（仅 https）");
  try {
    const snapshot = await request("/api/ingest/api-snapshot", {
      method: "POST",
      body: JSON.stringify({ url, headers, use_agent: useAgent.checked }),
    });
    currentPath = snapshot.snapshot.path;
    hidePreviewAndPlan();
    renderPreview(snapshot, useAgent.checked ? snapshot.agent_plan : null);
    setMessage(apiMessage, `快照已保存于 ${snapshot.snapshot.fetched_at}，请确认字段映射。`);
  } catch (error) {
    setMessage(apiMessage, error.message, "error");
  }
}

async function handlePlanSubmit(event) {
  event.preventDefault();
  if (!currentPath || !currentPreview) {
    setMessage(planMessage, "请先上传文件或拉取 API 快照。", "error");
    return;
  }
  const plan = {
    format: currentPreview.format,
    date_field: dateField.value,
    metric_field: metricField.value,
    value_field: valueField.value,
    records_path: recordsPath.value.trim(),
    sheet: sheetField.value,
    date_format: dateFormat.value.trim(),
  };
  if (!plan.date_field || !plan.metric_field || !plan.value_field) {
    setMessage(planMessage, "日期、指标、数值三个字段都必须选择。", "error");
    return;
  }
  const payload = { path: currentPath, plan, mode: currentMode };
  const knowledgeValue = knowledgePath.value.trim();
  if (knowledgeValue) {
    payload.knowledge_path = knowledgeValue;
  }
  if (currentMode === "api") {
    let headers = null;
    const rawHeaders = apiHeaders.value.trim();
    if (rawHeaders) {
      try {
        headers = JSON.parse(rawHeaders);
      } catch (_error) {
        headers = null;
      }
    }
    payload.api_config = { url: apiUrl.value.trim(), headers };
  }
  setMessage(planMessage, "正在转换为标准指标数据");
  try {
    const applied = await request("/api/ingest/apply", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resultBox.replaceChildren();
    const summary = document.createElement("p");
    summary.textContent = `已生成标准数据：${applied.result.row_count} 行指标，跳过 ${applied.result.skipped} 行。`;
    resultBox.appendChild(summary);
    const metricsLine = document.createElement("p");
    metricsLine.className = "quiet-copy";
    metricsLine.textContent = `指标：${applied.result.metrics.join("、")} · 日期范围 ${applied.result.date_range[0]} ~ ${applied.result.date_range[1]}`;
    resultBox.appendChild(metricsLine);
    if (applied.result.warnings && applied.result.warnings.length) {
      const warn = document.createElement("details");
      const warnSummary = document.createElement("summary");
      warnSummary.textContent = `跳过明细（${applied.result.warnings.length} 条）`;
      warn.appendChild(warnSummary);
      applied.result.warnings.forEach((text) => {
        const item = document.createElement("p");
        item.className = "quiet-copy";
        item.textContent = text;
        warn.appendChild(item);
      });
      resultBox.appendChild(warn);
    }
    if (applied.knowledge_warning) {
      const warnLine = document.createElement("p");
      warnLine.className = "context-disclosure";
      warnLine.textContent = `提示：${applied.knowledge_warning}`;
      resultBox.appendChild(warnLine);
    }
    const hint = document.createElement("p");
    if (applied.needs_knowledge_path) {
      hint.className = "ingest-warning";
      hint.textContent = "数据源已生成，但仍缺少文档目录——确定性结论需要它作为证据。请在左侧『数据源设置』填写文档目录后立即重试分析。";
    } else {
      hint.className = "context-disclosure";
      hint.textContent = "数据源已切换为标准指标文件，可以开始提问分析了。";
    }
    resultBox.appendChild(hint);
    resultBox.hidden = false;
    setMessage(planMessage, "数据源已更新。", "success");
    await Promise.all([loadProfile(), loadSourceProfile()]);
  } catch (error) {
    setMessage(planMessage, error.message, "error");
  }
}

export function initIngestPanel() {
  tabs.forEach((button) => {
    button.addEventListener("click", () => setIngestTab(button.dataset.ingestTab));
  });
  fileInput.addEventListener("change", handleFileSelected);
  localPathUseButton.addEventListener("click", handleLocalPathUse);
  apiFetchButton.addEventListener("click", handleApiFetch);
  proposeButton.addEventListener("click", handlePropose);
  planForm.addEventListener("submit", handlePlanSubmit);
  setIngestTab("local");
}
