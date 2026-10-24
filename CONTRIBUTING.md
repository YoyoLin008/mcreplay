# 参与开发

欢迎提交解析失败、结构比较、数据处理或文档问题。Issue 请附合成最小样本、运行命令、Python 版本和预期行为。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
python -m build
```

修复应包含能复现问题的测试。测试和 CI 使用本地合成样本。

修改比较规则时，说明输入约束对调用者的影响，以及输出结构变化对解析器的影响。新增响应格式需覆盖正常、失败和未知状态，并验证标量值已被替换。

提交原创或获授权的代码，并注明第三方来源。`CONTEST_DECLARATION.md` 按比赛要求保留原文。
