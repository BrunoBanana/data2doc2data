# 腾讯 CodeBuddy / WorkBuddy MCP 接入

先确认 `data2doc2data doctor --json` 通过。可以复制 `.mcp.json.example` 为项目根目录的 `.mcp.json`，或直接执行：

```bash
codebuddy mcp add --scope project data2doc2data -- data2doc2data mcp
```

项目级 MCP 首次连接需要在 CodeBuddy 中批准。之后用 `/mcp` 查看连接和诊断信息。示例不包含凭据，所有确定性数据计算仍在本机完成。
