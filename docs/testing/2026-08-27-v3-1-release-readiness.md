# Data2Doc2Data v3.1.0 发布就绪验证

日期：2026-08-27

## 当前结论

- Python wheel、sdist 与公开 Skill Bundle 均成功构建。
- 两次独立 Skill Bundle 构建得到相同 SHA-256 和相同 121 项文件清单。
- wheel 在全新 Python 3.13.9 虚拟环境中安装成功，`ddd doctor --json` 返回 `ok: true`。
- `v3.1.0` 注释标签已固定到合并提交 `6fa25010c26ed244f092cb91737f09c9850f73e8`，正式 [GitHub Release](https://github.com/BrunoBanana/data2doc2data/releases/tag/v3.1.0) 已发布。
- 从 Release 重新下载的 wheel、sdist 与 Skill Bundle 哈希与最终构建逐字节一致。
- WorkBuddy 2.115.0 / HY3 完成三轮真实 Agent 规划与本地计算；MCP 高层入口在不提供 `task_id` 时完成自动建任务、分析和 HTML 交付。
- Codex 0.148.0-alpha.9 的协议兼容、只读边界、低推理强度和硬超时均已验证；本机真实模型调用因 Code Mode/网络环境在 90 秒内未返回，按环境阻塞记录，不计为通过。
- 私人答辩材料、用户生成文件、会话状态、绝对本机路径、邮箱和常见凭据模式均未进入最终归档。

## 制品清单

| 制品 | 字节数 | 文件数 | SHA-256 |
|---|---:|---:|---|
| `data2doc2data-3.1.0-py3-none-any.whl` | 736,398 | 111 | `87b6052987999fe4caa620679337c7427eab8d08ee83f9313cab809c2bfd04ec` |
| `data2doc2data-3.1.0.tar.gz` | 707,355 | 117 | `d6d9e43daad90d6644d1be7d6e93c799850c7ca804361350a821946a0633825a` |
| `data2doc2data-skill-v3.1.0.zip`（构建 A） | 745,381 | 121 | `0c239d4108e26ab608196bff7c1eff53d495f57d700d046b788ee353864a80f0` |
| `data2doc2data-skill-v3.1.0.zip`（构建 B） | 745,381 | 121 | `0c239d4108e26ab608196bff7c1eff53d495f57d700d046b788ee353864a80f0` |

## 安装后诊断

隔离环境只从构建出的 wheel 安装，不复用仓库虚拟环境。诊断结果：

| 检查 | 结果 |
|---|---|
| 产品状态 | `ok: true` |
| 旗舰案例 | 2 套、468 条记录、9 份文档 |
| MCP | 协议 `2024-11-05`、15 个工具 |
| 内置场景 | 12 条记录、2 个指标、1 份文档，标记为合成数据 |
| 宿主模板 | Codex、CodeBuddy、DeepSeek Harness 共 3 套 |

## 发现并修复的问题

首次 sdist 审计发现 setuptools 默认把 `tests/` 收入源码包，导致“拒绝 URL 内嵌凭据”的虚构测试样例触发敏感内容扫描。根因是源码包缺少显式发布清单边界，而不是扫描器误报。新增 `MANIFEST.in` 与发布契约测试，明确排除测试目录和私人答辩目录；重新构建后 sdist 从 175 个文件收敛为 117 个文件并通过相同扫描。

## 隐私边界

对解压后的 wheel、sdist 和 Skill Bundle 执行路径与内容扫描，最终结果均为通过。扫描范围包括：

- `docs/pitch/`、`analysis_results.json`、`run_analysis.py`；
- `.env`、会话与审计状态文件；
- 本机绝对路径和邮箱地址；
- 私钥头、GitHub token、AWS key 与 Google API key 常见格式。

私人答辩 HTML 未复制到构建目录，后续只在本机更新与验证，不纳入 Git、GitHub Release 或公开 Skill Bundle。

## 真实宿主与 MCP 接受测试

| 入口 | 结果 | 可审计摘要 |
|---|---|---|
| WorkBuddy / CodeBuddy 2.115.0 + HY3 | 通过 | 无预置假设；3 轮自主规划、3 个本地分析产物、173 个事件、30 个证据节点、39 条关系；生成 43,399 字节 HTML，SHA-256 `4d1c80aae0bce789e9fac433de9acbc5009f6774059b686171d64a47dbb0e053` |
| MCP stdio `analyze_business_case` | 通过 | 请求不含 `task_id`；自动识别 260 条记录与 5 份文档，完成 10 个指标发现和 3 条规则实证；生成 60,154 字节 HTML，SHA-256 `384668cfd90eb07dd3815cd9fb930d41444685d65981aed47d2999bbc9b4e981` |
| Codex 0.148.0-alpha.9 | 环境阻塞 | 已兼容 `item/completed` 最终消息、隔离临时线程、低推理强度和 90 秒硬中断；本机 Code Mode 运行时/网络回退未在时限内返回公开决策，不计为真实通过 |

WorkBuddy 与 MCP 结果只记录版本、计数、匿名运行标识和报告哈希；未保存原始业务行、模型私有思考或完整提示词。`install-mcp --host codex/codebuddy --dry-run` 均生成正确的当前环境注册命令，CodeBuddy 插件清单验证通过。

## 本地完整质量门禁

| 门禁 | 结果 |
|---|---|
| Python | 548 项 pytest 通过；543 项 unittest 通过；覆盖率 85%；Ruff 通过 |
| React/Vitest | 22 个文件、73 项测试通过 |
| TypeScript | `tsc --noEmit` 通过 |
| 前端生产构建 | Vite 构建通过；动态图与图表运行时保持按需分块 |
| Playwright | 7 项确定性浏览器流程通过；2 项真实宿主流程按环境门禁跳过，转入单独接受测试 |

Playwright 覆盖三轮数据—文本循环、两套旗舰案例、离线 HTML 报告下载、390px 响应式与减少动态效果、1440px 工作台布局。构建输出存在 ECharts 单块超过 500 kB 的非阻断警告，当前已与主界面异步分离；本次发布不以牺牲图表能力为代价继续拆分。

## 合并、标签与冷安装

- PR [#3](https://github.com/BrunoBanana/data2doc2data/pull/3) 已合并；合并提交为 `6fa25010c26ed244f092cb91737f09c9850f73e8`。
- `v3.1.0` 是指向该合并提交的注释标签；Release 地址为 <https://github.com/BrunoBanana/data2doc2data/releases/tag/v3.1.0>。
- [CI run 33045387773](https://github.com/BrunoBanana/data2doc2data/actions/runs/33045387773) 在 Python 3.10、3.11、3.12、3.13 全部通过。
- 当前网络下，`uvx --from git+https://github.com/BrunoBanana/data2doc2data@v3.1.0 ...` 在 Git fetch 阶段约 8 分钟未完成，按网络传输失败停止，不计为 tag 冷安装通过。
- 使用从 Release 重新下载并复核哈希的 wheel，在全新配置与数据目录中安装；`ddd doctor --json` 返回 `ok: true`。依赖从本机 uv 缓存离线复用，不复用仓库 `.venv`。
- `ddd web --no-open` 在独立端口启动成功：根页面、`/api/agents`、案例、Provider 与任务 API 均返回 HTTP 200。
- Python 3.13 对第三方 `jieba 0.42.1` 报出三个无效转义序列 `SyntaxWarning`；不影响安装、诊断或运行，项目自身无对应警告。
