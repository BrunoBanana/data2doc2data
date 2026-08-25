# Agent / Harness 接入

Data2Doc2Data 同时支持三种产品形态：浏览器本地工作台、网页内连接本机 Codex/腾讯 CodeBuddy，以及包含原生插件清单、自动发现 Skill 和 MCP 工具的宿主 Agent 插件。MCP 是插件的工具协议，不是插件能力的全部。

Codex 使用 `.codex-plugin/plugin.json`，腾讯 WorkBuddy 使用 `.codebuddy-plugin/plugin.json`；两者共享 `skills/data2doc2data/SKILL.md` 和当前项目 `.venv` 中的本地运行时。DeepSeek Harness 保持标准 MCP/Cordis 接入。

开始前先安装项目并运行：

```bash
data2doc2data doctor --json
```

当结果为 `"ok": true` 时，按宿主选择配置：

- [`codex/`](codex/)：Codex CLI / App 的 `config.toml` 或 `codex mcp add`。
- [`deepseek-harness/`](deepseek-harness/)：官方 `@deepseek-ai/dsh-mcp-client` Cordis overlay。
- [`codebuddy/`](codebuddy/)：腾讯 CodeBuddy/WorkBuddy 项目级 `.mcp.json` 或 `codebuddy mcp add`。

Codex 与 WorkBuddy/CodeBuddy 还可以直接注册当前虚拟环境：

```bash
.venv/bin/data2doc2data install-mcp --host codebuddy --scope user
.venv/bin/data2doc2data install-mcp --host codex
```

追加 `--dry-run` 可以先检查命令，不改动宿主。三种宿主都启动同一个本地 MCP 服务，共提供 15 个工具。推荐优先使用 `analyze_business_case` 完成自然语言材料分析和 HTML 交付；需要自主迭代时使用 `create_analysis_task`、`run_diagnostic_step`、`evaluate_task_rules` 和 `get_analysis_trace`。宿主只接收有界统计、证据状态、来源文件名和产物引用，不接收原始 CSV 行或绝对来源路径。

可直接交给 WorkBuddy 的真实业务提示词：

> 请把当前项目安装为你自己的本地数据+文档交叉分析工具。先检查项目根目录的 SKILL.md 和 doctor 自检；如果尚未安装，创建 .venv、安装项目，然后运行 `.venv/bin/data2doc2data install-mcp --host codebuddy --scope user`。如果需要 MCP 安全批准或重新载入，请清楚提示我。安装成功后，读取 `src/data2doc2data/sample/cases/retail-promotion-fulfillment` 中的经营数据、财务复盘、履约记录和运营材料，判断大促增长是否以毛利、退款、履约和复购为代价。优先使用 `analyze_business_case`，或者根据实际证据自主调用深度分析与规则验证工具。不要修改全局数据源配置，不要把原始数据塞进模型上下文，不要让我手工处理 task_id。最后用管理层能理解的语言汇报结论、反证、限制与行动建议，并给出可离线打开的 HTML 报告。
