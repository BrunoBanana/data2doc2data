# Agent Flow 数据 × 文本交叉推理工作台重构设计

**日期：** 2026-08-24  
**状态：** 已确认  
**视觉目标：** `docs/design-references/2026-08-23/selected-evidence-blueprint.png`  
**范围：** 双运行模式、统一 Agent Flow、动态推理画布、持久 CLI 会话、知识演化、HTML 报告与 MCP 工具。

## 1. 产品定位

Data2Doc2Data 是本地优先的“数据 + 文本交叉推理引擎”。Web 工作台负责呈现、干预和审计；Codex、DeepSeek Harness、WorkBuddy / CodeBuddy 等宿主通过 MCP 调用同一内核。

产品提供两个明确入口：

1. **Demo 模式：** 无需 API 或本地模型。确定性 Demo Runner 使用真实本地工具按预置计划逐步执行，产出完整事件流、证据图和 HTML 报告。它不能伪装为模型推理，也不能只是播放预制卡片。
2. **真实分析模式：** 用户连接 OpenAI-compatible API、Codex 或 WorkBuddy 后，选择内置体验材料或导入自己的材料。Agent Planner 理解目标、规划步骤、调用工具、处理冲突并修订假设。

两套完整合成材料继续作为“未锁答案”的体验数据，可由真实 Agent 自由分析；Demo 模式可以基于同一材料运行稳定、可重复的内置流程。

## 2. 总体架构

```text
Demo Runner ───────┐
                   ├─> AgentFlowEngine ─> Typed Event Store ─> Live Canvas
Connected Runner ──┘          │                   │
                              ├─> Local Tools     ├─> Replay / Resume
                              ├─> Evidence Graph  ├─> HTML Report
                              └─> Knowledge Store └─> MCP Artifacts
```

### 2.1 双 Runner

- `DemoFlowRunner` 读取版本化 flow manifest，逐步调用真实本地工具并实时发出事件。
- `ConnectedAgentRunner` 将受约束工具目录暴露给 API / Codex / WorkBuddy。Agent 只负责规划、选择工具和解释，不直接执行任意分析代码。
- 两个 Runner 产生相同的 `FlowEvent`，因此工作台、事件重放、报告和测试不需要区分宿主。

### 2.2 AgentFlowEngine

每次运行拥有稳定的 `flow_id`、`run_id`、`cursor` 和检查点。流程允许顺序、分支、合并和受限回路，但限制最大步骤、最大修订次数、最大工具输出和运行时间。

核心节点类型：

- 输入识别：文件类型、数据/文本/混合模态、表格和段落清单。
- 数据准备：结构校验、质量分析、类型与时间识别、指标画像。
- 文本准备：章节切分、实体、时间、主张、口径和限制提取。
- 交叉推理：实体/指标/时间对齐、假设生成、数据查询、支持/冲突判定。
- 证据合并：来源、计算、文本引用、假设和结论组成证据图。
- 交付：Dashboard、知识候选、HTML 报告和 MCP artifact。

## 3. 本地工具层

Agent 不接收完整原始数据，而是调用本地受控工具：

- `inspect_sources`：识别文件、模态、大小、表格和章节。
- `extract_document`：将 PDF、DOCX、XLSX、HTML、Markdown、TXT 转为带页码/行号的结构化内容。
- `profile_data`：本地完成 schema、质量、分布和时间范围分析。
- `query_data`：执行受限只读聚合、分组、趋势、窗口和相关性计算。
- `extract_claims`：抽取带原文引用的主张、指标口径、时间和实体。
- `align_evidence`：对齐数据指标、文档实体与时间窗口。
- `test_hypothesis`：生成并执行可审计验证计划。
- `build_evidence_graph`：生成可追溯图结构。
- `generate_html_report`：生成离线、打印安全的单文件 HTML。

基础格式优先使用轻量、无模型解析；复杂 PDF/OCR 通过可选 Docling 适配器提供，避免让重型模型成为核心安装的强依赖。

## 4. Flow 事件协议

事件以追加写入方式保存，并带单调递增 cursor：

- 生命周期：`run.started`、`run.completed`、`run.failed`、`run.paused`。
- 计划：`plan.created`、`plan.revised`、`step.added`、`step.started`、`step.completed`。
- 工具：`tool.started`、`tool.progress`、`tool.result`、`tool.failed`。
- 图变化：`node.added`、`node.updated`、`edge.added`、`edge.activated`。
- 证据：`claim.extracted`、`hypothesis.created`、`hypothesis.tested`、`conflict.detected`。
- 知识：`knowledge.candidate`、`knowledge.verified`、`knowledge.superseded`。
- 交付：`dashboard.updated`、`report.generated`。

事件只记录可审计执行事实、工具输入摘要、输出摘要、来源和状态，不记录或伪造模型私有思维链。

## 5. 动态工作台

### 5.1 视口规则

- 顶部状态栏固定。
- 左侧资产栏占满剩余视口并独立滚动。
- 中央区域是主要工作空间；Dashboard 和文档视图内部滚动，Flow 画布本身不随页面向下漂移。
- 右侧 Agent Console 固定在视口内。标题、连接状态和输入框固定；消息、工具事件和审批队列在中间区域滚动。
- 移动端使用“资产 / Flow / Agent”切换，Agent 作为全高面板或底部面板，不把输入框放到长页面末尾。

### 5.2 活画布

- 新运行从空白网格开始，而不是先绘制完成图再逐条高亮。
- `step.added` 创建节点；`edge.added` 生长连线；`tool.progress` 在边上展示流动信号；`tool.result` 更新节点内容和状态。
- 发生冲突时生成红色冲突节点与回边；计划修订时新增分支，不覆盖历史路径。
- 节点详情展示：用途、输入摘要、工具名、输出摘要、耗时、引用和错误；不展示原始大表。
- 布局根据当前可见节点动态重排，同时保持已稳定区域尽量少移动。
- `prefers-reduced-motion` 下直接切换状态，但保留完整节点和边变化。

视觉实现严格以已选 Evidence Blueprint 为层级基线：中央画布优先，顶部 KPI 次之，底部步骤导航仅作定位，不再成为主要动态表达。

## 6. 报告能力

报告生成成为核心服务，而非网页专属按钮：

- Web 使用认证下载端点，下载测试必须观察到真实文件并成功打开。
- CLI 增加 `data2doc2data report`。
- MCP 增加 `generate_html_report`，返回 artifact ID、本地安全路径、文件名、SHA-256 和 MIME 类型。
- Codex、DeepSeek Harness、WorkBuddy 与 Web 共用同一个报告构建器。
- 报告包含问题、执行计划、数据发现、文本主张、交叉验证、冲突、证据引用、知识更新和限制。

## 7. 持久连接与恢复

- 浏览器拥有稳定 owner 身份；CSRF 可以轮换，但不能因为租约过期改变任务与 Agent 会话归属。
- 活跃页面定期续约，服务端采用滑动过期并持久化可恢复的 provider session ID。
- SSE 使用事件 cursor、`Last-Event-ID` 语义、去重和缓冲重放。
- 客户端采用带抖动的指数退避重连，并显示“重连中 / 已恢复 / 需要重新认证”真实状态。
- WorkBuddy 适配器由连接监督器管理健康检查、SSE 重建和 session resume；不能保留“连接 ID 存在但线程已死”的状态。
- 页面刷新、短暂休眠或 CLI 服务重启后，优先重新附着到原运行。

## 8. 受控知识演化

本功能不称为 Recursive Self-Improvement。模型、代码和推理引擎不会自动改写自己；改进发生在项目知识层。

- 知识默认按项目隔离，不跨项目自动传播。
- 每次运行可产生 `candidate` 事实、口径、实体映射、规则和冲突关系。
- 候选知识必须带来源、生成运行、有效时间和置信依据。
- 只有确定性证据满足规则或用户批准后才能成为 `verified`。
- 新证据可以将旧知识标记为 `superseded` 或 `rejected`，但不能抹去历史。
- 后续 Agent 可以检索已验证知识和当前冲突；未验证候选不能作为确定事实注入上下文。

## 9. 错误与安全边界

- 输入解析失败必须保留部分成功结果和逐文件诊断。
- Agent 计划必须经过 schema、工具白名单、预算和权限校验。
- 数据查询只读、受限、可取消，并记录查询摘要与结果哈希。
- Agent 断线不终止已提交的本地工具任务；运行可暂停、重连和继续。
- 报告与 Dashboard 不得包含本地绝对路径、密钥、未转义模型内容或无界原始数据。

## 10. 验收标准

1. 无模型 Demo 从空白画布开始，完整执行至少 10 类节点、一次分支或冲突，并生成可下载报告。
2. 真实 Agent 可以从单个混合文档或数据 + 文档组合构建并执行流程。
3. 右栏输入框在桌面和移动端始终可见，只有消息区域滚动。
4. HTML 下载产生真实文件；CLI 与 MCP 可生成同一报告。
5. 模拟断线、页面刷新和浏览器租约续期后，运行从 cursor 恢复且不重复事件。
6. Flow 画布展示节点创建、边激活、工具进度、冲突分支和汇聚，而非卡片回放。
7. 知识候选有项目隔离、来源、版本和验证状态。
8. 两套体验材料可在真实 Agent 模式自由使用；Demo 模式无需连接任何 Agent。

