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
    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (headingMatch) {
      const headingLevel = Math.min(4, headingMatch[1].length + 1);
      const heading = document.createElement(`h${headingLevel}`);
      heading.appendChild(renderInline(headingMatch[2]));
      container.appendChild(heading);
      index += 1;
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      const quote = document.createElement("blockquote");
      quote.appendChild(renderInline(quoteLines.join(" ")));
      container.appendChild(quote);
      continue;
    }
    if (isListLine(lines[index])) {
      index = appendListBlock(container, lines, index);
      continue;
    }
    if (trimmed) {
      const paragraphLines = [];
      while (
        index < lines.length
        && lines[index].trim()
        && !isBlockStart(lines[index])
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

function isListLine(line) {
  return /^\s*(?:[-*]|\d+\.)\s+/.test(line);
}

function isBlockStart(line) {
  const trimmed = line.trim();
  return trimmed.startsWith("```")
    || /^(?:#{1,3}|>)\s+/.test(trimmed)
    || isListLine(line);
}

function appendListBlock(container, lines, startIndex) {
  const first = /^\s*(?:(\d+)\.|([-*]))\s+(.+)$/.exec(lines[startIndex]);
  const root = document.createElement(first[1] ? "ol" : "ul");
  const stack = [{ indent: leadingSpaces(lines[startIndex]), list: root, item: null }];
  let index = startIndex;
  while (index < lines.length && isListLine(lines[index])) {
    const match = /^\s*(?:(\d+)\.|([-*]))\s+(.+)$/.exec(lines[index]);
    const indent = leadingSpaces(lines[index]);
    while (stack.length > 1 && indent < stack[stack.length - 1].indent) stack.pop();
    if (indent > stack[stack.length - 1].indent && stack[stack.length - 1].item) {
      const nested = document.createElement(match[1] ? "ol" : "ul");
      stack[stack.length - 1].item.appendChild(nested);
      stack.push({ indent, list: nested, item: null });
    }
    const item = document.createElement("li");
    item.appendChild(renderInline(match[3]));
    stack[stack.length - 1].list.appendChild(item);
    stack[stack.length - 1].item = item;
    index += 1;
  }
  container.appendChild(root);
  return index;
}

function leadingSpaces(line) {
  return line.length - line.trimStart().length;
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
