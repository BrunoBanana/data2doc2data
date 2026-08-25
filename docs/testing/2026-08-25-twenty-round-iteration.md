# 2026-08-25 二十轮产品与工程迭代审计

本记录只计入形成了明确发现、代码或测试变化并完成验证的轮次。纯讨论、重复运行测试和无结论的视觉浏览不计数。

| 轮次 | 发现 | 修改 | 验证 |
|---:|---|---|---|
| 1 | Demo 默认取首个指标，不一定对应最重要的业务变化 | 按前后窗口归一化变化强度选择主指标 | `test_demo_prioritizes_the_strongest_metric_change_and_text_evidence` |
| 2 | 有文档时第三轮仍可能只做无意义的 `segment=all` | 第三轮接入真实 TF-IDF/NMF/KMeans 文本分析和词云产物 | Cycle runner、文本 ML 与 E2E 断言通过 |
| 3 | Playwright 使用系统 Python，导致本地 ML 依赖与真实运行环境不一致 | E2E Web Server 统一通过项目 `uv` 环境启动 | 7 条确定性 E2E 通过 |
| 4 | 空 `knowledge_path` 被当成当前目录，制造幽灵文档 | 空路径明确表示 0 份可选文档 | `doctor --json` 在真实默认配置通过 |
| 5 | 重新打开任务只恢复未完成运行，最近结果会消失 | 自动恢复最新运行；仅对运行中记录重连 SSE | `App.test.tsx` 恢复最近完成运行用例通过 |
| 6 | 方法名只显示内部代码，业务用户难以理解 | 增加稳健异常检测、结构变化点等中文名称，同时保留审计代码 | `DiagnosticBlocks.test.tsx` 通过 |
| 7 | 关键数值埋在 artifact JSON 中 | 增加有界标量结果网格和统一数字/百分比格式 | 标量 findings 用例通过 |
| 8 | 文本产物“样本数”错误使用主题数 | `TextMLResult` 持久化实际文档数，Dashboard 使用文档数 | Dashboard/TextML/Semantic tests 通过 |
| 9 | `unavailable` 统一写成“证据不足”，且无原因 | 区分完成、不可用、不足、失败，并给出解释与安全重试提示 | 不可用诊断 UI 用例通过 |
| 10 | 工作台下载报告只含基础画像，丢失三轮深度诊断 | 报告加入方法、样本、标量/明细、词云、限制和产物引用 | Reporting 与 Workbench API tests 通过 |
| 11 | Flow 每新增一个节点都 `fitView`，画布不断跳动 | 仅首节点出现和终态收敛时自动适应画布 | `shouldAutoFitFlow` 策略测试通过 |
| 12 | 轮次和产物节点使用内部方法名，难以快速扫描 | 轮次显示“第 N 轮 + 公开理由”，产物显示中文方法名 | Flow projection tests 通过 |
| 13 | 用户只能看到事件数，看不到三轮分析进展 | Flow 状态增加已完成轮次、最大轮次和产物数 | `analysisCycleProgress` 测试通过 |
| 14 | Connected 模式只在运行前请求一次 Agent 计划，并非真正多轮调度 | 每轮在真实产物生成后再次请求 Codex/WorkBuddy 选择下一工具，最多三轮 | Connected cycle/API tests 断言 3 次 planner 调用与 artifact dashboard |
| 15 | Planner 短暂断线会直接终止整次分析 | 同一 provider session ID 最多重连 3 次，留下 waiting/resumed 事件 | transient reconnect 测试通过 |
| 16 | 界面无法区分 Agent 规划和 Demo 规则规划 | Connected 轮次节点明确显示“Agent 规划” | Flow projection connected-agent 用例通过 |
| 17 | 首次进入时仍像二选一聊天入口，没有解释产品内核 | 首屏增加“锁定输入→本地计算→证据链→安全回退→HTML 交付”能力合同 | Onboarding contract test 通过 |
| 18 | 非完成状态颜色相同；贡献表缺少语义化 caption | 增加不可用/失败状态色和表格 caption | Diagnostic 单元测试与类型检查通过 |
| 19 | 运行历史残留旧暗色卡片，回退语义不够显性 | 统一 Paper Desk 视觉，展示回放不改历史/重试新建运行/原记录保留 | RunHistory test 与 390px 浏览器检查通过 |
| 20 | 390px 下六个分析标签被挤成两行 | 标签最小宽度、禁止换行并允许有界横向滚动 | E2E 断言标签无文本溢出且整页横向溢出 ≤ 1px |

## 最终回归追加修复

完整 E2E 首次使用 4 个 worker 并发运行时，暴露了 SQLite 每次连接重复执行 `PRAGMA journal_mode=WAL` 的锁竞争。该问题不计入上述二十轮，但已作为发布阻断修复：数据库初始化现在在单个 `WorkspaceStore` 内只执行一次，其他连接先设置 busy timeout 并复用完成的 schema/WAL 初始化；新增 48 次、12 worker 并发连接回归测试。修复后完整 E2E 为 9 passed、2 个显式 live 测试按环境跳过，未再出现数据库锁。

## 结论

二十轮之后，产品内核从“确定性 Demo + 一次性 Agent 计划”提升为同一宿主协议下的双规划器：Demo 使用可重复规则，Connected 使用真正基于上一轮产物的 Agent 决策；两者都由宿主执行本地计算、保存不可变产物、构建证据图并交付离线 HTML。界面同时补齐了恢复、解释边界、轮次进度和移动端可读性。

仍然刻意保留的边界：系统不展示模型私有思维链；文本—指标时间关联工具只有在输入包含可对齐周期信号时才应启用；候选知识不会自动升级为已验证事实。

最终证据：477 个 Python tests + 54 subtests，覆盖率 85%；22 个前端文件共 68 tests；Ruff、TypeScript、生产构建通过；11 条 E2E 中 9 passed、2 个 live-provider 用例按环境跳过；`doctor --json` 报告 2 套案例、468 条记录、9 份文档、7 个 MCP 工具和 3 个 host 模板全部健康。
