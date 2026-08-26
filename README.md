# Data2Doc2Data-面向真实业务的数据+文本循环推理架构

**[中文](#中文) | [English](#english)**

---

<a id="english"></a>

Current version: **v3.0.0**. See the [changelog](CHANGELOG.md) for release history from v1.0.0.

Data2Doc2Data is built for real business scenarios. It loops between data metrics and strategy/decision documents: first discover signals from data, then understand business context from text, and finally return to data to verify hypotheses — producing traceable, actionable business insights.

```text
Data Signal → Document Context → Data Verification → Traceable Insight
```

## Capabilities

- Two complete flagship case packs (468 metric rows, 9 documents) plus three focused boundary scenarios
- User-supplied local CSV data
- Native local CSV/XLSX data, Markdown/TXT decisions, and mixed HTML/DOCX reports containing both narrative and tables
- Paper-style business analysis workbench with a fixed Agent Console and a live five-lane execution canvas (Chinese)
- Dual runners: a complete no-model Demo flow and Agent-authored connected plans executed by host-owned local tools
- Task-first React workbench with immutable run history, cursor replay, evidence/hypothesis graphs, and safe retry
- Standalone, print-ready HTML reports with inline SVG and source provenance; no CDN is required
- Direct web conversations with a locally installed Codex or Tencent WorkBuddy/CodeBuddy
- Native Codex and WorkBuddy plugin manifests, an auto-discovered host Skill, and a shared local MCP runtime
- Read-only, per-operation approval, and trusted-session permission modes
- CLI for configuration, analysis, status, MCP serving, and read-only integration diagnostics
- Explicit metric specification when a question cannot uniquely identify one

Deterministic evidence analysis reads and computes over source files locally. Raw CSV rows are never placed in the agent prompt. When you explicitly send an agent message, Data2Doc2Data attaches a bounded evidence snapshot containing source counts, local metric summaries, the matching deterministic result, and only document excerpts relevant to that question. The selected Codex or WorkBuddy provider handles that snapshot under its own account and data policy; the workbench shows the snapshot ID, excerpt count, and compression state for every turn.

## Quick start

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) once, then run:

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web
```

This single command downloads DDD from GitHub, creates an isolated cached environment, installs its dependencies, starts the workbench at `http://127.0.0.1:8781`, and opens it in the default browser. No model, API key, data file, or document is required for Demo mode.

For SSH or a launch where the browser should stay closed, append `--no-open`; DDD will print the local URL instead.

## Developer installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ddd web
```

Run `ddd web` from the project directory you want the agent to inspect. The browser page is bound to `127.0.0.1` and detects optional local agents from `PATH`. The previous `data2doc2data setup` command remains supported for compatibility.

- Codex: install and sign in to the Codex CLI, then confirm `codex --version` works. Data2Doc2Data uses the public `codex app-server --stdio` interface.
- Tencent WorkBuddy/CodeBuddy: install and sign in to the Tencent CLI, then confirm `codebuddy --version` works. Data2Doc2Data starts its public loopback service and uses ACP over HTTP/SSE.

Neither agent is required for deterministic analysis. If an agent is missing or unavailable, the evidence workflow remains usable.

The workbench now starts from an analysis task rather than a chat. Import a local file, upload a supported file, or create a locked snapshot from an HTTPS API; optional Markdown/TXT materials are preprocessed into topics, entities, and pending claims. Runs persist calculations, retrievals, claims, validations, and evidence links as observable events. The player can pause, seek, change speed, or skip to the result, but never presents private chain-of-thought as evidence. The right drawer is the only conversational surface.

Use **Download HTML report** in a task to generate one authenticated, self-contained file. It leads with an analysis conclusion and evidence-verification scorecard, then includes KPI findings, inline SVG charts, text claims with line citations, evidence/hypothesis status, next steps, open questions, caveats, locked snapshot IDs, and expandable calculation provenance. The downloaded file has no external resources, agent-authored markup, local paths, raw records, or secrets and can be opened offline or printed.

## Demo and connected journeys

The first screen has two explicit paths. **Try Demo now** runs a complete deterministic experience without an API or local model. **Connect an Agent** selects Codex or Tencent WorkBuddy/CodeBuddy, then lets the user load either flagship material pack or their own data/documents. The packs contain 468 synthetic metric records and 9 documents in total; connected mode receives the material, not the Demo's expected hypotheses or answers.

Both runners emit the same typed public events. The blank flow canvas grows as the host profiles data, extracts claims, aligns evidence, tests hypotheses, and produces the report. It shows tool inputs/outputs, evidence links, status, and provenance—not model-private chain-of-thought.

The scenarios intentionally demonstrate three boundaries:

1. activation improves while retention falls, supporting the documented condition;
2. measured directions contradict the strategy expectation;
3. a required second metric is absent, so the result stays insufficient.

## Local Agent Use

After evidence analysis, connect Codex or Tencent WorkBuddy from the same page. Choose a permission mode before starting the session:

- **Read only** blocks commands and file changes.
- **Collaborative** requires a visible approval for every state-changing operation.
- **Trusted session** may reuse a narrowly scoped approval for the same session, operation type, workspace, and command prefix until it expires.

All sessions are restricted to the directory from which `ddd web` was launched. Browser ownership, CSRF checks, approval expiry, path containment, redacted audit records, interruption, and child-process cleanup are enforced locally. Agent explanations and actions never replace the deterministic analysis result.

The first Codex turn can take up to roughly two minutes while its local app server and tools cold-start; later turns are usually faster. If an agent is shown as unavailable, check the command above, sign-in state, CLI compatibility, and restart `ddd web`. WorkBuddy requires the `codebuddy` executable; it is not bundled with this project.

### Grounded context and long conversations

Each message creates a new server-owned evidence snapshot from the active source profile. Local computation produces record, metric, date, and document counts plus per-metric first/last/change summaries; matching deterministic findings and query-relevant document excerpts are then added. Raw CSV rows remain local. If the configured byte budget is exceeded, lower-ranked excerpts are dropped automatically and the snapshot is marked compressed. This supports repeated turns without treating the entire dataset or full conversation as model context. Saving a different data source invalidates the previous deterministic result before the next turn.

## Local Data Format

CSV must contain the following core columns; each metric to analyze needs at least two dated observations:

```csv
date,metric,value
2026-01-05,retention_rate,0.66
```

Place related `.md` or `.txt` decision documents in the same directory. The local UI validates both paths before saving a workspace.

## Running Analysis

```bash
data2doc2data analyze --question "Why did retention drop?"
```

If the question cannot uniquely identify a metric, specify it explicitly instead of accepting a guess:

```bash
data2doc2data analyze --question "What changed?" --metric retention_rate
```

Results present: measured signal, most relevant document context, verification status, and local source paths used. Analysis is refused when no metric is resolved or fewer than two observations exist; zero-relevance documents are flagged as insufficient evidence; document matching is context only unless backed by data verification. A transparent "activation up, retention down" dual-metric verification rule is built in.

## MCP Tool Interface

Run the deterministic engine as a tool server for any MCP-capable agent (Codex, Tencent WorkBuddy, DeepSeek harness, or a generic client):

```bash
data2doc2data mcp
```

It exposes 15 tools over stdio. The preferred `analyze_business_case` workflow discovers a directory or a mixed HTML/DOCX report, creates an isolated task, locks local snapshots, profiles data, runs deep numerical/text diagnostics, evaluates every declared business-rule clause, and returns a standalone HTML report. For agent-directed work, combine `inspect_sources`, `create_analysis_task`, `analyze_task_metric`, `run_diagnostic_step`, and `evaluate_task_rules`; use `get_analysis_trace`, `run_analysis_cycle`, `resume_analysis_cycle`, and `list_cycle_artifacts` for observation and recovery. `generate_html_report` and `generate_cycle_html_report` share the same truthful persisted run state. `analyze`, `check_rules`, and `source_profile` remain available for compatibility. Task-scoped tools never modify the global profile or return raw rows and absolute source paths.

The repository is also a native plugin, not merely an MCP endpoint: `.codex-plugin/plugin.json` and `.codebuddy-plugin/plugin.json` declare the host integrations, while `skills/data2doc2data/SKILL.md` teaches the host Agent when and how to orchestrate the tools. The plugin launcher always prefers this project's `.venv` over an unrelated executable on global `PATH`. Validate the WorkBuddy plugin with `codebuddy plugin validate .`, or load the local plugin for development with `codebuddy --plugin-dir /absolute/path/to/data2doc2data`.

Register the executable from the current Python environment with one command:

```bash
data2doc2data install-mcp --host codebuddy --scope user
data2doc2data install-mcp --host codex
```

Append `--dry-run` to inspect the exact host command without changing its configuration. The host may require a one-time MCP security approval or a refreshed conversation. For optional PDF conversion, install `python -m pip install -e '.[documents]'`; scanned images and chart pixels are not claimed as extracted evidence without an explicit OCR/vision adapter.

If a host cannot reload newly registered MCP tools in its current conversation, the same complete local workflow is also available without any manual task ID:

```bash
data2doc2data analyze-case --question "Did promotion growth hurt margin and fulfillment?" \
  --source src/data2doc2data/sample/cases/retail-promotion-fulfillment \
  --output business-review.html
```

Verify the full local contract before connecting a host:

```bash
data2doc2data doctor --json
```

Copy-ready configurations and host-specific instructions are included under [`integrations/`](integrations/README.md): Codex `config.toml`, DeepSeek Harness Cordis overlay, and Tencent CodeBuddy/WorkBuddy project `.mcp.json`.

## Data Source Roadmap

This version does not connect to external vendors. For user-purchasable, configurable future options, see the [connector guide](references/connector-guide.md).

## Privacy & Security

The local helper service listens only on `127.0.0.1`, accepts only expected Host and same-origin browser requests, and has no credential input fields or telemetry. Workspace profiles, document-index cache, resumable session metadata, and redacted audit records are stored in the local configuration directory with restrictive permissions. CSV files are capped at 5 MB, individual documents at 1 MB, and document directories at 200 supported files; oversized files and malformed configs return clear local errors.

## Publishing

This project is licensed under [MIT](LICENSE). Generate a public upload bundle from a clean workspace:

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v3.0.0.zip
```

Upload the ZIP to your target SkillHub. It includes only the explicit public-resource allowlist: the root and host-discovered Skills, the two explicitly approved native plugin manifests, the local helper UI, runtime code, the connector guide, and `LICENSE.md` (MIT). All other hidden files, tests, build caches, symlinks, private presentations, and unlisted files such as accidental business exports are excluded. The builder rejects included resources containing prohibited private markers, email addresses, or common credential patterns. `--draft` is for local experimentation only — never publish.

---

<a id="中文"></a>

当前版本：**v3.0.0**。请查看[更新日志](CHANGELOG.md)了解从 v1.0.0 开始的版本记录。

Data2Doc2Data 面向真实业务场景，将数据指标与策略、决策文档进行循环推理：先从数据发现信号，再从文本理解业务语境，最后回到数据验证假设，输出可追溯、可行动的业务洞察。

```text
数据信号 → 文档决策语境 → 数据验证 → 可追溯业务洞察
```

## 本版本可用能力

- 两套完整旗舰材料包（共 468 条指标记录、9 份文档），并附带三个边界场景
- 原生识别本地 CSV / XLSX 数据、Markdown / TXT 文档，以及同时包含文字和表格的 HTML / DOCX 复盘报告
- Paper 风格三栏工作台：固定 Agent Console 与五泳道动态执行画布
- 双运行器：无需模型的完整 Demo Flow，以及由 Agent 规划、宿主本地工具执行的连接模式
- 任务优先的 React 工作台：不可变运行历史、游标回放、证据/假设图与安全重试
- 可下载、可打印的单文件 HTML 报告：内联 SVG 与完整来源口径，无需 CDN
- 在网页中直接连接本机 Codex 或腾讯 WorkBuddy/CodeBuddy
- Codex / WorkBuddy 原生插件清单、可自动发现的宿主 Skill，以及共享的本地 MCP 工具服务
- 只读、逐次审批和会话级受限信任三种权限模式
- 命令行配置、分析与状态检查
- 当问题不能唯一定位指标时，支持显式指定指标

确定性分析只在本机读取并计算证据文件，原始 CSV 始终留在本机，不会写入助手提示词。只有使用者明确发送助手消息时，系统才会建立有界证据快照：其中包含数据源计数、本地计算的统计摘要、与当前数据源匹配的确定性结论，以及针对问题检索出的相关文档片段。所选 Codex 或 WorkBuddy 会依据其账户与数据策略处理这份快照；工作台会逐轮展示快照编号、片段数量和压缩状态。

## 快速开始

首次使用先安装一次 [`uv`](https://docs.astral.sh/uv/getting-started/installation/)，然后运行：

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web
```

这一条命令会自动从 GitHub 下载 DDD、创建隔离且可复用的运行环境、安装依赖、在 `http://127.0.0.1:8781` 启动工作台并打开默认浏览器。Demo 模式不需要模型、API Key、数据文件或文档，启动后即可体验完整流程。

通过 SSH 启动或不希望自动打开浏览器时，在命令末尾添加 `--no-open`；DDD 会直接打印本地访问地址。

## 开发者安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ddd web
```

请在希望助手检查的项目目录中运行 `ddd web`。网页仅绑定 `127.0.0.1`，并从 `PATH` 检测可选的本地助手。原有的 `data2doc2data setup` 命令继续保留，兼容已有脚本。

- **Codex**：安装并登录 Codex CLI，确认 `codex --version` 可用。Data2Doc2Data 通过公开的 `codex app-server --stdio` 接口连接。
- **腾讯 WorkBuddy/CodeBuddy**：安装并登录腾讯 CLI，确认 `codebuddy --version` 可用。Data2Doc2Data 启动其公开回环服务，并通过 ACP over HTTP/SSE 连接。

两种助手都不是确定性分析的必需依赖；助手缺失或不可用时，证据分析仍可正常运行。

工作台现在从“业务分析任务”而不是聊天开始。使用者可以接入本地路径、上传文件或 HTTPS API 锁定快照，并可选导入 Markdown/TXT；系统会生成数据画像、主题、实体和待核验主张。每次运行都会把计算、检索、主张、验证与证据连接保存为可观察事件。过程播放器支持暂停、拖动、调速和直达结果，但不会把模型私有思维链伪装成证据；对话只位于右侧助手抽屉。

任务顶部的“下载 HTML 报告”会生成一个经过会话授权的自包含文件。报告依次提供 Executive Summary、KPI 与内联 SVG 图表、带行号引用的文本主张、证据/假设状态、下一步、待回答问题、局限、锁定快照与可展开的计算口径。文件不含外链资源、Agent 生成的 HTML、本地路径、原始数据行或凭据，可离线打开和打印。

## Demo 与连接 Agent 两条体验路径

首屏提供两条明确路径：“立即体验 Demo”无需 API 或本地模型即可运行完整确定性流程；“连接 Agent 开始分析”先选择 Codex 或腾讯 WorkBuddy/CodeBuddy，再使用两套旗舰材料包或导入自己的数据/文档。旗舰材料包共含 468 条虚构合成数据记录与 9 份文档；连接模式只复用材料，不会注入 Demo 的预设假设和答案。

两种运行器产生相同的类型化公开事件。空白画布会随本地数据画像、文本主张抽取、证据对齐、假设检验和报告生成逐步生长，展示工具输入输出、证据关系、状态和口径，但不会展示模型私有思维链。

三套演示分别展示：

1. 激活改善、留存下降，文档条件得到数据支持；
2. 实测方向与策略预期相反，结论标为矛盾；
3. 缺少第二指标，系统明确返回证据不足。

## 在网页中使用本地智能助手

完成证据分析后，可以在同一网页连接 Codex 或腾讯 WorkBuddy。开始会话前选择权限模式：

- **只读模式**：禁止命令和文件变更。
- **协作模式**：每个改变状态的操作都必须在网页中明确批准。
- **信任本次会话**：同一会话中，仅可在有效期内复用与操作类型、工作区和命令前缀严格匹配的批准。

所有会话都限制在启动 `ddd web` 时所在的目录。浏览器会话归属、CSRF、批准过期、路径边界、审计脱敏、任务中断和子进程清理都在本机执行。助手可以解释和执行，但不能覆盖确定性分析生成的证据结论。

Codex 第一次对话可能因本地 app server 与工具冷启动而耗时约两分钟，后续通常更快。若页面显示助手不可用，请检查对应命令、登录状态和 CLI 兼容性，再重启 `ddd web`。腾讯 WorkBuddy 必须先安装 `codebuddy`，本项目不会捆绑该程序。

### 证据上下文与多轮对话

每次发送消息，服务端都会基于当前数据源重新创建一份证据快照。本地计算先生成记录数、指标数、日期范围、文档数和各指标的首值、末值与变化统计，再加入与当前数据源匹配的确定性分析结果和按本轮问题检索的相关文档片段。原始 CSV 始终留在本机。超过上下文字节预算时，系统会自动压缩，按相关度移除排名靠后的片段并在页面明确标记，不会把完整数据集或整段历史对话塞入模型上下文。切换数据源后，旧的确定性分析会立即失效，避免跨数据集引用旧结论。

## 本地数据格式

CSV 必须包含以下核心列；每个待分析指标至少需要两条带日期的观测值：

```csv
date,metric,value
2026-01-05,retention_rate,0.66
```

将相关的 `.md` 或 `.txt` 决策文档放在同一目录。本地页面会在保存工作区前校验两个路径。

## 发起分析

```bash
data2doc2data analyze --question "留存为什么下降？"
```

如果问题不能唯一定位指标，请显式指定，而不是接受猜测结果：

```bash
data2doc2data analyze --question "发生了什么变化？" --metric retention_rate
```

结果会依次给出测得信号、最相关的文档语境、验证状态和所用本地来源路径。未解析出指标或指标少于两条观测值时会拒绝分析；零相关度文档会被标为证据不足；文档匹配仅是语境，除非另有数据验证。当前内置一条透明的"激活上升、留存下降"双指标验证规则。

## MCP 工具接口

将确定性引擎作为工具服务器，供任意支持 MCP 的助手（Codex、腾讯 WorkBuddy、DeepSeek harness 或通用客户端）直接调用：

```bash
data2doc2data mcp
```

它通过 stdio 暴露 15 个工具。推荐的 `analyze_business_case` 可以从一次自然语言请求直接完成材料识别、隔离建任务、不可变快照锁定、本地深度计算、文本分析、声明式规则逐条实测，以及离线 HTML 报告交付；用户不需要知道或输入 `task_id`。

项目同时也是宿主可识别的原生插件，而不仅仅是 MCP 服务：`.codex-plugin/plugin.json` 和 `.codebuddy-plugin/plugin.json` 分别提供 Codex、WorkBuddy 的插件清单；`skills/data2doc2data/SKILL.md` 让宿主 Agent 知道何时触发、如何调度和怎样交付。启动器优先使用项目自己的 `.venv`，不会误连系统 PATH 中的旧版本。可以通过 `codebuddy plugin validate .` 验证 WorkBuddy 插件，或执行 `codebuddy --plugin-dir /项目绝对路径` 加载本地开发版本。

对于需要 Agent 自主判断的复杂问题，宿主可以依次调用 `inspect_sources`、`create_analysis_task`、`analyze_task_metric`、`run_diagnostic_step` 和 `evaluate_task_rules`，根据已经产生的真实证据继续决定下一步。`get_analysis_trace`、`run_analysis_cycle`、`resume_analysis_cycle`、`list_cycle_artifacts` 提供公开执行轨迹、检查点和恢复能力；`generate_html_report`、`generate_cycle_html_report` 使用同一份已完成运行状态。旧版 `analyze`、`check_rules`、`source_profile` 保持兼容，但 `check_rules` 只是结构校验，不能替代实际规则验证。任务级工具不会修改全局 profile，也不会返回原始数据行或绝对来源路径。

一条命令即可注册当前 Python 环境中的正确可执行文件：

```bash
data2doc2data install-mcp --host codebuddy --scope user
data2doc2data install-mcp --host codex
```

加 `--dry-run` 可以先预览注册命令，不修改宿主。WorkBuddy/CodeBuddy 首次使用可能需要用户批准 MCP 服务或刷新会话。CSV、XLSX、Markdown、TXT、HTML、DOCX 可直接使用；PDF 等可选格式需要执行 `python -m pip install -e '.[documents]'`。未安装专门的 OCR/视觉适配器时，不能把扫描件或图表像素假装成已经提取的证据。

如果宿主当前对话暂时不能动态加载新注册的 MCP 服务，也可直接执行等价的完整本地分析，不需要手动创建任务：

```bash
data2doc2data analyze-case --question "大促增长是否以利润、履约和复购为代价？" \
  --source src/data2doc2data/sample/cases/retail-promotion-fulfillment \
  --output business-review.html
```

接入宿主前，先运行只读自检：

```bash
data2doc2data doctor --json
```

项目的 [`integrations/`](integrations/README.md) 目录提供 Codex `config.toml`、DeepSeek Harness Cordis overlay 和腾讯 CodeBuddy/WorkBuddy 项目级 `.mcp.json` 的可复制配置与说明。

## 数据源路线图

本版本不连接外部供应商。关于可由使用者自行购买、授权和配置的后续选择，请查看[数据连接器指南](references/connector-guide.md)。

## 隐私与安全

本地辅助服务仅监听 `127.0.0.1`，只接受预期 Host 和同源浏览器请求，不包含凭据输入框或遥测。工作区配置、文档索引缓存、可恢复会话元数据和脱敏审计记录保存在本地配置目录，并使用受限文件权限。CSV 文件最大 5 MB，单个文档最大 1 MB，文档目录最多 200 个受支持文件；超限文件和格式错误的配置会返回明确的本地错误。

## 发布

本项目采用 [MIT](LICENSE) 许可证。请从干净工作区生成公开上传包：

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v3.0.0.zip
```

将该 ZIP 上传至目标 SkillHub。它仅包含明确列入公开资源白名单的根 Skill、宿主自动发现的 Skill、两份已审核的原生插件清单、本地辅助界面、运行时代码、数据连接器指南和 `LICENSE.md` 形式的 MIT 许可证；其他隐藏文件、测试、生成缓存、私人答辩材料、符号链接或未列入白名单的意外业务导出文件均不会进入发布包。构建器还会扫描每个纳入的文本资源，并在发现禁止的私有标记、邮箱地址或常见凭据模式时拒绝构建。`--draft` 仅用于无许可证的本地实验，绝不能发布。
