# Data2Doc2Data v3.1.0 发布就绪验证

日期：2026-08-27

## 当前结论

- Python wheel、sdist 与公开 Skill Bundle 均成功构建。
- 两次独立 Skill Bundle 构建得到相同 SHA-256 和相同 121 项文件清单。
- wheel 在全新 Python 3.13.9 虚拟环境中安装成功，`ddd doctor --json` 返回 `ok: true`。
- 私人答辩材料、用户生成文件、会话状态、绝对本机路径、邮箱和常见凭据模式均未进入最终归档。

## 制品清单

| 制品 | 字节数 | 文件数 | SHA-256 |
|---|---:|---:|---|
| `data2doc2data-3.1.0-py3-none-any.whl` | 734,280 | 111 | `7bb7b2bd9eedd4e88a05d5eb54eea37fb113f4e377551a2b328eacd15f3d09d9` |
| `data2doc2data-3.1.0.tar.gz` | 706,558 | 117 | `a9f42ca10459ed8b2c3416d46b15422f8babcea1133ce1d14a0db1104b2b8f9c` |
| `data2doc2data-v3.1.0.zip`（构建 A） | 743,267 | 121 | `4723bf94a68ba3883292f98d647dfb1f500c89f749bfbe12f631396d685a0adf` |
| `data2doc2data-v3.1.0.zip`（构建 B） | 743,267 | 121 | `4723bf94a68ba3883292f98d647dfb1f500c89f749bfbe12f631396d685a0adf` |

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

## 后续门禁

- 候选提交的 GitHub Actions Python 3.10–3.13 矩阵；
- Codex、WorkBuddy/HY3 与宿主级 MCP 真实接受测试；
- 私人 5 分钟答辩 HTML 的事实更新与 1440×900 视觉检查。

## 本地完整质量门禁

| 门禁 | 结果 |
|---|---|
| Python | 539 项通过；Ruff 通过 |
| React/Vitest | 22 个文件、73 项测试通过 |
| TypeScript | `tsc --noEmit` 通过 |
| 前端生产构建 | Vite 构建通过；动态图与图表运行时保持按需分块 |
| Playwright | 7 项确定性浏览器流程通过；2 项真实宿主流程按环境门禁跳过，转入单独接受测试 |

Playwright 覆盖三轮数据—文本循环、两套旗舰案例、离线 HTML 报告下载、390px 响应式与减少动态效果、1440px 工作台布局。构建输出存在 ECharts 单块超过 500 kB 的非阻断警告，当前已与主界面异步分离；本次发布不以牺牲图表能力为代价继续拆分。

## Git 冷安装

- 候选运行时提交：`5e7183d7ec21a2355fdd9e0108ba89b6c7c5c655`。
- PR：[BrunoBanana/data2doc2data#3](https://github.com/BrunoBanana/data2doc2data/pull/3)。
- 使用全新的 uv 缓存和配置目录，从 `git+https://github.com/BrunoBanana/data2doc2data@<candidate-sha>` 安装，不复用仓库 `.venv`。
- `ddd doctor --json` 返回 `ok: true`，案例、MCP、合成场景和宿主模板计数与 wheel 验证一致。
- `ddd web --no-open` 在独立端口启动成功，首次轮询后返回 HTTP 200，页面标题为 `Data2Doc2Data · 业务分析工作台`。
- 冷安装期间 Python 3.13 对第三方 `jieba 0.42.1` 报出三个无效转义序列 `SyntaxWarning`；不影响安装、诊断或运行，项目自身无对应警告。
