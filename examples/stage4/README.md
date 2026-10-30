# 阶段四实际验收

2026-10-30。第三题，真实模型 deepseek-flash。当前结果以 [verification.json](verification.json) 为索引，由 Codex AI 核对引文与答案；不是候选人独立复核，也不是稳定性证明。

## 最新结果

15 组真实用例的最新结果通过复核，1 组 Mock 上限测试通过。完整批次 `20261030T034927Z-acc6a38a` 加补验 `20261030T035227Z-15c2e5e1` 的 T06B/T09 构成最终集合。历史结果不覆盖、不删除。

| 用例 | 模式 | 状态 | 证据 |
|---|---|---|---|
| T01 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T034930Z-907c44b6/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034930Z-907c44b6/trace.jsonl) |
| T02 | real | needs_clarification | [输出](20261030T034927Z-acc6a38a/improved/20261030T034934Z-13aa0891/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034934Z-13aa0891/trace.jsonl) |
| T03 | real | insufficient_evidence | [输出](20261030T034927Z-acc6a38a/improved/20261030T034942Z-f65e987d/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034942Z-f65e987d/trace.jsonl) |
| T04 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T034949Z-72aa0f25/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034949Z-72aa0f25/trace.jsonl) |
| T04-v1 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T034953Z-fb111a92/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034953Z-fb111a92/trace.jsonl) |
| T04-v2 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T034957Z-9c792977/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T034957Z-9c792977/trace.jsonl) |
| T05 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035001Z-35d83877/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035001Z-35d83877/trace.jsonl) |
| T06A | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035008Z-0036bfdf/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035008Z-0036bfdf/trace.jsonl) |
| T06B | real | tool_error | [输出](20261030T035227Z-15c2e5e1/improved/20261030T035230Z-0e25b25e/output.json) · [轨迹](20261030T035227Z-15c2e5e1/improved/20261030T035230Z-0e25b25e/trace.jsonl) |
| T07 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035019Z-c32315dc/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035019Z-c32315dc/trace.jsonl) |
| T08 | real | needs_clarification | [输出](20261030T034927Z-acc6a38a/improved/20261030T035023Z-d38926b1/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035023Z-d38926b1/trace.jsonl) |
| T09 | real | insufficient_evidence | [输出](20261030T035227Z-15c2e5e1/improved/20261030T035235Z-03970ba3/output.json) · [轨迹](20261030T035227Z-15c2e5e1/improved/20261030T035235Z-03970ba3/trace.jsonl) |
| T10 | mock | incomplete | [输出](20261030T034927Z-acc6a38a/improved/20261030T035035Z-2e8ec073/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035035Z-2e8ec073/trace.jsonl) |
| T11 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035036Z-8398060e/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035036Z-8398060e/trace.jsonl) |
| T12 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035041Z-3dc4848f/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035041Z-3dc4848f/trace.jsonl) |
| T13 | real | answered | [输出](20261030T034927Z-acc6a38a/improved/20261030T035047Z-586dc4e7/output.json) · [轨迹](20261030T034927Z-acc6a38a/improved/20261030T035047Z-586dc4e7/trace.jsonl) |

每个目录还包含 input.json、evidence.json、evidence-state.json、answer.txt、automatic-checks.json、model-config.json、run-config.json。最终采用的运行包含 semantic-review.json，记录复核说明和 output SHA256。自动检查与人工式 AI 语义复核分开；自动报告中的 pending 保留，复核结果见独立文件。

## 失败与修复

1. 首轮 `20261030T034032Z-bfb9c443`：15个真实用例自动检查全通过，但语义复核发现T12虚构精确到期日和“含当日”；T04/T04-v2/T06A/T06B有引文覆盖不足或摘要断言。整批不认定验收通过。加强逐句引用、禁止不必要扩写，并增加日期边界拦截。
2. 第二轮 `20261030T034431Z-2bad2312`：T09耗尽6次工具预算返回incomplete，T06B仍转述未经核实的候选数字，T02附加描述未被最终引文覆盖。补充提前收尾和不得转述未核实数字的提示，没有增加预算或放宽状态要求。
3. 第三轮完整批次：自动检查全通过，但T09附加其他未读文档摘要断言，增加最终回答摘要断言拦截与回归测试。T09和T06B单独补验通过，其余最终样例重新用最终校验器审计。

共保存65次真实运行：三次完整批次各21次（15验收+6基线），最后补验2次。每个全量批次另有1次Mock预算测试。失败不是被平均分掩盖的成功结果，必须读各批次 semantic-review.json。

## 检索与证据变化

固定输入实验见 [retrieval-comparison.json](20261030T034927Z-acc6a38a/retrieval-comparison.json)：11个有相关文档标签的输入，top_k=5，同问题同场景；有历史时两种算法都附加先前用户问题。整句字面子串匹配的宏平均Recall@5为0，中文双字词项/同义词/IDF和标题权重检索为1；冲突两侧均须召回。无标签的资料外/故障问题不计算召回。样本来自开发集，且基线很弱，不代表生产搜索效果。

[同模型对比](live-retrieval-comparison.json)：六个输入、同一模型/提示/预算/语料，基线自动检查5/6通过、工具24次、模型30轮；改进版6/6通过、工具14次、模型20轮。基线通过缩短查询可恢复部分问题，说明模型确实会观察空结果并改写查询。单次随机实验不能推断显著性或普遍提升。

[内容替换对比](mutation-comparison.json)：T01的30天→T07的45天，ID与日期未变但快照改变；T08新增D02后读取双方并追问；T09删除期限后补检索并报告不足。每项链接两侧实际run_id与动作，不要求数值替换必定改变动作序列。

## 复现与局限

[环境验证](environment-verification.json)：全新.venv安装成功，pip check、安装后的CLI/模块入口及离线评估均通过；首次下载不完整导致哈希校验失败，未关闭校验，禁用缓存重下载后成功。详细安装调试日志仅保留本机并被Git忽略。[venv-tests.xml](venv-tests.xml)为最终108通过、1个付费API测试默认跳过。新环境真实模型连接另行验证connected。

没有独立留出集、重复稳定性统计或全语义证明；源码哈希和依赖版本随批次保存，最后两例补验在新增摘要校验后执行。精确主动开发总时长未记录。GitHub网络检查失败，本地Git提交与远端上传分开记录，详见 [提交说明](../../docs/07-submission.md)。
