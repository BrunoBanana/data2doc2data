# DeepSeek Harness MCP 接入

先确认 `data2doc2data doctor --json` 通过，并根据 Harness 版本安装匹配版本的 `@deepseek-ai/dsh-mcp-client`。将示例作为 overlay 传入：

```bash
dsh web --patch integrations/deepseek-harness/data2doc2data.cordis.yml.example
```

如需长期启用，把这条插件配置合并到对应 profile 的 `cordis.patch.yml`；不要覆盖已有 patch。15 个工具将以 `mcp__data2doc2data__*` 的名称暴露。优先使用 `analyze_business_case` 一次完成材料识别、隔离任务、本地计算、规则实证和离线 HTML 报告；需要由 Harness 自主选择分析方法时，则组合 `create_analysis_task`、`run_diagnostic_step`、`evaluate_task_rules`、`get_analysis_trace` 与 `generate_html_report`。
