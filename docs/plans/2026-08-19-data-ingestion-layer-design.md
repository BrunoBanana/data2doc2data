# 数据接入层设计（ingestion layer）

日期：2026-08-19
状态：已实现（核心逻辑 + 服务端端点 + 前端面板，290 测试全绿）

## 背景与目标

确定性引擎只认识 `date,metric,value` 标准指标行。真实业务数据往往是任意格式：
Excel、JSON、嵌套 JSON、或来自某个数据 API。接入层（ingestion）负责把"任意来源"
桥接成标准指标行，让人（或 Agent）在环内确认字段映射，再由确定性引擎完成"证"。

设计原则（与项目定位一致）：
- **Agent 负责"想/理解"**：格式探测、结构预览、字段映射建议可由 Agent 在环内给出。
- **引擎负责"证"**：转换逐行校验、可溯源（`MetricRow.source_row`），LLM 不能改数值。
- **原始数据本地计算**：文件仅在本机解析，API 仅支持 HTTPS 并落到本地快照。

## 数据来源两种

1. **本地文件**（CSV / TSV / JSON / XLSX）：浏览器选文件 → base64 上传到本机服务 →
   探测结构 → 建议映射 → 人确认 → 转换为标准 CSV。
2. **数据 API**：用户给 HTTPS 地址（可选请求头/参数）→ 服务拉取快照到本地 →
   作为本地文件走同样的预览/映射/转换流程。

## 模块职责

- `ingestion.py`（核心，零依赖）：
  - 格式探测 `detect_format`、结构预览 `preview_source`（`SourcePreview`：字段/样例/行数/工作表/Sheet）。
  - 内置映射建议 `suggest_plan`（按中英文列名启发式）、Agent 提案解析
    `build_proposal_prompt` / `parse_plan_response`（兼容 fenced / 裸 JSON，识别 `{"error": ...}`）。
  - 确定性转换 `apply_plan` → `IngestionResult`（逐行校验，记录跳过与告警，行级溯源）。
  - 标准 CSV 写出 `write_standard_csv`。
  - 最小 XLSX 读取器（zip + 共享字符串 + 单元格坐标，无第三方库）。
  - API 快照 `fetch_api_snapshot`（仅 HTTPS，落到带时间戳的本地文件）。
- `server.py`（服务端编排）：`ingest_upload` / `ingest_preview` / `ingest_apply` /
  `ingest_api_snapshot` 四个可单测的编排函数 + 对应 HTTP 端点；`ingest_apply` 回写
  `Profile.data_path` 指向生成的标准 CSV。
- `config.py`：`Profile` 新增 `api` 模式与 `ingestion` / `api` 配置字段。
- 前端 `ingest-panel.js`：两种来源入口 + 字段映射编辑器（预填建议）+ 应用后刷新
  Profile 与数据源画像。安全约束：无 `innerHTML`、无外链、文件仅本机解析。

## 安全契约

- 上传文件名做 sanitize（去路径遍历），落到 `<state>/ingested/uploads/`。
- API 强制 HTTPS，响应大小上限 `MAX_SOURCE_BYTES`，凭据仅留内存（随请求头下发）。
- `ingest_apply` 仅把数据路径指向本地生成的标准 CSV，绝不把原始 CSV 外传。

## 测试

- `tests/test_ingestion.py`：格式探测 / 预览 / 建议 / 转换 / XLSX / Agent 提案 / API 守卫。
- `tests/test_server_ingestion.py`：四个编排函数的单测（含 API 快照 mock）。
- `tests/test_server_ingestion_http.py`：经真实 HTTP 服务跑通 upload→preview→apply 全链路。
- 覆盖率：ingestion 88%、整体 85%（≥80% 门槛）。

## 已知边界

- `ingest_apply` 只更新 `data_path`，`knowledge_path`（文档目录）沿用原 Profile；
  用户仍需在「数据源设置」中确认文档目录，否则分析会因缺文档目录而失败。
- 目前内置 `suggest_plan` 走启发式；Agent 在环提案（把 `build_proposal_prompt` 交给助手）
  的接线尚未接上对话流，可作为后续增强。
