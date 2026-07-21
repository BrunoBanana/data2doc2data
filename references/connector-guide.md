# 数据连接器指南

当前 Data2Doc2Data 版本仅处理本地文件。本指南列出可供后续评估的连接方向，帮助使用者自行判断供应商、账户、权限范围和数据处理要求。列出的供应商均未被当前包默认连接。

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
