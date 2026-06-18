# Eval 编写指南

## 整体架构

Better Harness 的 eval 基于 **pytest**，核心流程：

```
构造用户输入 → 调用 Agent → 捕获完整轨迹(Trajectory) → 用断言打分
```

Eval 就是普通的 pytest 测试函数，但遵循一套统一的写法模式。

---

## 核心组件

### 1. `conftest.py` — 测试基础设施

每个 eval 项目需要一个 `conftest.py`，负责：

- 注册 `--model` 参数（better-harness 通过这个传模型名）
- 注册 `--evals-report-file` 参数（better-harness 通过这个读取测试结果）
- 创建 `model` fixture（根据 `--model` 初始化 LLM）
- 在 `pytest_sessionfinish` 中写出 JSON 报告

```python
# conftest.py 精简版
import json
from pathlib import Path
import pytest

COUNTS = {"passed": 0, "failed": 0, "skipped": 0}


def pytest_addoption(parser):
    parser.addoption("--model", action="store", default="demo-model")
    parser.addoption("--evals-report-file", action="store", default="")


@pytest.fixture
def model(request):
    model_name = request.config.getoption("--model")
    # 返回初始化好的 LLM 实例
    return init_chat_model(model_name)


def pytest_configure(config):
    for key in COUNTS:
        COUNTS[key] = 0


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    if report.passed:
        COUNTS["passed"] += 1
    elif report.failed:
        COUNTS["failed"] += 1
    elif report.skipped:
        COUNTS["skipped"] += 1


def pytest_sessionfinish(session, exitstatus):
    summary_file = str(session.config.getoption("--evals-report-file"))
    if not summary_file:
        return
    total = COUNTS["passed"] + COUNTS["failed"] + COUNTS["skipped"]
    payload = {
        "model": str(session.config.getoption("--model")),
        "passed": COUNTS["passed"],
        "failed": COUNTS["failed"],
        "skipped": COUNTS["skipped"],
        "total": total,
        "correctness": 0.0 if total == 0 else COUNTS["passed"] / total,
    }
    Path(summary_file).parent.mkdir(parents=True, exist_ok=True)
    Path(summary_file).write_text(json.dumps(payload, indent=2) + "\n")
```

### 2. 断言工具箱

项目提供了这些开箱即用的断言，定义在 `utils.py` 中：

#### 成功断言（不通过就 fail 测试）

| 断言 | 用途 | 示例 |
|------|------|------|
| `final_text_contains(text)` | 最终回复包含某文本 | `final_text_contains("U12345")` |
| `final_text_excludes(text)` | 最终回复不包含某文本 | `final_text_excludes("我不确定")` |
| `file_equals(path, content)` | 生成的文件内容完全匹配 | `file_equals("config.json", '{"port": 8080}')` |
| `file_contains(path, substring)` | 生成的文件包含某文本 | `file_contains("report.md", "进展")` |

#### 效率断言（只记录，不 fail 测试）

| 断言 | 用途 | 示例 |
|------|------|------|
| `agent_steps=N` | Agent 执行了 N 步 | `agent_steps=2` |
| `tool_call_requests=N` | 调用了 N 次工具 | `tool_call_requests=1` |
| `tool_call(name, args_contains)` | 检查是否调用了特定工具 | `tool_call(name="slack_send_dm")` |

#### LLM-as-Judge 断言（主观质量评估）

| 断言 | 用途 | 来源 |
|------|------|------|
| `llm_judge(criterion1, criterion2, ...)` | 用 LLM 裁判评判回复质量 | `llm_judge.py`，基于 `openevals` |

### 3. `TrajectoryScorer` — 评分器

所有断言通过 `TrajectoryScorer` 组合：

```python
scorer = (
    TrajectoryScorer()
    .expect(                          # 效率断言，只记录不 fail
        agent_steps=2,
        tool_call_requests=1,
        tool_calls=[tool_call(name="gmail_send_email")],
    )
    .success(                         # 成功断言，不通过就 fail
        final_text_contains("U12345"),
    )
)
```

### 4. `run_agent()` — 执行入口

```python
trajectory = run_agent(
    agent,            # 编译好的 Agent 图
    model=model,      # LLM 实例（用于日志）
    query="用户输入",  # 字符串或消息列表
    scorer=scorer,    # TrajectoryScorer 实例
)
```

---

## 三种典型的 Eval 写法

### 类型 A：工具选择评估（精确断言）

**场景**：验证 Agent 选对了工具、参数正确

```python
"""Eval tests for tool selection behavior."""
from deepagents import create_deep_agent
from langchain_core.tools import tool
from tests.evals.utils import TrajectoryScorer, run_agent, tool_call, final_text_contains


# 1. 定义 mock tools（返回固定字符串，不调真 API）
@tool
def slack_send_dm(user_id: str, message: str) -> str:
    """Send a direct message to a user on Slack."""
    return f"Sent DM to {user_id}: {message}"


@tool
def gmail_send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail."""
    return f"Sent email to {to}: {subject} — {body}"


@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    return f"Top 3 results for '{query}'"


ALL_TOOLS = [slack_send_dm, gmail_send_email, web_search]


# 2. 构建测试
def test_direct_request_slack_dm(model):
    """Agent uses the Slack DM tool when explicitly asked."""
    # 构建带工具的 agent
    agent = create_deep_agent(model=model, tools=ALL_TOOLS)

    # 运行并评分
    run_agent(
        agent,
        model=model,
        query="Send a Slack DM to user U12345 saying 'Hello from evals'",
        scorer=(
            TrajectoryScorer()
            .expect(
                agent_steps=2,
                tool_call_requests=1,
                tool_calls=[
                    tool_call(name="slack_send_dm", args_contains={"user_id": "U12345"})
                ],
            )
            .success(
                final_text_contains("U12345", case_insensitive=True),
            )
        ),
    )
```

**关键点**：

- Mock tools 返回固定字符串，不调真 API
- `tool_call()` 检查工具名和参数
- `final_text_contains()` 检查最终回复

**更多测试模式**：

```python
# 间接请求：用户描述意图，Agent 推断工具
def test_indirect_email_report(model):
    """Agent infers the Gmail tool from 'email a report' request."""
    agent = create_deep_agent(model=model, tools=ALL_TOOLS)
    run_agent(
        agent,
        model=model,
        query="Email the weekly status report to manager@company.com",
        scorer=(
            TrajectoryScorer()
            .expect(
                tool_calls=[
                    tool_call(name="gmail_send_email", args_contains={"to": "manager@company.com"})
                ],
            )
            .success(
                final_text_contains("manager@company.com", case_insensitive=True),
            )
        ),
    )


# 多步骤：工具链
def test_chain_search_then_email(model):
    """Agent searches the web then emails results — two tools in sequence."""
    agent = create_deep_agent(model=model, tools=ALL_TOOLS)
    run_agent(
        agent,
        model=model,
        query="Search for 'LangGraph 0.3 release notes' and email a summary to team@co.com",
        scorer=(
            TrajectoryScorer()
            .expect(
                tool_calls=[
                    tool_call(name="web_search"),
                    tool_call(name="gmail_send_email", args_contains={"to": "team@co.com"}),
                ],
            )
            .success(
                final_text_contains("team@co.com", case_insensitive=True),
            )
        ),
    )
```

---

### 类型 B：追问质量评估（LLM-as-Judge）

**场景**：验证 Agent 面对模糊请求时的追问是否合理

```python
"""Eval tests for followup question quality.

Uses LLM-as-judge to evaluate semantic quality of the questions.
"""
from deepagents import create_deep_agent
from tests.evals.llm_judge import llm_judge
from tests.evals.utils import TrajectoryScorer, run_agent

# 1. 定义测试用例：模糊请求 + 评判标准
FOLLOWUP_CASES = [
    {
        "id": "vague_send_report",
        "query": "Send a report to my team every week",
        "criteria": (
            "The agent should ask what the report should contain or what data to include.",
            "The agent should ask how the report should be delivered (email, Slack, etc.).",
            "The agent should NOT ask about scheduling details since the user already specified 'every week'.",
        ),
    },
    {
        "id": "vague_data_analysis",
        "query": "Analyze my data",
        "criteria": (
            "The agent should ask what data source or file the user wants analyzed.",
            "The agent should ask what kind of analysis the user needs.",
            "The agent should NOT assume a specific file format or tool without asking.",
        ),
    },
]

# 2. 参数化测试
@pytest.mark.parametrize("case", FOLLOWUP_CASES, ids=[c["id"] for c in FOLLOWUP_CASES])
def test_followup_question_quality(model, case):
    """Agent asks relevant followup questions for an underspecified request."""
    agent = create_deep_agent(model=model)
    run_agent(
        agent,
        model=model,
        query=case["query"],
        scorer=(
            TrajectoryScorer().success(
                llm_judge(*case["criteria"]),  # 每条 criteria 独立评判，全部通过才通过
            )
        ),
    )
```

**关键点**：

- 用 `llm_judge()` 代替硬编码断言
- 每条 criterion 是一句自然语言描述
- 底层调 `openevals` 的 `create_llm_as_judge`，使用另一个 LLM（默认 `claude-sonnet-4-6`）做裁判
- 所有 criteria 必须全部通过
- `case_insensitive` 参数可忽略大小写

**LLM Judge 的工作原理**：

```python
# llm_judge 内部的裁判 prompt
RESPONSES_PROMPT = """You are a strict grading assistant. You will receive a
series of agent responses and a single criterion. Decide whether the agent's
responses satisfy the criterion.

<criterion>
{criterion}
</criterion>

<agent_responses>
{outputs}
</agent_responses>"""
```

每条 criterion 独立评判，返回 `{score: true/false, comment: "..."}` 。所有 criterion 通过才算整体通过。

---

### 类型 C：文件操作评估（检查生成内容）

**场景**：验证 Agent 对文件的操作是否正确

```python
"""Eval tests for file creation and editing."""
from deepagents import create_deep_agent
from tests.evals.utils import (
    TrajectoryScorer,
    run_agent,
    file_contains,
    file_equals,
)


def test_create_config_file(model):
    """Agent creates a JSON config file with correct content."""
    agent = create_deep_agent(model=model, tools=[write_file, read_file])
    run_agent(
        agent,
        model=model,
        query="Create a JSON config file at config.json with port 8080 and debug true",
        scorer=(
            TrajectoryScorer()
            .expect(tool_call_requests=1)
            .success(
                # 精确匹配
                file_equals("config.json", '{"port": 8080, "debug": true}'),
            )
        ),
    )


def test_update_report_section(model):
    """Agent updates a specific section in a report file."""
    agent = create_deep_agent(model=model, tools=[write_file, read_file])
    run_agent(
        agent,
        model=model,
        initial_files={"report.md": "# Report\n## TODO\n- nothing yet"},
        query="Add 'Complete API integration' to the TODO section",
        scorer=(
            TrajectoryScorer().success(
                file_contains("report.md", "Complete API integration"),
            )
        ),
    )
```

**关键点**：

- `file_equals` — 文件内容完全匹配
- `file_contains` — 文件包含某子串（宽松匹配）
- `initial_files` — 可以预置文件给 Agent
- 适合代码生成、配置生成、文档编辑类任务

---

## 断言选择速查表

| 你想验证什么 | 用什么断言 |
|-------------|-----------|
| 选对了工具 | `tool_call(name="xxx", args_contains={...})` |
| 回复包含关键信息 | `final_text_contains("xxx")` |
| 回复不应包含某内容 | `final_text_excludes("xxx")` |
| 生成的文件内容对 | `file_equals()` 或 `file_contains()` |
| 追问/对话质量（主观） | `llm_judge("标准1", "标准2")` |
| 步骤/效率 | `agent_steps=N`, `tool_call_requests=N` |

---

## Eval 编写套路总结

```
1. 定义 mock tools（返回固定结果，不调真 API）
2. 构建 agent（create_deep_agent + tools/middleware）
3. 构造 query（用户会说什么）
4. 用 TrajectoryScorer 组合断言：
   - .expect(...)  → 效率指标（步数、工具调用），不 fail
   - .success(...) → 正确性指标，不通过就 fail
5. run_agent(agent, model, query, scorer)
```

---

## 在 Better Harness 中引用 Eval

在 TOML 配置中通过 `case_id` 引用 eval 测试，格式就是标准的 pytest node ID：

```toml
[[cases]]
case_id = "tests/evals/test_tool_selection.py::test_direct_request_slack_dm[{model}]"
split = "train"
stratum = "tool_use"

[[cases]]
case_id = "tests/evals/test_followup_quality.py::test_followup_question_quality[{model}-vague_send_report]"
split = "holdout"
stratum = "conversation"
```

其中 `{model}` 会被替换为 `[experiment]` 中配置的模型名。

---

## 参考文件

项目中的实际 eval 示例：

| 文件 | 说明 |
|------|------|
| `libs/evals/tests/evals/test_tool_selection.py` | 工具选择评估 |
| `libs/evals/tests/evals/test_followup_quality.py` | 追问质量评估（LLM-as-Judge） |
| `libs/evals/tests/evals/test_file_operations.py` | 文件操作评估 |
| `libs/evals/tests/evals/test_summarization.py` | 上下文溢出和摘要行为 |
| `libs/evals/tests/evals/utils.py` | 断言工具库（TrajectoryScorer 等） |
| `libs/evals/tests/evals/llm_judge.py` | LLM-as-Judge 实现 |
| `libs/evals/tests/evals/conftest.py` | 测试基础设施 |
