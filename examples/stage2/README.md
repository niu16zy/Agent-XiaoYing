# 阶段二验证记录

状态：阶段二实现及两条真实模型路径验收完成。Python 3.12.3、pytest 9.1.1、OpenAI SDK 2.30.0，真实模型 deepseek-flash。最新累计 72 项测试通过，机器结果为 `deepseek-tests.xml`；此前 70 项的 `tests.xml` 保留为历史记录。真实验收结论见 `real-acceptance.json`。

## 实际运行记录

| 目录（相对本目录） | 实际结果 | 说明 |
|---|---|---|
| `real/20261029T143416Z-56eae51d/` | answered | DeepSeek 检索 → 读取 D01 → 回答 30 个自然日；3 轮/2 次工具调用 |
| `real/20261029T143544Z-792bacff/` | needs_clarification | DeepSeek 读取 D01/D02 后展示冲突并请求确认；6 轮/3 次工具调用，含 2 轮响应格式修正 |
| `real/20261029T095334Z-70e3adbc/` | tool_error / MODEL_REQUEST_FAILED | 默认执行环境连接失败，1 次模型尝试、0 次工具调用 |
| `real/20261029T095419Z-f8b55dc0/` | tool_error / MODEL_HTTP_401 | 联网环境到达服务端但认证失败，1 次模型尝试、0 次工具调用 |
| `mock/20261029T095626Z-fe165abd/` | incomplete | 检索 → 读取 → 明确 Mock 边界，3 轮、2 次工具调用 |
| `mock/20261029T095627Z-86c9487f/` | tool_error | 检索 → 读取失败 → 停止，3 轮、2 次工具调用 |
| `mock/20261029T095627Z-4f7e95dc/` | incomplete | 带合成历史输入，3 轮、2 次工具调用 |
| `mock/20261029T095628Z-750e5f38/` | incomplete / BUDGET_EXHAUSTED | 配置 1 轮预算，1 次检索后停止，无额外模型调用 |

真实失败记录产生于配置记录功能补充之前，因此没有 model-config.json；input.json 记录实际模式、模型、语料快照和预算。后续运行将额外保存 model-config.json。两次真实请求均使用默认官方地址和 gpt-4.1-mini，未取得响应动作。诊断列表请求也因连接失败未取得结果，未计入上述问答运行。

## 复现

在项目根目录运行：

```powershell
python -m pytest -q --junitxml=examples/stage2/tests.xml
python scripts/run_agent.py --mode mock --question "报销期限多久？" --output-dir examples/stage2/mock
python scripts/run_agent.py --mode mock --question "报销期限多久？" --fault examples/inputs/read_failure.json --output-dir examples/stage2/mock
python scripts/run_agent.py --mode mock --input examples/inputs/follow_up.json --output-dir examples/stage2/mock
python scripts/run_agent.py --mode mock --question "报销期限多久？" --max-model-turns 1 --output-dir examples/stage2/mock
```

以上 Mock 命令均返回退出码 2，代表模拟器主动标记未完成或工具错误，并非 CLI 崩溃。每次创建新目录，不覆盖已有结果。

已配置有效 `.env` 并成功执行的真实验收命令：

```powershell
python scripts/run_agent.py --mode real --question "报销期限多久？" --model-timeout 90 --total-timeout 300 --output-dir examples/stage2/real
python scripts/run_agent.py --mode real --scenario conflict --question "报销期限多久？" --model-timeout 90 --total-timeout 300 --output-dir examples/stage2/real
```

两条真实路径的引文均与本次读取原文、版本和字符位置一致；语义检查确认单一依据保留了自然日及起算点，冲突输出没有擅自确定优先制度。冲突查证发生在读取双方全文的过程中，本次没有额外补充检索动作。两轮无效响应被反馈修正并计入预算，未隐去。

阶段二的真实模型决策循环已得到实际证据；Mock 和 ScriptedModel 仍只用于工程测试。全部六项业务验收的剩余场景、批量稳定性检查和阶段三语义核验机制尚未完成。
