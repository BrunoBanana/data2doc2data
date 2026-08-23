# Codex MCP 接入

先确认 `data2doc2data doctor --json` 返回 `"ok": true`。然后把 `config.toml.example` 中的配置合并到 `~/.codex/config.toml`，重启 Codex，并用 `/mcp` 确认 `data2doc2data` 的三个工具已经加载。

也可以用命令添加同一服务：

```bash
codex mcp add data2doc2data -- data2doc2data mcp
```

服务通过 stdio 在本机运行，不需要 API Key，也不会把原始 CSV 行返回给 Codex。
