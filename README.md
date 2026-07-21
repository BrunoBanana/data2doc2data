# Data2Doc2Data — Data + Text Loop Reasoning for Real Business Scenarios

**[中文](#中文) | [English](#english)**

---

<a id="english"></a>

Current version: **v2.9.0**. See the [changelog](CHANGELOG.md) for release history from v1.0.0.

Data2Doc2Data is built for real business scenarios. It loops between data metrics and strategy/decision documents: first discover signals from data, then understand business context from text, and finally return to data to verify hypotheses — producing traceable, actionable business insights.

```text
Data Signal → Document Context → Data Verification → Traceable Insight
```

## Capabilities

- Built-in synthetic demo data (Chinese)
- User-supplied local CSV data
- User-supplied local Markdown / text decision documents
- Local web UI for configuration and analysis (Chinese)
- CLI for configuration, analysis, and status check
- Explicit metric specification when a question cannot uniquely identify one

All source data stays on your machine. Nothing is sent to hosted services.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
data2doc2data setup
```

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

The local helper service listens only on `127.0.0.1`, accepts only expected Host and same-origin browser requests, and stores source paths locally only. It contains no credential inputs, telemetry, or network data calls. CSV files are capped at 5 MB, individual documents at 1 MB, and document directories at 200 supported files; oversized files and malformed configs return clear local errors.

## Publishing

This project is licensed under [MIT](LICENSE). Generate a public upload bundle from a clean workspace:

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v2.9.0.zip
```

Upload the ZIP to your target SkillHub. It includes `SKILL.md`, the local helper UI, runtime code, the connector guide, and `LICENSE.md` (MIT). It excludes tests, build caches, hidden files, and symlinks. The builder scans every included text resource and rejects builds containing prohibited private markers. `--draft` is for local experimentation only — never publish.

---

<a id="中文"></a>

当前版本：**v2.9.0**。请查看[更新日志](CHANGELOG.md)了解从 v1.0.0 开始的版本记录。

Data2Doc2Data 面向真实业务场景，将数据指标与策略、决策文档进行循环推理：先从数据发现信号，再从文本理解业务语境，最后回到数据验证假设，输出可追溯、可行动的业务洞察。

```text
数据信号 → 文档决策语境 → 数据验证 → 可追溯业务洞察
```

## 本版本可用能力

- 内置中文合成演示数据
- 使用者自有的本地 CSV 数据
- 使用者自有的本地 Markdown 与文本决策文档
- 中文本地配置与分析页面
- 命令行配置、分析与状态检查
- 当问题不能唯一定位指标时，支持显式指定指标

所有源数据均保留在本机，不会发送至托管服务。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
data2doc2data setup
```

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

本地辅助服务仅监听 `127.0.0.1`，只接受预期 Host 和同源浏览器请求，并仅在本机保存来源路径。它不包含凭据输入框、遥测或网络数据调用。CSV 文件最大 5 MB，单个文档最大 1 MB，文档目录最多 200 个受支持文件；超限文件和格式错误的配置会返回明确的本地错误。

## 发布

本项目采用 [MIT](LICENSE) 许可证。请从干净工作区生成公开上传包：

```bash
python scripts/build_skill_bundle.py dist/data2doc2data-v2.9.0.zip
```

将该 ZIP 上传至目标 SkillHub。它包含 `SKILL.md`、本地辅助界面、运行时代码、数据连接器指南和 `LICENSE.md` 形式的 MIT 许可证；不包含测试、生成缓存、隐藏文件或符号链接。构建器还会扫描每个纳入的文本资源，并在发现禁止的私有标记时拒绝构建。`--draft` 仅用于无许可证的本地实验，绝不能发布。
