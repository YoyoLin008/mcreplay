# MCP 集成

McReplay 将麦当劳 MCP 查询结果接入本地开发流程：提取结构、比较变化，再通过标准 MCP 回放到解析器或适配器。

## 官方连接

- [官方文档](https://github.com/M-China/mcd-mcp-server)
- [MCP 平台](https://open.mcd.cn/mcp)
- 端点：`https://mcp.mcd.cn`
- 传输：Streamable HTTP
- 认证：`Authorization: Bearer <MCP_TOKEN>`，在 AI 客户端的安全配置中设置。

在官方平台登录并开通 MCP 后，按客户端文档配置连接。[配置示例](mcp-config.example.json) 使用 `${MCD_MCP_TOKEN}` 环境变量占位符；具体展开方式按客户端文档设置。官方服务的使用规则见 [MCP Server 服务规则](https://cdn.mcd.cn/cms/pages/MCPServerRules.html)。

## 支持的工具

| 工具 | 官方用途 | 开发测试场景 |
|---|---|---|
| `now-time-info` | 当前时间信息 | 时间响应的字段类型和文本封装变化 |
| `campaign-calendar` | 当月营销活动日历 | 活动记录、集合及空结果变化 |
| `list-nutrition-foods` | 常见餐品营养成分 | JSON、普通文本和空文本之间的变化 |

当前版本接收这三个工具的空参数调用 `{}`。Skill 会检查客户端提供的工具定义，参数要求不匹配时结束操作并说明原因。

## 查询、保存与回放

1. 用户在 AI 客户端中请求一次查询并保存结构；已有完整查询结果时直接使用。
2. 客户端调用对应工具。认证、限流、超时等错误会结束本次流程。
3. 客户端将完整 MCP `CallToolResult` 传给本地 `record_mcd_observation(name, result)`。
4. 本地识别响应封装，将字符串、数字和布尔值替换为占位符，写入 `mcreplay/v1` 结构包。
5. `compare` 比较两份结构包，`replay` 通过 MCP SDK 的 stdio 协议回放样本。

`capture` 使用空参数 schema；`import` 还可接收导出文件中的工具定义。接收服务每次保存一个新文件，下一次观察使用新路径并重启连接。

## 本地导入格式

最小合成示例：

```json
{
  "tools": [{
    "name": "now-time-info",
    "inputSchema": {"type": "object", "properties": {}}
  }],
  "observations": [{
    "name": "now-time-info",
    "arguments": {},
    "response": {
      "content": [{"type": "text", "text": "{\"sampleTime\":\"fixture-only\"}"}],
      "isError": false
    }
  }]
}
```

```bash
mcreplay import private/export.json --out private/capture.json
```

`source` 记录输入方式：`synthetic` 为演示生成，`user-import` 为本地导入或接收。结构包包含工具定义、带占位值的 `CallToolResult` 和结构描述。协议 `type`、`isError` 等标记保留。

导入文件保留在原位置。字段名也会保留，分享前检查其中的个人信息；存储方式见 [本地数据管理](SECURITY.md)。

## 响应处理

| 输入 | 处理方式 |
|---|---|
| 完整 JSON、围栏 JSON、Markdown 后缀 JSON | 提取结构，生成相同封装的样本 |
| 普通文本 | 记录 `text` 类型，使用文本占位符 |
| 空文本、空数组、`isError` | 保留对应状态，在比较报告中显示 |
| 格式错误、超限、不支持的工具或参数 | 返回明确错误 |
| 已存在的输出文件 | 提示使用新路径 |
| 回放缺少观察或参数不匹配 | 返回 MCP 工具错误 |

## 验证记录

本地协议测试通过标准 MCP SDK 客户端连接 stdio 服务，覆盖工具发现、调用、接收、回放及错误路径。详细结果和官方连接验证进度见 [QA 记录](docs/QA.md)，比较规则见 [支持范围](docs/limitations.md)。
