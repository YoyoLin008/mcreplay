# 发布素材

## 中文短公告

麦当劳 MCP 响应变了，解析器哪里需要改？McReplay（麦回放）把一次查询变成可复现的本地测试：提取响应结构、定位字段和类型变化，再通过标准 MCP 回放到适配器。一个命令生成演示，打开 HTML 报告就能看到变化位置。

仓库：https://github.com/YoyoLin008/mcreplay

## English GitHub description

Structural snapshots, change reports, and local MCP replay for McDonald's China integrations.

## 90 秒演示脚本

1. **0–15 秒：问题。** 展示解析器依赖整数 `timestamp` 的示例，以及字段变成字符串后的失败。
2. **15–35 秒：运行。** 执行 `mcreplay demo --out-dir demo-output`，生成两份合成样本和报告。
3. **35–55 秒：定位。** 打开报告，查看字段移除、类型变化与文本变空的位置。
4. **55–75 秒：回放。** 将 MCP 客户端连接 `mcreplay replay demo-output/before.json`，调用工具，把样本送进适配器。
5. **75–90 秒：接入项目。** 展示 Skill 配置与本地保存流程，说明如何用 `compare` 的退出码接入 CI。

## 功能亮点

- 时间、活动、营养三个工具的结构观察。
- 以占位值保留字段和响应格式，生成可重复使用的测试样本。
- 字段、类型、封装与空结果变化一目了然。
- 终端结果、HTML 报告和 CI 退出码。
- 标准 MCP SDK 回放，直接接入现有客户端和适配器。

## 关键词与主题

`mcp`、`model-context-protocol`、`python`、`developer-tools`、`contract-testing`、`test-fixtures`、`offline`、`mcdonalds`、`skill`。

## 分享方向

麦当劳挑战赛开发者讨论、MCP 客户端与 SDK 社区，以及开发工具实践分享。用一个解析失败的最小示例，展示定位变化和回归测试的完整过程。
