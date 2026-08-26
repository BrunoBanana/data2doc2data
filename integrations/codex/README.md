# Codex 原生插件与 MCP 接入

项目包含 `.codex-plugin/plugin.json`、`skills/data2doc2data/SKILL.md` 和本地 MCP 启动器，能够作为 Codex 原生插件被宿主识别；MCP 也可以独立注册。先确认 `.venv/bin/data2doc2data doctor --json` 返回 `"ok": true`，然后使用一键注册：

```bash
.venv/bin/data2doc2data install-mcp --host codex
```

安装器固定使用当前虚拟环境的可执行文件；加 `--dry-run` 可以预览。也可将 `config.toml.example` 中的配置合并到 `~/.codex/config.toml`，或手动运行：

```bash
codex mcp add data2doc2data -- .venv/bin/data2doc2data mcp
```

重新载入 Codex 后用 `/mcp` 确认全部 15 个工具已加载。优先使用 `analyze_business_case` 处理真实业务材料；需要逐步自主推理时使用 `create_analysis_task`、`run_diagnostic_step`、`evaluate_task_rules` 和 `generate_html_report`。服务通过 stdio 在本机运行，不需要额外模型 API Key，也不会把原始 CSV 行返回给 Codex。
