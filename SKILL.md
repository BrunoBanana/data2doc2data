---
name: data2doc2data
description: 面向真实业务场景，将本地数据指标与策略、决策文档交叉验证，输出可追溯的 Data-to-Doc-to-Data 洞察。适用于解释指标变化、用本地 CSV 和文档验证策略假设、配置本地证据工作区，或检查业务建议背后的数据与文本依据。
---

# Data2Doc2Data-面向真实业务的数据+文本循环推理架构

使用此 Skill 将业务问题转化为本地证据闭环：

1. 自动识别用户给出的材料目录、CSV/XLSX、Markdown/TXT，或者同时包含文字和表格的 HTML/DOCX 复盘报告。
2. 自动建立隔离分析任务并锁定不可变快照，不要求用户知道、输入或管理 `task_id`。
3. 由宿主 Agent 调度本地指标计算、异常与变点检测、分组/归因、文本主题聚类和数据—文本交叉验证。
4. 实际验证每条业务规则，明确区分获得支持、存在冲突与证据不足，并自动交付离线 HTML 报告。
5. 只向宿主返回有界统计、证据片段、来源文件名和可审计产物引用；不返回原始记录或绝对来源路径。

## 首次使用

若用户明确要求在 WorkBuddy/CodeBuddy 或 Codex 中安装插件，先在项目目录建立独立环境并注册当前环境中的实际可执行文件：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/data2doc2data doctor --json
.venv/bin/data2doc2data install-mcp --host codebuddy --scope user
```

Codex 改用 `.venv/bin/data2doc2data install-mcp --host codex`。先加 `--dry-run` 可以预览准确注册命令而不修改宿主。首次接入如果出现 MCP 安全批准或宿主需要重新打开会话，请告知用户批准/刷新；不要静默绕过宿主权限。DeepSeek Harness 使用 [`integrations/deepseek-harness/README.md`](integrations/deepseek-harness/README.md) 的现有 Cordis 配置。

项目还包含 `.codex-plugin/plugin.json` 与 `.codebuddy-plugin/plugin.json` 原生插件清单，以及 `skills/data2doc2data/SKILL.md` 自动发现入口。腾讯宿主可用 `codebuddy plugin validate .` 校验；不要为了安装插件额外创建根目录 `.mcp.json`，以免遮蔽已批准的用户级 MCP 服务。

如果宿主暂时不能在当前对话动态加载新注册的 MCP 工具，但用户已经授权通过命令行分析，可用同样的完整本地流程作为回退，不要求用户提供任务 ID：

```bash
.venv/bin/data2doc2data analyze-case \
  --question "大促增长是否以利润、履约和复购为代价？" \
  --source src/data2doc2data/sample/cases/retail-promotion-fulfillment \
  --output business-review.html
```

用户希望使用浏览器本地工作台时，在打开页面前先征得用户同意，然后执行：

```bash
data2doc2data setup
```

本地页面提供两套完整虚构合成旗舰材料包，以及三套边界场景和本地文件模式；确定性分析不会将源数据发送到托管服务。

三套演示分别用于说明：文档假设获得支持、策略与数据矛盾、缺少第二指标时证据不足。场景切换只更新建议问题，必须由使用者明确保存并开始分析。

## 分析已有工作区

使用本地配置页，或执行：

```bash
data2doc2data analyze --question "发生了什么变化？应该重新审视哪项文档假设？"
```

如果问题无法唯一定位指标，要求使用者明确指定：

```bash
data2doc2data analyze --question "发生了什么变化？" --metric retention_rate
```

按以下顺序呈现结果：

1. 数据信号
2. 文档语境
3. 验证状态：获得数据支持、与策略矛盾、证据有限或证据不足
4. 证据来源与明确的限制条件

## 连接本地智能助手

使用者希望在网页继续解释或执行时，可连接已安装且已登录的 Codex 或腾讯 WorkBuddy/CodeBuddy：

- Codex 需要 `codex --version` 可用；通过 `codex app-server --stdio` 连接。
- 腾讯 WorkBuddy 需要 `codebuddy --version` 可用；通过其公开 ACP over HTTP/SSE 服务连接。
- 助手缺失时不得阻断确定性分析。
- 连接前让使用者选择只读模式、协作模式或信任本次会话；改变状态的操作必须遵守页面审批。
- 助手只能在启动配置页时的工作目录内运行，且不能覆盖确定性证据结果。
- 首次 Codex 回合可能因本地工具冷启动耗时约两分钟；不要将正常冷启动误报为分析失败。

## 宿主 Agent 的推荐执行流程

用户说“帮我分析这些材料”“看看这份复盘报告有没有问题”“结合经营数据和会议纪要给我一份管理层报告”等自然业务请求时，不要要求用户配置全局数据源、手工创建任务或处理 `task_id`。

优先按请求复杂度选择：

1. 常规完整交付：调用 `analyze_business_case(question, paths, filename?)`，由同一次调用自动识别材料、建任务、执行可观察分析、计算全部指标、验证已发现的 `rules.json` 并返回 HTML 资源链接。
2. 需要你自主追问、验证不同假设或迭代分析：先调用 `inspect_sources(paths)`、`create_analysis_task(question, paths)`，在宿主内部保存返回的 `task_id`，随后根据实际结果调用 `analyze_task_metric`、`run_diagnostic_step` 和 `evaluate_task_rules`；必要时调用 `run_analysis_cycle`，最后调用 `generate_html_report`。
3. 用户问“你怎么算出来的”“上次做到哪了”“能继续吗”时，调用 `get_analysis_trace(task_id)`、`list_cycle_artifacts(cycle_id)` 或 `resume_analysis_cycle(cycle_id)`；只能展示公开执行事件、方法、证据引用和限制，不能假装获得模型私有思维链。

可选择的本地诊断方法包括 `compare_periods`、`detect_anomalies`、`detect_change_points`、`segment_rank`、`decompose_change`、`correlate_metrics`、`compare_groups`、`analyze_text`、`semantic_cluster`、`compare_topics_with_metrics`、`test_text_metric_lag` 与 `find_explanatory_segments`。语义聚类需要用户提供已经存在的本地模型；不要擅自下载模型或上传材料。

交付时用业务语言先回答用户的问题，再给出关键数据、文档来源、每条假设的实测方向、反证或不足、建议行动和 HTML 报告链接。没有规则时必须明确说明“未提供可验证规则”；文档匹配、相关性或时间先后都不能直接等同于因果。

## MCP 工具接口

以工具方式接入任意支持 MCP 的 harness（WorkBuddy、DeepSeek harness、Codex 或通用客户端）时，启动 stdio 工具服务器：

```bash
data2doc2data mcp
```

它通过 stdio 传输 MCP，暴露 15 个工具：

- 一站式交付：`analyze_business_case`。
- 材料与任务：`inspect_sources`、`create_analysis_task`、`source_profile`。
- 实证分析：`analyze_task_metric`、`evaluate_task_rules`、`run_diagnostic_step`。
- 可观察与恢复：`run_analysis_cycle`、`resume_analysis_cycle`、`get_analysis_trace`、`list_cycle_artifacts`。
- HTML 交付：`generate_html_report`、`generate_cycle_html_report`。
- 兼容旧流程：`analyze`、`check_rules`。注意 `check_rules` 只校验规则结构；要判断规则是否被真实数据支持，必须使用 `evaluate_task_rules`。

新增任务级工具不修改用户已有的全局 profile。宿主负责业务推理和选用工具，Data2Doc2Data 负责受约束的本地计算、快照、证据、执行记录和最终报告；不要在 MCP 内再启动一个重复的模型 Agent。

## 数据源要求

- CSV、Excel 或文档中的内嵌表格必须包含 `date`、`metric` 和 `value` 列。
- 每个待分析指标至少需要两条带日期的观测值。
- `.md`、`.txt`、HTML 和 DOCX 可作为文字材料；HTML/DOCX 还可同时提供结构化表格。XLSX 无需额外依赖。
- PDF、旧版 XLS 与 PPTX 需要用户显式安装可选转换器：`python -m pip install -e '.[documents]'`；扫描件或图表像素不等于已提取事实，未安装 OCR/视觉适配器时必须说明该限制。
- 使用者希望先理解流程时，使用内置演示，不必连接自己的文件。
- 内置演示目录由固定场景 ID 映射，不接受网页或配置提供任意文件路径。

## 使用边界

- 此本地优先版本不得请求、展示或上传任何凭据。
- 明确区分本地确定性分析和可选助手：助手提示词受其提供方的数据策略约束，网页不得自动把 CSV 或文档内容发送给助手。
- 不得暗示尚未支持的数据源已经连接。
- 问题有歧义时不得猜测指标；要求使用 `--metric`，或使用本地页面中的指定指标。
- 文档相关度过低或指标存在歧义时，视为证据不足。
- 除非有受控方向短语、声明式业务规则或独立数据验证，否则只能将文档匹配视为语境，不能视为因果支持；用户自有规则可以声明其他指标，但仍须由本地引擎逐条实测。
- 仅当使用者询问未来数据源选择时，才读取[数据连接器指南](references/connector-guide.md)。
