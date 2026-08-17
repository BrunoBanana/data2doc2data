// Entry point: wires the workspace tabs and starts each panel.

import { initializeWorkspace } from "./data-panel.js";
import { loadAgents } from "./assistant-panel.js";

const workbenchShell = document.querySelector("#workbench-shell");
const workspaceTabs = Array.from(document.querySelectorAll("[data-workspace-tab]"));

function setupWorkspaceTabs() {
  if (!workbenchShell || workspaceTabs.length === 0) return;
  const activate = (selected) => {
    workspaceTabs.forEach((tab) => {
      const active = tab === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    workbenchShell.dataset.activeWorkspace = selected.dataset.workspaceTab;
  };
  workspaceTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let targetIndex = index;
      if (event.key === "ArrowRight") targetIndex = (index + 1) % workspaceTabs.length;
      if (event.key === "ArrowLeft") targetIndex = (index - 1 + workspaceTabs.length) % workspaceTabs.length;
      if (event.key === "Home") targetIndex = 0;
      if (event.key === "End") targetIndex = workspaceTabs.length - 1;
      if (targetIndex === index) return;
      event.preventDefault();
      activate(workspaceTabs[targetIndex]);
      workspaceTabs[targetIndex].focus();
    });
  });
}

async function initializeApplication() {
  setupWorkspaceTabs();
  // Agent 检测（子进程）与工作区数据加载互不依赖，并行执行以缩短首屏时间。
  await Promise.all([loadAgents(), initializeWorkspace()]);
}

initializeApplication();
