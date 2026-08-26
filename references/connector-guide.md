# 数据连接器指南

当前 Data2Doc2Data 版本仅处理本地文件。本指南列出可供后续评估的连接方向，帮助使用者自行判断供应商、账户、权限范围和数据处理要求。列出的供应商均未被当前包默认连接。

## 本地智能助手不是数据连接器

Codex 与腾讯 WorkBuddy/CodeBuddy 只用于在网页中解释证据或执行经过授权的本地操作，不会替代 CSV/文档数据源，也不会成为确定性结论的证据权威。

- Codex 必须由使用者另行安装并登录，且 `codex --version` 可用；项目通过公开的 App Server stdio 接口连接。
- 腾讯 WorkBuddy 必须由使用者另行安装并登录，且 `codebuddy --version` 可用；项目通过公开的 ACP over HTTP/SSE 接口连接回环服务。
- 两者都限制在启动配置页的工作目录；只读模式禁止变更，协作模式逐次审批，信任本次会话仅复用范围和有效期都匹配的批准。
- 确定性分析不会自动把 CSV 或文档内容附加给助手。使用者主动发送给助手的提示词与操作受相应提供方的数据策略约束。
- 助手未安装、未登录或版本不兼容时，本地证据分析仍然可用。

## 先从本地文件开始

先使用 CSV/XLSX 导出文件和本地决策文档目录。这是在向实时分析账户授权前，最快验证数据—文本循环是否有业务价值的方式。

## 推荐的后续连接器

### 网站与增长分析

- **Google Analytics Data API**：适合网站与获客报表。请阅读[官方 Data API 概览](https://developers.google.com/analytics/devguides/reporting/data/v1)，并仅通过使用者授权的 OAuth 连接。
- **PostHog API**：适合已在使用 PostHog 的产品与 Web 分析团队。请从[官方 API 文档](https://posthog.com/docs/api)开始评估。

### 产品分析

- **Amplitude**：适合围绕事件、分群和看板开展的产品分析。其[官方 API 目录](https://www.amplitude.com/docs/apis)涵盖看板、导出能力与事件写入。

### 电商分析

- **Shopify GraphQL Admin API**：适合需要订单、商品和客户证据的商家。Shopify 为新的集成推荐使用 [GraphQL Admin API](https://shopify.dev/docs/apps/build/graphql)。

## 连接器要求

未来的连接器应当：

1. 只请求最小化的只读权限。
2. 在分析前清晰展示查询模型和返回字段。
3. 将访问令牌保存在使用者可控制的本地凭据存储中。
4. 在最终证据链中记录准确查询与结果时间戳。
5. 指标无法可靠映射时，返回明确的限制说明。
