# DeepSeek Harness MCP 接入

先确认 `data2doc2data doctor --json` 通过，并根据 Harness 版本安装匹配版本的 `@deepseek-ai/dsh-mcp-client`。将示例作为 overlay 传入：

```bash
dsh web --patch integrations/deepseek-harness/data2doc2data.cordis.yml.example
```

如需长期启用，把这条插件配置合并到对应 profile 的 `cordis.patch.yml`；不要覆盖已有 patch。工具将以 `mcp__data2doc2data__*` 的名称暴露。
