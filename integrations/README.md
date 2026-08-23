# Agent / Harness 接入

Data2Doc2Data 同时支持三种产品形态：浏览器本地工作台、网页内连接本机 Codex/腾讯 CodeBuddy，以及作为 MCP 工具运行在 Codex、DeepSeek Harness、CodeBuddy/WorkBuddy 等宿主中。

开始前先安装项目并运行：

```bash
data2doc2data doctor --json
```

当结果为 `"ok": true` 时，按宿主选择配置：

- [`codex/`](codex/)：Codex CLI / App 的 `config.toml` 或 `codex mcp add`。
- [`deepseek-harness/`](deepseek-harness/)：官方 `@deepseek-ai/dsh-mcp-client` Cordis overlay。
- [`codebuddy/`](codebuddy/)：腾讯 CodeBuddy/WorkBuddy 项目级 `.mcp.json` 或 `codebuddy mcp add`。

三种配置都启动同一条本地命令 `data2doc2data mcp`，暴露 `analyze`、`check_rules`、`source_profile` 三个工具。宿主只接收有界统计、证据状态和来源计数，不接收原始 CSV 行。
