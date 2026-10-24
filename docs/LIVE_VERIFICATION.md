# 官方 MCP 实测记录

2026-10-24 使用已激活的麦当劳 MCP Token，通过 MCP Inspector 2.12.0 连接 `https://mcp.mcd.cn`，执行三次空参数查询。三项均返回 `isError=false`、业务 `success=true` 和 `code=200`。

## 连接与查询

- 传输：Streamable HTTP；认证：Bearer Token。
- 服务：`mcd-mcp` 1.0.0；协商协议：`2025-06-18`。
- 本地环境：macOS 15.2、Python 3.13.3、MCP Python SDK 1.30.0。

| 工具 | 查询开始时间（UTC） | 耗时 | 实际响应 |
|---|---|---:|---|
| `now-time-info` | 2026-10-24 18:38:25 | 1,274 ms | Markdown 后缀 JSON + `structuredContent`；`data.timestamp` 为整数 |
| `campaign-calendar` | 2026-10-24 18:38:49 | 1,776 ms | 活动 Markdown + `structuredContent`；含 `currentTime`、`dailyList`、`subscribedEvents` |
| `list-nutrition-foods` | 2026-10-24 18:41:50 | 1,670 ms | Markdown 后缀 JSON + `structuredContent`；`data` 为营养表格文本 |

三次参数均为 `{}`。工具发现结果中，活动日历还提供可选字符串参数 `specifiedDate`。

## McReplay 端到端验证

从 Inspector 导出完整协议结果，保留每次 `CallToolResult` 的 `content`、`structuredContent` 和 `isError`，完成以下检查：

| 检查 | 结果 |
|---|---|
| 三项完整响应导入结构包 | 通过 |
| 将三项原始结果分别传给本地 `record_mcd_observation` | 通过；输出文件权限均为 `0600` |
| 对比接收结果与直接导入结果 | 三项观察完全一致 |
| 标准 SDK 初始化、发现与回放三项工具 | 通过；返回值与结构包逐项一致 |
| 原样比较 | 时间与营养无结构变化；活动 Markdown 文本块返回 `review` |
| 本地将 `data.timestamp` 从整数改为字符串 | 同时定位文本 JSON 与 `structuredContent` 中的变化；CLI 退出 `2` |

活动日历的 Markdown 展示文本按文本块处理，结构字段通过 `structuredContent` 比较。原样比较的 `review` 对应这个文本块。类型变更实验修改的是本地副本。

## 复现

[实测结构包](../examples/fixtures/official-20261024.json) 由本次查询提取，标量值已替换为占位值。安装项目后运行：

```bash
python examples/check_recorded_structure.py
```

脚本通过标准 MCP 客户端检查三项响应的字段类型、完整回放结果与本地接收结果。该检查已加入 Linux / macOS CI。
