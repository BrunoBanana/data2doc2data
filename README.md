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

- Three built-in fictional synthetic scenarios: supported evidence, strategy conflict, and insufficient evidence
- User-supplied local CSV data
- User-supplied local Markdown / text decision documents
- Three-column evidence workbench for data, deterministic analysis, and assistant collaboration (Chinese)
- Direct web conversations with a locally installed Codex or Tencent WorkBuddy/CodeBuddy
- Read-only, per-operation approval, and trusted-session permission modes
- CLI for configuration, analysis, and status check
- Explicit metric specification when a question cannot uniquely identify one

Deterministic evidence analysis reads and computes over source files locally. Raw CSV rows are never placed in the agent prompt. When you explicitly send an agent message, Data2Doc2Data attaches a bounded evidence snapshot containing source counts, local metric summaries, the matching deterministic result, and only document excerpts relevant to that question. The selected Codex or WorkBuddy provider handles that snapshot under its own account and data policy; the workbench shows the snapshot ID, excerpt count, and compression state for every turn.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
data2doc2data setup
```

Run `data2doc2data setup` from the project directory you want the agent to inspect. The browser page is bound to `127.0.0.1` and detects optional local agents from `PATH`:

- Codex: install and sign in to the Codex CLI, then confirm `codex --version` works. Data2Doc2Data uses the public `codex app-server --stdio` interface.
- Tencent WorkBuddy/CodeBuddy: install and sign in to the Tencent CLI, then confirm `codebuddy --version` works. Data2Doc2Data starts its public loopback service and uses ACP over HTTP/SSE.

Neither agent is required for deterministic analysis. If an agent is missing or unavailable, the evidence workflow remains usable.

## Guided Demo

Open the setup page, keep **Built-in demo**, and choose one of the three scenarios. Each scenario contains a small CSV and Markdown strategy note clearly labeled as fictional synthetic data. Selecting a scenario updates the suggested question but does not run analysis; save the workspace, then select **Start analysis**.

The scenarios intentionally demonstrate three boundaries:

1. activation improves while retention falls, supporting the documented condition;
2. measured directions contradict the strategy expectation;
3. a required second metric is absent, so the result stays insufficient.

## Local Agent Use

After evidence analysis, connect Codex or Tencent WorkBuddy from the same page. Choose a permission mode before starting the session:

- **Read only** blocks commands and file changes.
- **Collaborative** requires a visible approval for every state-changing operation.
- **Trusted session** may reuse a narrowly scoped approval for the same session, operation type, workspace, and command prefix until it expires.

All sessions are restricted to the directory from which `data2doc2data setup` was launched. Browser ownership, CSRF checks, approval expiry, path containment, redacted audit records, interruption, and child-process cleanup are enforced locally. Agent explanations and actions never replace the deterministic analysis result.

The first Codex turn can take up to roughly two minutes while its local app server and tools cold-start; later turns are usually faster. If an agent is shown as unavailable, check the command above, sign-in state, CLI compatibility, and restart `data2doc2data setup`. WorkBuddy requires the `codebuddy` executable; it is not bundled with this project.

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

## Data Source Roadmap

This version does not connect to external vendors. For user-purchasable, configurable future options, see the [connector guide](references/connector-guide.md).

## Privacy & Security

The local helper service listens only on `127.0.0.1`, accepts only expected Host and same-origin browser requests, and has no credential input fields or telemetry. Workspace profiles, document-index cache, resumable session metadata, and redacted audit records are stored in the local configuration directory with restrictive permissions. CSV files are capped at 5 MB, individual documents at 1 MB, and document directories at 200 supported files; oversized files and malformed configs return clear local errors.

## Publishing

This project is licensed under [MIT](LICENSE). Generate a public upload bundle from a clean workspace:

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v3.0.0.zip
```

Upload the ZIP to your target SkillHub. It includes only the explicit public-resource allowlist: `SKILL.md`, the local helper UI, runtime code, the connector guide, and `LICENSE.md` (MIT). It excludes tests, build caches, hidden files, symlinks, and unlisted files such as accidental business exports. The builder rejects included resources containing prohibited private markers, email addresses, or common credential patterns. `--draft` is for local experimentation only — never publish.

---

<a id="中文"></a>

当前版本：**v3.0.0**。请查看[更新日志](CHANGELOG.md)了解从 v1.0.0 开始的版本记录。

Data2Doc2Data 面向真实业务场景，将数据指标与策略、决策文档进行循环推理：先从数据发现信号，再从文本理解业务语境，最后回到数据验证假设，输出可追溯、可行动的业务洞察。

```text
数据信号 → 文档决策语境 → 数据验证 → 可追溯业务洞察
```

## 本版本可用能力

- 三套内置虚构合成数据：证据支持、策略冲突、证据不足
- 使用者自有的本地 CSV 数据
- 使用者自有的本地 Markdown 与文本决策文档
- 数据、确定性分析、助手协作一体化的三栏工作台
- 在网页中直接连接本机 Codex 或腾讯 WorkBuddy/CodeBuddy
- 只读、逐次审批和会话级受限信任三种权限模式
- 命令行配置、分析与状态检查
- 当问题不能唯一定位指标时，支持显式指定指标

确定性分析只在本机读取并计算证据文件，原始 CSV 始终留在本机，不会写入助手提示词。只有使用者明确发送助手消息时，系统才会建立有界证据快照：其中包含数据源计数、本地计算的统计摘要、与当前数据源匹配的确定性结论，以及针对问题检索出的相关文档片段。所选 Codex 或 WorkBuddy 会依据其账户与数据策略处理这份快照；工作台会逐轮展示快照编号、片段数量和压缩状态。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
data2doc2data setup
```

请在希望助手检查的项目目录中运行 `data2doc2data setup`。网页仅绑定 `127.0.0.1`，并从 `PATH` 检测可选的本地助手：

- **Codex**：安装并登录 Codex CLI，确认 `codex --version` 可用。Data2Doc2Data 通过公开的 `codex app-server --stdio` 接口连接。
- **腾讯 WorkBuddy/CodeBuddy**：安装并登录腾讯 CLI，确认 `codebuddy --version` 可用。Data2Doc2Data 启动其公开回环服务，并通过 ACP over HTTP/SSE 连接。

两种助手都不是确定性分析的必需依赖；助手缺失或不可用时，证据分析仍可正常运行。

## 三套内置演示

打开配置页，保留“内置演示”，然后选择一个场景。每套场景都包含小型 CSV 和 Markdown 策略资料，并明确标注为虚构合成数据。切换场景只会更新建议问题，不会自动分析；先保存工作区，再点击“开始分析”。

三套演示分别展示：

1. 激活改善、留存下降，文档条件得到数据支持；
2. 实测方向与策略预期相反，结论标为矛盾；
3. 缺少第二指标，系统明确返回证据不足。

## 在网页中使用本地智能助手

完成证据分析后，可以在同一网页连接 Codex 或腾讯 WorkBuddy。开始会话前选择权限模式：

- **只读模式**：禁止命令和文件变更。
- **协作模式**：每个改变状态的操作都必须在网页中明确批准。
- **信任本次会话**：同一会话中，仅可在有效期内复用与操作类型、工作区和命令前缀严格匹配的批准。

所有会话都限制在启动 `data2doc2data setup` 时所在的目录。浏览器会话归属、CSRF、批准过期、路径边界、审计脱敏、任务中断和子进程清理都在本机执行。助手可以解释和执行，但不能覆盖确定性分析生成的证据结论。

Codex 第一次对话可能因本地 app server 与工具冷启动而耗时约两分钟，后续通常更快。若页面显示助手不可用，请检查对应命令、登录状态和 CLI 兼容性，再重启 `data2doc2data setup`。腾讯 WorkBuddy 必须先安装 `codebuddy`，本项目不会捆绑该程序。

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

## 数据源路线图

本版本不连接外部供应商。关于可由使用者自行购买、授权和配置的后续选择，请查看[数据连接器指南](references/connector-guide.md)。

## 隐私与安全

本地辅助服务仅监听 `127.0.0.1`，只接受预期 Host 和同源浏览器请求，不包含凭据输入框或遥测。工作区配置、文档索引缓存、可恢复会话元数据和脱敏审计记录保存在本地配置目录，并使用受限文件权限。CSV 文件最大 5 MB，单个文档最大 1 MB，文档目录最多 200 个受支持文件；超限文件和格式错误的配置会返回明确的本地错误。

## 发布

本项目采用 [MIT](LICENSE) 许可证。请从干净工作区生成公开上传包：

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v3.0.0.zip
```

将该 ZIP 上传至目标 SkillHub。它仅包含明确列入公开资源白名单的 `SKILL.md`、本地辅助界面、运行时代码、数据连接器指南和 `LICENSE.md` 形式的 MIT 许可证；不包含测试、生成缓存、隐藏文件、符号链接或未列入白名单的意外业务导出文件。构建器还会扫描每个纳入的文本资源，并在发现禁止的私有标记、邮箱地址或常见凭据模式时拒绝构建。`--draft` 仅用于无许可证的本地实验，绝不能发布。
