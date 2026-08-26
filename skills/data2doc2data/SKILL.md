---
name: data2doc2data
description: 对用户提供的经营数据、业务文档或同时包含表格与文字的复盘报告执行本地交叉验证、深度诊断和 HTML 报告交付。
---

# 业务数据与文档交叉分析

当用户说“分析这些材料”“看看这份复盘是否可信”“解释指标变化”“帮我出一份管理层报告”时，主动使用此插件；不要把任务重新变成普通对话或让用户手工处理 `task_id`。

## 自动交付

1. 确认用户已经明确提供文件或目录，以及希望回答的业务问题。
2. 调用 `analyze_business_case(question, paths, filename?)`，自动识别数据、文档或含表格的单份报告，创建隔离任务并完成本地计算。
3. 根据工具实际返回值说明数据范围、文档依据、已支持的判断、存在冲突的判断和证据不足之处。
4. 把返回的离线 HTML 报告资源链接交给用户。

支持 CSV、XLSX、Markdown、TXT、HTML 和 DOCX。HTML、DOCX、Markdown 中可同时提取可访问文字和结构化表格。PDF、旧版 XLS 和 PPTX 需要用户明确安装可选转换器；没有 OCR 或视觉能力时不要假装读懂图表像素。

## 自主深度诊断

当问题需要逐步验证多种解释时：

1. 先调用 `inspect_sources(paths)` 和 `create_analysis_task(question, paths)`，只在宿主内部保存 `task_id`。
2. 根据实际证据调用 `analyze_task_metric`、`run_diagnostic_step`、`evaluate_task_rules` 和 `run_analysis_cycle`。
3. `run_diagnostic_step` 支持异常与变点、分组、归因、相关分析、主题聚类和数据—文本交叉验证。
4. 用 `get_analysis_trace` 查看公开执行事件和产物；中断后用 `resume_analysis_cycle` 恢复。
5. 用 `generate_html_report` 或 `generate_cycle_html_report` 交付报告。

原始数据必须保持在本地；只向宿主返回统计摘要、证据片段、来源名称和产物引用。不得覆盖用户已有全局数据源配置；不得把文档相似度、相关性或时间先后直接表述为因果。`check_rules` 只检查规则格式，实际实证必须调用 `evaluate_task_rules`。
