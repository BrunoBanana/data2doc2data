# Agent Flow 通信与可靠性验证

日期：2026-08-26

## 交付范围

- 单一逻辑 Orchestrator 调度 Planner 与本地工具，不引入自由广播式多 Agent 对话。
- 所有持久化运行事件携带版本化通信信封：message、trace、causation、sender、receiver、attempt、idempotency、deadline。
- 工具结果明确因果指向对应的 `tool.started`；通信流拒绝重复消息和前向因果引用。
- Evidence Graph 采用 revision + compare-and-swap，避免旧结果静默覆盖新状态。
- Connected Planner 使用有限指数退避、总截止时间和私有恢复 checkpoint；公开事件不泄露 provider session ID。
- 工作台 Inspector 与离线 HTML 报告展示真实协议交接、重试、checkpoint 与制品引用，不展示原始数据、提示词或模型隐性思维链。

## 发现并修复的发布阻断问题

1. ReactFlow 晚于首批事件初始化时，旧视口状态会提前消费首次自动聚焦。新增红绿回归测试，改为画布实例就绪后才推进视口状态。
2. React StrictMode 并发启动会建立两个本地会话，Cookie 与 CSRF token 可能错配并触发 `agent request authorization failed`。客户端启动改为 single-flight，同一时刻只建立一次会话。
3. 连续浏览器流程中，多个 HTTP/SSE 线程同时打开和关闭同一个 SQLite WAL 文件，进程采样确认线程阻塞在 SQLite 文件互斥锁。工作区存储现在串行化连接的完整打开—使用—关闭生命周期；可控并发测试断言最多一个活动连接。
4. E2E 服务只有一个本地工作区，跨文件并发会互相污染任务状态。Playwright 固定为单 worker，与产品单工作区语义保持一致。

## 验证矩阵

| 门禁 | 结果 |
|---|---|
| Agent protocol、因果链、兼容旧事件 | 单元测试覆盖新旧事件、重复 message ID、前向 causation 与长标识符 |
| Evidence Graph revision/CAS | revision 递增、冲突拒绝、旧数据库迁移通过 |
| Planner 恢复 | 有限重试、deadline、checkpoint、恢复信息脱敏通过 |
| 前端回放 | 首节点初始化竞态红绿验证；协议交接 Inspector 断言通过 |
| HTML 报告 | 通信与恢复审计、TRACE、证据树、离线 CSP、零外部请求通过 |
| 响应式体验 | 390px、reduced-motion、画布/轨道不重叠、全页横向溢出不超过 1px |
| 连续使用 | 两套旗舰案例连续完成，报告下载可打开，下一任务不会因 SQLite 互斥冻结 |

## 最终命令

```text
uv run pytest
uv run ruff check .
npm test -- --run
npm run typecheck
npm run build
npm run e2e
```

真实 WorkBuddy 与 Codex E2E 需要外部宿主环境变量，因此在默认确定性门禁中显式跳过；对应协议、适配器和恢复路径由 Python 测试覆盖。
