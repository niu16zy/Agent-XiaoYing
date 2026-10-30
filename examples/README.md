# 当前评审入口

最新结果见 [阶段四报告](stage4/README.md)与 [验收索引](stage4/verification.json)。stage1/2/3为历史，stage4保留所有失败与重跑。

# 验证材料保存规范

当前最新结果为 `stage3/`：85 项工程测试及 14 次真实运行，覆盖 10 个用例。最新选定结果均通过本次核验，首轮失败保留并说明。详见 `stage3/README.md` 和 `stage3/verification.json`。下面各阶段说明按历史时间保留。

当前包含开发前静态检查 `preparation-validation.json` 和阶段一实际工具记录 `stage1/`，其中有 pytest 结果和五组工具输出。尚无 Agent 实际答案或模型 Trace；阶段一脚本直接执行指定工具，不能作为模型动态决策证据。

阶段二更新：`stage2/` 保存 70 项工程测试、四组 Mock 执行记录，以及两次失败的真实调用（连接失败、HTTP 401）。Mock 已使用 Agent 执行器，但不能证明真实模型决策；real 目录目前也没有成功的模型动作。详见 `stage2/README.md`。`inputs/` 是人工合成的历史和故障配置，不是真实历史记录。

最新补验：`stage2/deepseek-tests.xml` 为 72 项通过的工程测试；`stage2/real-acceptance.json` 为两条成功 DeepSeek 路径的实际核验，分别覆盖明确答案和文档冲突。以上旧失败记录保留历史语境，以最新补验和 `stage2/README.md` 为当前状态。

后续每次运行建议保存：

- `input.json`：问题、历史、运行模式、语料快照、模型及必要配置；不含密钥。
- `output.json`：实际回答、引用、冲突、缺口、追问和状态。
- `trace.jsonl`：每步模型动作、工具参数、返回摘要、错误、后续动作及简短依据。
- `evaluation.json`：预期、实际、自动检查结果、人工语义核验、失败原因。

真实模型记录存放于 `real/<run_id>/`，Mock 记录存放于 `mock/<run_id>/`。至少覆盖正常、资料不足和工具失败；至少两条真实模型路径体现对工具结果的动态响应。

检索改进实验单独保留 baseline / improved 的参数、同一组输入和实际结果。文档替换实验记录语料内容快照，确保可以解释相同 ID 和日期下的不同答案。

`data/evaluation_cases.json` 的历史和期望是合成测试材料，不是已经发生的真实运行记录。
