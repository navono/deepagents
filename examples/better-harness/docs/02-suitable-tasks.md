# 适合 Better Harness 优化的任务类型

## 判断标准

核心判断：**Agent 的行为是否可以通过调优 prompt / tools / middleware 来改善**，以及 **是否能写出明确的 pass/fail 评估**。

### 适合 ✅

- 有明确的对/错判断
- 行为主要由 prompt / tools / middleware 决定（而非模型基础能力）
- 可重复运行，结果稳定
- 窄范围，针对性改进

### 不适合 ❌

- 开放式创意任务（写小说、写营销文案）
- 行为由模型基础能力决定（纯推理、数学）
- 依赖外部 API 实时响应（不可控）
- 太宽泛，"让 agent 变聪明"

---

## 两种使用模式的适用任务

### Pattern A：你已有 evals

适合场景：你已经有一个 Agent + 一套测试，但通过率不理想，想自动调优。

| 任务类型 | 具体例子 | 为什么适合 |
|----------|---------|-----------|
| **工具选择** | Agent 需要在 send_email / send_slack / create_ticket 中选对工具 | 有唯一正确答案，对 prompt 和 tool description 非常敏感 |
| **追问质量** | 用户意图模糊时，Agent 是否问了正确的问题而非瞎猜 | 可用 rubric 评估，受 prompt 影响大 |
| **输出格式** | Agent 必须返回 JSON / 表格 / 特定 schema | 二元判断（格式对/错），通过 prompt 约束即可改善 |
| **安全/拒绝策略** | 面对越权请求时是否正确拒绝 | 明确的 pass/fail，middleware 能直接拦截 |
| **多步骤工作流** | 报告生成 → 审核 → 发送，步骤是否完整 | 每步可检查，prompt 可以明确流程规范 |

**典型 prompt 示例：**

```
我的 Agent 在工具选择评估中通过率只有 60%，
经常在应该用 send_email 的时候用了 send_slack。
这是我的 eval 测试，帮我优化 harness。
```

---

### Pattern B：没有 evals，需要先 bootstrap

适合场景：你有一个明确的任务目标，但还没写过评估测试。

| 任务类型 | 具体例子 | Bootstrap 思路 |
|----------|---------|---------------|
| **客服路由** | 用户提问 → 正确路由到退货/技术支持/销售 | AI 先生成一批"用户问题 + 正确部门"的 case，然后优化 prompt 让路由准确 |
| **代码审查 Agent** | 对 PR diff 提出有意义的 review 意见 | AI 先构造几组 diff + 预期 review 要点的 case，再优化 prompt 让 review 更到位 |
| **数据提取** | 从非结构化文本中提取结构化字段 | 写几个输入文本 + 期望的 JSON 输出作为 eval，优化 prompt 和 tool schema |
| **报告生成** | 根据用户需求生成特定格式的报告 | 构造"需求描述 + 期望报告格式/内容要点"的 eval，优化 prompt 和 skills |

**典型 prompt 示例：**

```
我有一个客服路由 Agent，需要把用户问题分到正确的部门。
帮我 bootstrap 一套 eval 测试，然后运行优化循环，
让它在退货、技术支持、销售三个路由上都达到高准确率。
```

---

## 完整案例：日报总结 Agent

假设你要做一个日报总结 Agent：接收一天的 Slack 消息，生成结构化日报。

### 配置文件

```toml
[experiment]
name = "daily-report-agent"
runner = "pytest"
workspace_root = "/path/to/my-agent"
model = "claude-sonnet-4-6"
max_iterations = 5

[surfaces.prompt]
kind = "module_attr"
target = "my_agent.graph:DAILY_REPORT_PROMPT"
filename = "prompt.txt"
base_value = """
你是一个日报总结助手。请根据今天的消息生成一份日报。
"""

[surfaces.report_template]
kind = "workspace_file"
target = "my_agent/templates/report.md"
filename = "report_template.md"
base_value = """
# 日报

## 今日进展
- ...
## 阻塞事项
- ...
## 明日计划
- ...
"""

# train eval: 消息中明确有进展/阻塞/计划
[[cases]]
case_id = "tests/test_daily_report.py::test_basic_summary[{model}]"
split = "train"
stratum = "format"

[[cases]]
case_id = "tests/test_daily_report.py::test_action_items_extracted[{model}]"
split = "train"
stratum = "content"

# holdout eval: 消息很杂乱，考验 Agent 的归纳能力
[[cases]]
case_id = "tests/test_daily_report.py::test_noisy_messages[{model}]"
split = "holdout"
stratum = "robustness"
```

### 为什么这个任务适合

1. **格式正确性**可以二元判断（有没有分三个 section）
2. **内容质量**可以用关键词匹配或 LLM-as-judge 评估
3. **prompt 和模板**是核心可调表面，改了确实会影响结果
4. 范围足够窄，几轮迭代就能看到提升

---

## 总结

**一句话原则**：如果你能说出"Agent 做这件事的正确行为是什么"，并且这个行为受 prompt / tools / middleware 配置影响，那这个任务就适合用 better-harness 优化。

最有价值的场景是 **Agent 行为边界 case** — 大部分情况 Agent 做得还行，但在特定场景（工具选择、追问、格式、安全）上翻车。这些正是 harness 调优能解决的问题。
