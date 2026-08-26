# 腾讯 CodeBuddy / WorkBuddy MCP 接入

项目同时提供腾讯原生插件清单 `.codebuddy-plugin/plugin.json`、自动发现的 `skills/data2doc2data/SKILL.md`，以及直接 MCP 注册这两种接入方式。先确认项目安装在独立虚拟环境，并运行 `.venv/bin/data2doc2data doctor --json`。最简单的用户级安装方式：

```bash
.venv/bin/data2doc2data install-mcp --host codebuddy --scope user
```

安装器使用当前 Python 环境的绝对可执行文件路径，避免系统 PATH 指向缺少依赖的其他环境。加 `--dry-run` 可只查看注册命令；项目级安装可改为 `--scope project`。也可以复制 `.mcp.json.example` 为项目根目录的 `.mcp.json`，或手工运行：

`--host workbuddy` 与 `--host codebuddy` 等价，都会使用腾讯实际提供的 `codebuddy` 可执行程序。

```bash
codebuddy mcp add --scope user data2doc2data -- .venv/bin/data2doc2data mcp
```

首次连接可能需要在 WorkBuddy/CodeBuddy 中批准，之后使用 `/mcp` 检查 15 个已加载工具，必要时刷新会话。推荐让宿主调用 `analyze_business_case` 一次完成材料发现、任务创建、计算、文本分析、规则实证和 HTML 交付；复杂场景则调用 `run_diagnostic_step` 自主选择本地统计、机器学习和交叉验证步骤。所有原始数据保持本地。

原生插件包可以先用腾讯 CLI 校验，再作为本地开发插件加载：

```bash
codebuddy plugin validate .
codebuddy --plugin-dir /你的项目绝对路径/data2doc2data
```

插件启动器会使用项目自己的 `.venv`，不会误用系统 PATH 里的旧版本。不要另外在项目根目录创建同名 `.mcp.json`：它会遮蔽已经批准的用户级 MCP 服务，导致 WorkBuddy 再次显示“需要批准”。

使用 `codebuddy --print` 做自动化验收时，腾讯宿主会通过 `DeferExecuteTool` 间接调用 MCP。可以只对本次进程授权该代理和指定工具，不写入全局设置、也不关闭权限系统：

```bash
codebuddy --print --model hy3 \
  --allowedTools mcp__data2doc2data__analyze_business_case \
  --settings '{"permissions":{"allow":["DeferExecuteTool","mcp__data2doc2data__analyze_business_case"]}}' \
  '请分析我指定的数据和文档，并生成离线 HTML 报告。'
```

图形界面中的普通自然对话无需使用这条自动化命令；首次出现审批时按宿主提示批准即可。
