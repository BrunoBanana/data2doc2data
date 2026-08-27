# Data2Doc2Data v3.1 发布就绪设计

## 目标

把已经合并到 `main` 的 Agent Flow 通信、恢复与可观测能力交付为可验证的 `v3.1.0`：主分支 CI 全绿；用户可在全新环境从 GitHub 一条命令启动；Codex、WorkBuddy/HY3 与 MCP 至少完成有证据链的真实材料验收；GitHub Release 不包含私人答辩材料。

## 当前事实

- 项目当前版本为 `v3.0.0`，因此下一兼容功能版本必须是 `v3.1.0`，不能倒退到 `v0.1.0`。
- `main` 的 Python 3.10、3.12、3.13 CI 已通过；Python 3.11 在 coverage 模式下有两个完整分析 HTTP 请求超过测试客户端写死的 2 秒超时。
- 本地基线为 536 个 Python 测试、73 个前端测试和 TypeScript typecheck 全部通过。
- GitHub 尚无正式 Release；README 已提供从 GitHub 使用 `uvx` 启动的入口。
- 私人答辩文件位于 `docs/pitch/`，已被公共交付边界排除。

## 设计原则

1. 修复真实门禁，不删除或弱化测试。快速元数据 API 保持短超时，执行完整本地分析的 API 使用独立、明确且有限的集成测试预算。
2. 发布从不可变 tag 验收。先验证候选提交，再创建 `v3.1.0` tag；创建 tag 后再从该 tag 做一次冷安装冒烟。
3. 宿主 Agent 只负责规划和解释，本地工具负责原始数据计算；验收必须检查证据、制品引用和 HTML，而不只检查自然语言答案。
4. 私人与公共产物分离。GitHub Release、wheel/sdist、Skill bundle 和源码不包含 `docs/pitch/` 或真实业务导出。
5. 不为发布继续扩展产品范围。OCR、更多连接器、长期知识库与新模型适配器推迟到发布后的真实反馈阶段。

## 工作流

### 1. CI 稳定化

- 为测试 HTTP helper 增加按请求传入的 timeout。
- 默认快速请求继续使用 2 秒。
- 仅两个执行完整分析的请求使用 15 秒预算；它们仍通过真实 loopback HTTP 服务执行。
- 增加测试断言，确保默认预算没有被整体放宽。
- 更新 GitHub Actions 主版本以消除 Node 20 运行时弃用警告，但不改变 Python 3.10–3.13 矩阵。

### 2. v3.1.0 元数据与发布产物

- 对齐 `pyproject.toml`、运行引擎、MCP server、Codex/WorkBuddy 握手、Skill metadata、README、CHANGELOG 与 bundle builder 中的版本。
- 构建 wheel、sdist 和公开 Skill ZIP。
- 对所有产物做文件清单、哈希、安装和隐私扫描。

### 3. 全新环境验收

- 使用临时目录和独立缓存从候选 Git commit 安装。
- 验证 `ddd doctor --json`、`ddd web --no-open`、HTTP 200、Demo 两套案例和 HTML 报告。
- 发布 tag 后重复最短冒烟，安装源改为 `@v3.1.0`。

### 4. 真实宿主验收

- Codex：从一套未注入预设答案的数据＋文档材料开始，检查自动任务创建、三轮调度、证据追踪、HTML 报告。
- WorkBuddy/HY3：执行等价任务并记录模型/CLI 版本、完成状态、制品引用与报告路径。
- MCP：从宿主视角调用无 task_id 的高层工具，检查自动识别、自动建任务、分析循环和报告生成。
- 若真实宿主凭据不可用，发布阻断并明确报告，不用 mock 代替真实验收。

### 5. GitHub Release 与答辩材料

- 只有 CI、冷安装和真实宿主验收通过后才创建 `v3.1.0` Release。
- Release notes 解释核心差异：可验证、可回退、可观测的 Data + Text Agent Flow。
- 私人答辩 PPT 只更新必要事实：v3.1.0、通信协议、恢复 checkpoint、真实宿主验收和发布安装命令；不把答辩文件加入 Git。

## 失败处理

- CI 单版本超时：保留日志和精确失败端点；不靠全局重试掩盖。
- 冷安装失败：停止发 tag，修复包数据或入口点后重新构建。
- 宿主断线：验证 checkpoint/resume；无法恢复则记录为发布阻断。
- tag 后冒烟失败：不覆盖 tag，删除尚未发布的本地/远端候选 tag，修复后使用新的候选流程。

## 完成标准

- Python 3.10–3.13 CI 全绿且覆盖率不低于 80%。
- 536+ Python 测试、73+ 前端测试、类型检查、生产构建、确定性 E2E 全部通过。
- 从 Git commit 和 `v3.1.0` tag 的全新 `uvx` 安装均能启动工作台。
- Codex、WorkBuddy/HY3、MCP 三个入口均有真实验收证据。
- wheel、sdist、Skill ZIP 和 GitHub Release 通过隐私审计。
- 私人 PPT 更新但不进入 GitHub。
