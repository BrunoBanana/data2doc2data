// Small, side-effect-free presentation helpers shared across modules.

import { METRIC_LABELS } from "./state.js";

export function setMessage(element, message = "", state = "") {
  element.textContent = message;
  element.dataset.state = state;
}

export function formatMetric(metric) {
  return METRIC_LABELS[metric] || metric.replaceAll("_", " ");
}

export function formatStatus(status, labels) {
  return labels[status] || status.replaceAll("_", " ");
}

export function formatObject(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return "无法显示此操作的详细内容。";
  }
}

export function agentLabel(name) {
  return name;
}

export function formatAgentOption(agent) {
  return agent.name;
}

export function renderMarkdown(container, text) {
  container.replaceChildren();
  const lines = text.split("\n");
  let index = 0;
  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (trimmed.startsWith("```")) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      index += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.appendChild(code);
      container.appendChild(pre);
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const list = document.createElement("ul");
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        const item = document.createElement("li");
        item.appendChild(renderInline(lines[index].trim().replace(/^[-*]\s+/, "")));
        list.appendChild(item);
        index += 1;
      }
      container.appendChild(list);
      continue;
    }
    if (/^\d+\.\s+/.test(trimmed)) {
      const list = document.createElement("ol");
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        const item = document.createElement("li");
        item.appendChild(renderInline(lines[index].trim().replace(/^\d+\.\s+/, "")));
        list.appendChild(item);
        index += 1;
      }
      container.appendChild(list);
      continue;
    }
    if (trimmed) {
      const paragraphLines = [];
      while (
        index < lines.length
        && lines[index].trim()
        && !/^([-*]|\d+\.)\s+/.test(lines[index].trim())
        && !lines[index].trim().startsWith("```")
      ) {
        paragraphLines.push(lines[index].trim());
        index += 1;
      }
      const paragraph = document.createElement("p");
      paragraph.appendChild(renderInline(paragraphLines.join(" ")));
      container.appendChild(paragraph);
      continue;
    }
    index += 1;
  }
}

function renderInline(text) {
  const fragment = document.createDocumentFragment();
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      fragment.appendChild(strong);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      fragment.appendChild(code);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
  return fragment;
}
