# 阶段一实际验证记录

环境：Windows PowerShell、Python 3.12.3、pytest 9.1.1。测试命令：`python -m pytest -q --junitxml=examples/stage1/tests.xml`。

最终结果：41 项通过。首轮 40 项通过、1 项失败（基线中文短查询无命中），修复字面匹配后重新全量验证通过。`tests.xml` 保存最终机器可读结果。

| 文件 | 运行参数 | 验证内容 |
|---|---|---|
| `baseline.json` | 默认参数 | 原文为 30 个自然日，不含 D02 |
| `conflict.json` | `--scenario conflict` | 检索候选中同时包含 D01 / D02 |
| `deadline_45.json` | `--scenario deadline_45` | 同一 ID 和日期下正文变为 45 个自然日，快照改变 |
| `deadline_missing.json` | `--scenario deadline_missing` | 读取正文不再含期限依据 |
| `tool_failure.json` | `--fail-read` | 读取返回 TOOL_UNAVAILABLE、无伪造正文 |

上述文件均由 `python scripts/stage1_demo.py` 实际运行生成，使用 `--output` 保存。它们是工具输出，`model_called` 均为 false，不是 Agent 答案、真实模型 Trace 或业务验收通过证据。

测试另覆盖不可变快照、未知/重复 ID、非法日期、隐藏文档替换、改写查询、材料及产品查询、引用片段位置、空检索、结果截断、非法参数、瞬时和持续故障、不自动重试等。

模型配置检查：检测到 API 密钥变量，但缺少明确的模型名和服务地址，未调用服务；连通性待阶段二验证。密钥未保存到记录。
