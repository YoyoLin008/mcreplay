# McReplay · 麦回放

**把一次麦当劳 MCP 查询变成可复现的本地结构测试。**

面向维护麦当劳 MCP Skill、解析器和演示应用的个人开发者：删除响应真实值，保留结构，比较变化，再通过标准 MCP 在本地回放。

![结构变化报告](docs/demo-report.png)

## 解决什么问题

“昨天能解析，今天为什么空了？”字段类型改变、活动字段消失、文本返回变空，都可能让已有解析器失效。McReplay 把这些变化变成可定位、可复现的测试结果。

开发流程：在 AI 客户端中查询 → 本地提取结构 → 比较变化 → 回放样本，运行适配器回归测试。

- **结构观察包**：识别完整 JSON、代码围栏 JSON、`## Original Response` 后的 JSON，以及未解析文本与空文本。
- **变化检测**：工具删除、必填参数增加、字段消失、类型和封装变化；区分 `breaking`、`review`、`info`。
- **本地 MCP 回放**：官方 Python MCP SDK、stdio 协议；复用已记录的三种只读工具。
- **本地接收工具与 Skill**：接收一次正常官方查询的结果，在内存中删除原值后写入文件。
- **可用于 CI**：离线命令、明确退出码和独立 HTML 报告。

支持的工具包括 `now-time-info`、`campaign-calendar`、`list-nutrition-foods`。三项工具已于 2026-10-24 完成官方认证查询、结构提取与本地 MCP 回放验证，详见 [实测记录](docs/LIVE_VERIFICATION.md)。

## 30 秒离线试用

运行环境：Python 3.11+，Linux 或 macOS。

```bash
git clone https://github.com/YoyoLin008/mcreplay.git
cd mcreplay
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mcreplay demo --out-dir demo-output
```

打开 `demo-output/report.html`，查看三处预设的结构变化。演示使用合成样本；每次运行选择一个新输出目录。

```bash
mcreplay compare demo-output/before.json demo-output/after.json
# 该演示包含破坏性变化，因此 compare 预期退出码为 2。
```

可运行 `python examples/check_adapter.py demo-output/before.json` 查看独立 SDK 适配器通过；将文件换成 `after.json` 会检测到刻意加入的类型变化并退出 2。

退出码：`0` 无变化或仅信息项；`2` 有破坏性风险；`3` 仅需人工复核；`1` 输入或执行失败。

## 回放官方实测结构

仓库附带由三项官方查询提取的结构样本，可直接运行：

```bash
python examples/check_recorded_structure.py
```

该检查通过标准 MCP 客户端完成三项样本的接收和回放，并验证时间、活动及营养响应的字段格式。

## 三个实际开发工作流

### 1. 修改解析器前，先比较样本

```bash
mcreplay import private/export-before.json --out private/before.json
mcreplay import private/export-after.json --out private/after.json
mcreplay compare private/before.json private/after.json --html private/report.html
```

导入格式与字段含义见 [集成文档](MCP_INTEGRATION.md#本地导入格式)。输入与输出保存在本地 `private/` 目录，每次导入使用新的输出文件名。

### 2. 用本地样本测试 MCP 客户端

在客户端中添加以下 stdio 连接，并替换为本机的绝对路径：

```json
{
  "mcpServers": {
    "mcreplay-offline": {
      "command": "/absolute/path/to/.venv/bin/mcreplay",
      "args": ["replay", "/absolute/path/to/demo-output/before.json"]
    }
  }
}
```

选择 `mcreplay-offline` 连接，调用已记录的工具，即可把结构样本送入适配器测试。

### 3. 在正常 AI 客户端中保存一次结构观察

将仓库的 `skills/mcreplay/` 作为一个技能目录导入支持 `SKILL.md` 的客户端（目录位置按客户端文档设置）；详细步骤见 [Skill](skills/mcreplay/SKILL.md)。连接官方 MCP 及本地接收服务：

先在项目目录运行 `mkdir -m 700 private`，再将下面的绝对路径替换为本机实际路径。接收服务要求父目录已存在，输出文件尚未存在。

```json
{
  "mcpServers": {
    "mcreplay-local": {
      "command": "/absolute/path/to/.venv/bin/mcreplay",
      "args": ["capture", "--out", "/absolute/path/to/private/observation.json"]
    }
  }
}
```

向客户端明确提出：“查询一次当前麦当劳活动，并用 McReplay 保存其结构供我本地测试。”Skill 执行这次只读查询，再将完整 `CallToolResult` 交给本地 `record_mcd_observation`。一次接收服务只写一个新文件；需要新观察时配置新路径并重启。

官方连接使用 `https://mcp.mcd.cn`、Streamable HTTP 和 Bearer Token。配置示例见 [mcp-config.example.json](mcp-config.example.json)；环境变量展开方式因客户端而异，须按客户端文档配置。凭证保存在客户端的安全配置中。

## 架构

```text
用户明确查询 → 正常 AI MCP 客户端 → 官方 MCP（三种只读工具）
                         │ 完整结果，瞬时传递
                         ▼
                 本地 capture / import
                  验证 → 删除值 → 结构包
                            ├─ compare → 终端 / HTML / CI 退出码
                            └─ replay → 本地 stdio MCP → 适配器
```

CLI 负责导入和比较，MCP 服务负责接收和回放。字符串、数字、布尔值替换为占位符，字段结构与 MCP 协议标记保留。

## 测试与开发

```bash
# requirements.lock 记录本次验证的完整运行依赖版本（不含工具开发依赖）
python -m pip install -r requirements.lock
python -m pip install -e '.[dev]'
pytest -q
ruff check .
python -m build
```

120 项测试覆盖值删除、异常输入、结构差异和本地 MCP 协议路径。测试结果与集成验证进度见 [QA 记录](docs/QA.md)。

## 使用文档

- [MCP 集成与数据格式](MCP_INTEGRATION.md)
- [比较规则与支持范围](docs/limitations.md)
- [本地数据管理](SECURITY.md)
- [参与开发](CONTRIBUTING.md)

## 研究、许可与致谢

选题前检查了全部 33 个官方文档工具和 10 个参赛项目的 README 与实现：[能力矩阵](docs/capability-matrix.md)、[竞争研究](docs/competitive-research.md)、[加权选题](docs/product-selection.md)、[PRD](docs/PRD.md)。

代码采用 [MIT 许可](LICENSE)。感谢麦当劳中国开放 MCP 文档、MCP Python SDK 维护者和公开记录问题的开发者。
