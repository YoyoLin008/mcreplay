# 发布素材（草稿，未向个人账号发布）

## 中文短公告

做麦当劳 MCP 解析器时，一次能跑通的对话不容易变成安全的回归测试。我做了 MaiReplay（麦回放）：在正常客户端明确查询后，本地删除响应真实值，比较字段、类型和封装变化，再用标准 MCP 离线回放。演示无需 Token，样本全部标注为合成；目前尚未完成官方认证实测，回放只验证结构。

仓库：https://github.com/YoyoLin008/maireplay

## English GitHub description

Local structural fixtures, drift reports, and offline MCP replay for McDonald's China integrations. No tokens in CI; synthetic values, explicit provenance.

## 90 秒演示脚本

1. **0–15 秒：问题。** 展示适配器依赖整数 `timestamp` 字段的合成例子；说明类型变化可能让解析器失效。不要称它是官方真实字段。
2. **15–35 秒：运行。** 执行 `maireplay demo --out-dir demo-output`；指出不需要 Token，也不访问官方服务。
3. **35–55 秒：定位。** 打开报告，展示活动字段移除、时间字段类型变化、非空文本变空及人工复核项；说明观察差异不等于完整契约证明。
4. **55–75 秒：回放。** 将标准 MCP 客户端连接 `maireplay replay demo-output/before.json`，列出并调用已记录工具；展示合成占位值。
5. **75–90 秒：真实使用边界。** 展示 Skill 的正常客户端查询→本地接收流程与凭证隔离；明确官方认证尚未实测，不演示虚构 live 成功。

## 可核实的技术差异

- 不遍历业务工具；固定三种只读工具，不持有会员凭证。
- 原始响应值在本地删除，区分 `synthetic` 与 `user-import`。
- 把封装变化、空结果、未知文本保留为显式状态。
- 终端和本地 HTML 报告配合 CI 退出码；标准 MCP SDK 回放。
- 与通用 CLI、诊断器的区别是可重复的结构样本与差异分析，不宣称在线监控或完整业务验证。

## 关键词与主题

`mcp`、`model-context-protocol`、`python`、`developer-tools`、`contract-testing`、`test-fixtures`、`privacy`、`offline`、`mcdonalds`、`skill`。

## 可考虑的社区

麦当劳挑战赛开发者讨论、MCP 客户端或 SDK 社区、V2EX 的项目分享、掘金或少数派的开发工具实践。先核对各社区规则，使用一个合成问题复现说明价值，不跨版刷屏，不自动发帖，不购买或互换 Stars。对个人账号发布、评论或群发需另外获得授权。
