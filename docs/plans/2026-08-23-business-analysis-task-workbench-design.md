# 业务分析任务工作台设计

**日期：** 2026-08-23  
**状态：** 已确认  
**定位：** 以数据、文本和可验证证据为主体，AI 助手为侧边协作者的本地业务分析任务工作台。

## 1. 背景与目标

现有产品已经具备本地数据计算、文档检索、确定性验证、证据快照、Codex/WorkBuddy 连接和操作审批，但信息架构仍以对话为主。数据接入、规则、历史结论和证据过程大多折叠在侧栏，用户容易把产品理解成“带证据的聊天工具”。

本次重构的目标是让用户首先感知并完成一项业务分析任务：连接智能能力、接入数据、查看数据 Dashboard、可选地接入并分析文本材料、获得数据与文本联合 Dashboard，再使用右侧 AI 助手继续调查。分析过程必须通过计算、检索、证据、假设和验证等可观察事件呈现。

## 2. 产品原则

1. **任务优先，聊天从属。** 主画布属于分析任务和分析产物，AI 只占右侧可收起区域。
2. **宿主掌控执行。** Agent 提出计划、查询意图、图表规范和假设；本地宿主负责执行、校验、存储、权限和渲染。
3. **事实与解释分层。** 数据事实、文档主张、假设、验证结果、Agent 建议使用不同类型和视觉状态。
4. **展示可验证过程，不展示隐藏思维链。** 页面展示 SQL、公式、工具调用、检索片段、证据连接和结果，不展示模型私有推理文本。
5. **本地优先。** 原始数据默认留在本机；只把有界统计、必要样例和相关文档片段发送给用户选择的模型提供方。
6. **无模型也可工作。** 用户可跳过模型连接并获得基础数据画像、质量报告和确定性 Dashboard；模型只增强自动规划、图表建议、文本抽取、假设和解释。

## 3. 用户体验路径

### 3.1 首次进入

首次进入显示一个有进度的接入向导，而不是空聊天框：

1. **连接智能能力**
   - 本机 Codex CLI。
   - 腾讯 WorkBuddy/CodeBuddy CLI。
   - 大模型 API（OpenAI-compatible 为首个通用协议，后续增加专用适配器）。
   - 允许“暂时跳过”。
2. **创建分析任务**
   - 输入业务问题、目标和可选时间范围。
   - 也可从任务模板开始，例如异常调查、周期复盘、策略核验。
3. **接入数据**
   - 本地文件、文件夹、HTTPS API、数据库或由 Agent 提出读取方案。
   - 用户在任何外部读取或写操作前审核计划。
4. **数据画像与 Dashboard**
   - 展示结构、字段、质量、时间覆盖、指标候选和推荐图表。
5. **导入文档（可选）**
   - 形成文档画像、主题、实体、时间线、主张和引用。
6. **进入联合分析工作台**
   - 数据 Dashboard、文本 Dashboard、证据链、假设图和右侧 AI 助手共存。

### 3.2 重返产品

重返产品直接进入“任务首页”，展示最近任务、数据健康度、待处理异常、最近结论和失败运行。用户不需要重复接入已经保存且仍有效的本地连接。

## 4. 信息架构

### 4.1 一级页面

1. **任务首页**：最近任务、任务模板、待处理异常、最近结论。
2. **接入中心**：模型/CLI、数据源、文档源和连接健康状态。
3. **分析任务工作台**：一个具体任务的所有数据、文本、证据、假设和结论。
4. **资产中心**：数据集、指标、文档语料、规则和历史快照。
5. **运行历史**：任务运行、失败原因、耗时、模型调用、审批和审计。

### 4.2 分析任务工作台

工作台采用三段布局：

```text
┌──────────────┬────────────────────────────────────┬──────────────┐
│ 任务与资产栏 │              分析主画布            │  AI 助手     │
│ 当前任务     │ 总览 数据 文本 证据 假设 历史      │ 对话         │
│ 数据源       │ KPI / 图表 / 表格 / 图 / 时间线    │ 建议问题     │
│ 文档         │                                    │ 操作与审批   │
│ 运行记录     │ 底部可展开：本轮执行时间线         │              │
└──────────────┴────────────────────────────────────┴──────────────┘
```

右侧助手默认约 340px，可收起；主画布始终是视觉中心。移动端用一级标签切换主画布、执行过程和助手，不强行并排。

## 5. 系统架构

### 5.1 前端

现有零构建原生模块适合轻量页面，但不足以承载可编辑 Dashboard、分支任务、证据图和大量状态动画。新工作台迁移为 React + TypeScript + Vite，构建后的静态资源仍由本地 Python 服务提供，不引入外部 CDN。

核心前端模块：

- `Onboarding`：连接、任务创建、数据和文档接入。
- `TaskShell`：三段布局、任务导航和状态。
- `DashboardCanvas`：KPI、图表、表格和布局管理。
- `TextDashboard`：文档画像、主题、实体、时间线和主张。
- `RunTimeline`：可观察执行事件。
- `EvidenceGraph`：证据链和假设图。
- `AssistantDrawer`：Codex、WorkBuddy 或 API 模型交互与审批。

### 5.2 后端

保留 Python 回环服务和现有确定性分析内核，增加任务编排、Dashboard、文档处理和事件存储层：

- `ProviderRegistry`：CLI 与 API 模型连接。
- `ConnectorRegistry`：文件、API、数据库和 Agent 数据获取计划。
- `LocalQueryEngine`：本地结构探测、SQL/聚合执行和结果约束。
- `DashboardPlanner`：图表目标、查询计划和 DashboardSpec。
- `DocumentPipeline`：解析、切分、索引、实体和主张处理。
- `AnalysisOrchestrator`：驱动计算、检索、假设、验证和结论。
- `RunEventStore`：保存并通过 SSE 重放运行事件。

### 5.3 本地存储

从单一 JSON 状态逐步迁移为本地 SQLite 元数据仓库，原始文件和大产物仍保存在受控目录。核心实体：

- `Workspace`
- `ProviderConnection`
- `DataSource` / `DatasetSnapshot`
- `DocumentCorpus` / `DocumentSnapshot`
- `AnalysisTask` / `AnalysisRun`
- `DashboardSpec` / `Artifact`
- `EvidenceNode` / `EvidenceEdge`
- `Approval` / `AuditEntry`

快照不可变；任务运行引用精确的数据和文档快照，保证重放和比较。

## 6. 数据 Dashboard

### 6.1 生成流程

```text
业务目标
→ Agent 或内置规划器提出分析目标
→ 本地引擎生成并校验查询/计算计划
→ 本地执行并限制结果规模
→ Agent 输出声明式图表规范
→ 图表编译器校验并渲染
→ 保存图表、公式、查询、数据来源和时间范围
```

Agent 不生成任意网页代码，也不直接拥有数据执行权限。每张图表必须包含：标题、业务问题、查询或公式、使用字段、数据快照、结果行数、生成者和验证状态。

### 6.2 图表技术

直接采用 MIT 许可的 Microsoft Flint 作为 Agent 与渲染器之间的图表中间语言。Flint 可编译为 Vega-Lite、ECharts、Chart.js 或 Plotly；首版选择一种浏览器渲染后端，避免同时维护多套交互语义。

Data Formulator 作为交互和 Data Thread 参考，不直接嵌入或 Fork。LIDA 不作为生产核心，因为其默认模式包含模型生成和执行代码；只借鉴目标生成、图表解释和评估思想。

### 6.3 基础 Dashboard

无模型模式至少产生：

- 数据规模、字段和时间覆盖 KPI。
- 缺失、重复、类型异常和新鲜度质量卡。
- 时间序列候选图。
- 数值分布和类别 Top-N。
- 数据表预览和字段画像。

模型增强模式增加业务指标识别、图表组合、标题解释、异常标注和推荐追问。

## 7. 文本处理与文本 Dashboard

### 7.1 处理层级

1. **解析**：文件类型、标题、章节、段落、表格、页码和编码。
2. **规范化**：去除重复、保留原文位置、语言识别和元数据清洗。
3. **索引**：现有 BM25/中文 n-gram 为基础，可选本地或远端嵌入索引。
4. **内容抽取**：实体、日期、指标引用、规则、目标和可验证主张。
5. **证据化**：每个抽取结果保存原文、文件、章节/页码、哈希和抽取方法。

首版保证 Markdown/TXT 和现有支持格式；PDF、DOCX、OCR 通过解析适配器逐步加入，不在首个前端重构里一次性实现。

### 7.2 文本 Dashboard

- 文档数量、格式、来源和时间覆盖。
- 主题分布和文档时间线。
- 高频实体、指标和规则。
- 文档主张列表及原文引用。
- 主张之间的一致、冲突和版本变化。
- 已有数据支持、与数据矛盾、待验证和无法验证的主张数量。

Agent 抽取的主张默认标记为“待验证”，不能直接成为确定性结论。

## 8. 可观察分析过程

### 8.1 运行事件

后端发出稳定的结构化事件，而不是让前端解析模型文本：

- `run.started` / `run.completed` / `run.failed`
- `step.started` / `step.completed` / `step.failed`
- `data.profiled`
- `compute.plan.created` / `compute.result.created`
- `chart.spec.created` / `chart.rendered`
- `document.indexed`
- `retrieval.result.created`
- `claim.extracted`
- `hypothesis.created`
- `validation.completed`
- `evidence.linked`
- `conclusion.created`
- `approval.requested` / `approval.decided`

每个事件拥有 run id、序号、时间、阶段、输入/输出产物引用和安全摘要。SSE 断线后按序号续传。

### 8.2 证据与假设图

图节点类型：

```text
数据源 → 计算计划 → 指标 → 数据信号
文档源 → 文档片段 → 文档主张
数据信号 + 文档主张 → 假设 → 验证 → 结论 → 行动
```

边必须说明关系，例如 `derived_from`、`supports`、`contradicts`、`tests`、`insufficient_for`。使用 React Flow/xyflow 实现可缩放、筛选和展开的图形 UI；布局状态属于用户界面，证据关系由后端契约决定。

Agent/工具追踪的数据结构参考 OpenInference/OpenTelemetry，但首版不嵌入 Phoenix 或 Langfuse 完整 UI。这样可以保持产品一致性，并为以后接入外部可观测平台留出兼容层。

## 9. 动画与交互反馈

动画服务于状态变化，不装饰隐藏推理：

- 节点进入时渐显，当前步骤轻微脉冲。
- 事件完成时沿证据边绘制一次流动效果。
- 假设在 `supported`、`contradicted`、`insufficient` 间切换颜色和图标。
- Dashboard 从骨架屏逐卡填充，避免整页突然出现。
- 计数器和进度只对真实事件变化动画。
- 失败节点停止动画并显示可恢复操作。

全部动画支持 `prefers-reduced-motion`；单次过渡通常控制在 150–450ms，持续运行的动画必须可暂停且不影响读取。

## 10. 安全与权限

- API Key 不写入项目配置、提示词或审计日志；优先使用系统钥匙串或环境变量引用。
- 外部数据连接默认只读；写操作必须显式审批。
- Agent 获取的是 schema、统计、受控样例和有界查询结果，不是默认全量原始表。
- 图表采用声明式规范和宿主执行，不运行 Agent 任意 JavaScript/Python。
- 本地查询引擎限制可访问路径、外部网络、结果大小、执行时间和内存。
- 文档引用和数据证据均保留内容哈希与快照 id。
- 现有 Cookie/CSRF、回环 Host、工作区 containment、审批和审计边界继续保留。

## 11. 错误处理

- 模型不可用：退回确定性 Dashboard，保留“稍后增强”入口。
- 数据接入失败：停留在当前步骤，显示失败字段、格式或连接阶段，不丢失已填配置。
- 查询或图表失败：保留计划、错误和可编辑规范；不展示空白卡片。
- 单个文档失败：语料任务部分成功，列出失败文档并允许单独重试。
- SSE 断线：按事件序号续传；无法恢复时从本地运行存储重建 UI。
- 假设证据不足：显示“证据不足”和所需数据，不允许 Agent 将其包装成确定结论。

## 12. 开源能力采用决策

| 项目 | 决策 | 用途 |
|---|---|---|
| Microsoft Data Formulator | 借鉴，不嵌入/Fork | 接入流程、Data Thread、分支分析和报告 UX |
| Microsoft Flint | 直接依赖 | Agent 友好的声明式图表规范与编译 |
| WrenAI | 后期可选适配 | 数据库连接、语义层和 governed text-to-SQL 参考 |
| LIDA | 不作核心依赖 | 借鉴图表目标、解释和评估 |
| React Flow / xyflow | 直接依赖 | 证据链、假设图和执行图 |
| OpenInference | 兼容其语义 | 模型、检索和工具运行事件 |
| Phoenix / Langfuse | 不嵌入 UI | 调试与可观测设计参考，可作为外部导出目标 |

任何新依赖在落地前必须锁定版本、核对许可证、检查公开包边界和离线运行策略。

## 13. 测试策略

1. **契约测试**：任务、DashboardSpec、运行事件、证据节点和边的 schema。
2. **确定性单元测试**：数据画像、质量、查询限制、图表输入和文档引用。
3. **安全测试**：任意代码阻断、路径 containment、Key 脱敏、只读连接和审批。
4. **前端组件测试**：向导、任务状态、Dashboard 卡片、事件时间线和图状态。
5. **端到端测试**：连接 → 数据 → Dashboard → 文档 → 联合分析 → 助手。
6. **可访问性测试**：键盘、屏幕阅读器、颜色对比和 reduced motion。
7. **性能测试**：大文件本地查询、长运行事件、100+ 图节点和 Dashboard 渲染。
8. **真实提供方测试**：Codex 与 WorkBuddy 至少各完成一轮只读分析和一轮审批流程。

## 14. 分阶段交付

### 阶段 A：新壳层与接入向导

React/TypeScript 构建基础、任务首页、模型/CLI 连接、任务创建和现有能力桥接。

### 阶段 B：数据资产与自动 Dashboard

数据画像、质量卡、查询计划、Flint 图表、DashboardSpec 和本地任务存储。

### 阶段 C：文档语料与文本 Dashboard

文档接入、预处理、主张抽取、引用和文本分析视图。

### 阶段 D：运行时间线、证据链与假设图

统一运行事件、SSE 重放、React Flow 图、假设状态和数据/文本联合验证。

### 阶段 E：右侧助手与产品化收口

助手抽屉、上下文选择、审批、报告导出、动画、响应式、可访问性和三轮真实使用测试。

## 15. 成功标准

- 首次使用者不经过聊天即可完成数据接入并看到基础 Dashboard。
- 工作台首屏主视觉是分析产物，不是消息流。
- 每张图表能回到数据快照、查询/公式和字段。
- 每条文本主张能回到文档位置和原文。
- 每个结论能沿证据图回溯到数据或文档；证据不足必须明确显示。
- 用户能观察计算、检索、抽取、假设和验证状态，但不会看到隐藏思维链。
- Codex、WorkBuddy 和 API 模型使用同一任务与证据契约。
- 原始数据和凭据继续遵守本地优先、安全审批和最小披露边界。

## 参考项目

- Data Formulator: https://github.com/microsoft/data-formulator
- Flint: https://github.com/microsoft/flint-chart
- WrenAI: https://github.com/Canner/WrenAI
- LIDA: https://github.com/microsoft/lida
- React Flow / xyflow: https://github.com/xyflow/xyflow
- OpenInference: https://github.com/Arize-ai/openinference
- Phoenix: https://github.com/Arize-ai/phoenix
- Langfuse: https://github.com/langfuse/langfuse
## Observable playback and report delivery extension

The dynamic surface is an audit-player, not a visualization of private model reasoning. It replays only persisted host events—profiling, calculations, document indexing, claim extraction, validations, and evidence links—and synchronizes the active event with the evidence graph. Motion is used for finite layout and state transitions, with explicit playback controls and a reduced-motion path.

Reports are generated by the trusted Python host from locked dashboard, text, run, and evidence artifacts. The result is one standalone HTML file with an answer-first Executive Summary, visual findings, recommended next steps, further questions, caveats, and expandable provenance. Styles and SVG are inline, external network requests and executable agent markup are absent, and local source paths/raw records are never included.
