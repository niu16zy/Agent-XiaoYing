# 企业知识问答 Agent

第三题：帮助员工从带文档 ID 和版本日期的合成制度、产品 FAQ 中获取有依据的答案。模型选择检索、读取、补充查证、追问或停止；引用只能来自本次成功读取的原文。

## 当前交付

阶段一至四的本地开发与验收已完成，GitHub 上传尚未确认成功。目标仓库：[niu16zy/Agent-XiaoYing](https://github.com/niu16zy/Agent-XiaoYing)。提交状态见 [提交说明](docs/07-submission.md)。

- 工程测试：108 通过，1 个付费 API 测试默认跳过；完整真实验收另行执行。
- 15 组真实模型验收的最新结果通过原文与语义复核；另有 1 组 Mock 预算测试。最新结果汇总跨完整批次和 2 例补验，不是“一轮全部成功”。
- 阶段四共保存 65 次真实运行（含基线实验、失败与重跑）。不能把重跑后的通过率当作稳定性指标。
- 同一组 6 个问题、同模型同提示下，检索基线自动检查通过 5/6，改进版 6/6；工具调用合计 24→14。固定查询的 11 组开发样例 Recall@5 为 0→1，基线仅为整句字面匹配，不能代表对成熟搜索系统的提升。

评审先看 [完整验收报告](examples/stage4/README.md)、[评估方法](docs/03-evaluation.md)和[结果索引](examples/stage4/verification.json)。复核者为 Codex AI，不能记作候选人独立验收。

## 安装

已在 Windows PowerShell / Python 3.12.3 的全新项目虚拟环境验证。代码要求 Python ≥3.10，其他版本尚未实测。项目使用原生 Python 有界循环，无 Agent 框架依赖。

在项目根目录执行（不需要激活虚拟环境）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[model,dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

直接依赖为 OpenAI SDK 2.30.0、pytest 9.1.1；`requirements-lock.txt` 记录本次 Windows 环境全部实际运行依赖版本。需要这些精确版本时，可先执行 `python -m pip install -r requirements-lock.txt`，再安装本项目。锁定文件是版本快照，不保证跨平台安装。首次下载因文件不完整导致哈希校验失败；保持校验并重新下载后成功，记录见 [环境验证](examples/stage4/environment-verification.json)。

## 配置真实模型

仅在本地 `.env` 填写密钥；文件已被 Git 忽略。如不存在，可根据 `.env.example` 创建，勿覆盖已配置文件。详细位置见 [DeepSeek 指南](docs/06-deepseek-setup.md)。

```dotenv
MODEL_API_KEY=在本地填写你的密钥
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-flash
```

同名环境变量优先于 `.env`。DeepSeek 官方地址也支持 `DEEPSEEK_API_KEY` 备用变量，不使用 OpenAI 密钥回退。不要把真实密钥放进命令、文档或提交历史。

```powershell
.\.venv\Scripts\python.exe scripts/check_model_connection.py
.\.venv\Scripts\knowledge-agent.exe --mode real --question "报销期限多久？" --format text --model-timeout 90 --total-timeout 300
.\.venv\Scripts\knowledge-agent.exe --mode real --scenario conflict --question "报销期限多久？" --format text --model-timeout 90 --total-timeout 300
.\.venv\Scripts\python.exe -m knowledge_agent --mode real --input examples/inputs/follow_up.json --format text --model-timeout 90 --total-timeout 300
```

连接检查在新虚拟环境实测返回 `connected`。业务验收使用同一 SDK 版本；详细传递依赖、模型参数、源码哈希和语料快照记录于各批次 manifest。真实模式失败会明确返回错误，不静默切换 Mock。

## 离线演示与完整评估

离线运行不需要密钥。源码入口可用系统 Python，或使用上述虚拟环境：

```powershell
python scripts/run_agent.py --mode mock --question "报销期限多久？" --format text
python scripts/evaluate.py
python scripts/evaluate.py --mode real --compare-baseline
python scripts/evaluate.py --mode real --cases T07 T08 T09 T04-v1 T04-v2
```

第一条 Mock 只演示流程，预期 `incomplete`、退出码 2。第二条执行离线检索实验与 T10 预算测试，不执行真实业务验收。第三条显式启用付费 API，运行 15 个真实输入、1 个 Mock 上限用例及 6 次基线对照。不要把评估器的 `automatic_pass` 当作语义通过；新运行默认仍是 `semantic_review=pending`。评估器只把问题、历史和工具观察传给模型，标准答案只供运行结束后检查。

如要启用 pytest 内单例真实连接与业务冒烟测试（完整评估不要求重复执行）：

```powershell
$env:KNOWLEDGE_AGENT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py::test_opt_in_live_core -q
Remove-Item Env:KNOWLEDGE_AGENT_LIVE
```

## 输出与边界

输出包括 `answer`、`status`、`citations`、`conflicts`、`gaps`、`follow_up_question`。每条引文包含文档 ID、版本日期、原文、字符位置和快照 ID。每次运行保存 input/output、evidence、evidence-state、answer.txt 和逐步 trace.jsonl。Trace 记录简短行动依据，不存内部思维过程。

状态有 `answered`、`needs_clarification`、`insufficient_evidence`、`tool_error`、`incomplete`。单次 CLI 的前三种退出码为 0，后两种为 2。评估器以改进版自动检查失败返回 1；基线实验失败保留为结果，不阻止归档。

默认最多 8 轮模型、6 次业务工具调用，模型单次 30 秒、工具 5 秒、总计 120 秒；本次真实评估将模型/总超时设为 90/300 秒，调用次数不变。工具次数达到上限立即返回未完成，因此模型应提前收尾。重试、无效动作、引用修正均消耗预算，SDK 自动重试关闭。超时只停止等待，不能强杀后台线程；当前仅提供只读工具。

引用校验、有限数值冲突提示和词句拦截不能证明所有语义正确性。词句拦截可能误拒绝合理表述；一般改写冲突仍依赖模型，真实企业大规模检索、权限控制、生产稳定性、独立留出集尚未实现。

## 目录与阅读顺序

- [开发方案](docs/00-development-plan.md)、[需求](docs/01-requirements.md)、[技术设计](docs/02-solution.md)。
- [评估报告](docs/03-evaluation.md)、[AI 使用记录](docs/04-ai-usage.md)、[复盘](docs/05-retrospective.md)。
- `src/knowledge_agent/`：工具、检索、模型、执行器、证据、校验、展示、评估器。
- `data/`：12 份完全虚构的短文档、6 场景、14 个用例定义（扩展为16个输入）。没有真实员工或客户数据。
- `examples/stage4/`：当前结果及所有阶段四失败记录；`stage1/2/3` 为历史证据。

实际主动开发总时长未完整记录，不能把原建议 180 分钟当作实际用时。源码使用可编辑安装，运行命令需在项目根目录；从其他位置使用时请显式提供 `--data-dir`、`--env-file`、`--output-dir`。本项目不包含网页、部署或多 Agent。
