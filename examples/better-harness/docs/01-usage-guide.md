# Better Harness 使用指南

## 它是什么

Better Harness 是一个 **自动优化 Agent Harness 的系统**。核心理念是用一个"外部 Agent"（outer agent）来自动改进另一个"内部 Agent"（inner agent）的 harness 配置（prompt、tools、skills、middleware 等），通过 eval 驱动的循环来验证改进是否有效。

简单说：**让 AI 自动调优 AI 的系统提示词、工具、中间件等配置，并用测试来验证效果。**

灵感来源于以下工作：

- [Improving Deep Agents with Harness Engineering](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/)
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
- [Meta-Harness](https://arxiv.org/abs/2603.28052)

## 优化流程

```
基线评估 → 外部Agent提出修改 → 在proposer workspace中应用修改 → 运行train+holdout评估
→ 如果综合通过数提升则保留修改，否则丢弃 → 重复N次
```

## 前置条件

1. **Python 3.12+**
2. **[uv](https://github.com/astral-sh/uv)**（Python 包管理工具）
3. **[deepagents](https://github.com/langchain-ai/deepagents)** 已安装，或者设置 `DEEPAGENTS_ROOT` 环境变量指向本地代码路径

## 使用步骤

### 1. 安装依赖

```bash
cd examples/better-harness
uv sync --extra dev
```

### 2. 准备配置文件

从示例配置开始：

```bash
cp examples/deepagents_example.toml my_experiment.toml
```

### 3. 编辑配置文件

配置文件采用 TOML 格式，核心配置块如下：

#### `[experiment]` — 实验基本信息

```toml
[experiment]
name = "my-deepagents-harness"   # 实验名称
runner = "pytest"                 # 评估运行器，支持 pytest / harbor
workspace_root = "${DEEPAGENTS_ROOT}"  # 目标 workspace 的绝对路径（支持环境变量）
model = "claude-sonnet-4-6"       # 内部 Agent 使用的模型
max_iterations = 3                # 最大优化迭代次数
```

#### `[better_agent]` — 外部 Agent 配置

```toml
[better_agent]
model = "claude-sonnet-4-6"  # 外部 Agent 使用的模型
max_turns = 11000            # 外部 Agent 最大轮次
```

#### `[runner.pytest]` — Pytest 运行器配置

```toml
[runner.pytest]
project_root = "${DEEPAGENTS_ROOT}/libs/evals"  # eval 测试的根目录
model_flag = "--model"           # 传模型名的 pytest 参数
summary_flag = "--evals-report-file"  # 传报告文件路径的 pytest 参数
pytest_args = ["-q"]             # 额外的 pytest 参数
```

#### `[surfaces.*]` — 可编辑表面

每个 surface 定义一个外部 Agent 可以修改的文件或属性：

```toml
# 方式一：替换 Python 模块属性
[surfaces.prompt]
kind = "module_attr"
target = "deepagents.graph:BASE_AGENT_PROMPT"  # 模块:属性名
filename = "prompt.txt"                         # proposer workspace 中的文件名
base_value = """You are a helpful agent."""     # 初始值（内联）

# 方式二：替换 workspace 中的文件
[surfaces.middleware_impl]
kind = "workspace_file"
target = "deepagents/custom_middleware.py"  # workspace 中的目标路径
filename = "middleware.py"                  # proposer workspace 中的文件名
base_file = "middleware.py"                 # 初始值（从文件读取）
```

两种加载模式：

- **`module_attr`** — 替换 Python 模块的某个属性，如 `deepagents.graph:BASE_AGENT_PROMPT`
- **`workspace_file`** — 临时替换目标 workspace 中的某个文件

初始值来源：

- **`base_value`** — 在配置文件中直接写初始值（适合自包含配置）
- **`base_file`** — 指向一个文件路径（适合复用已有源文件）

> **注意**：Middleware 通常需要两个 surface：
> 1. middleware 实现代码
> 2. 把 middleware 注册到 agent 的代码（如 `agent_setup.py`）
>
> 如果只暴露实现但不暴露注册的地方，外部 Agent 就无法真正启用它。

#### `[[cases]]` — 评估用例

```toml
[[cases]]
case_id = "tests/evals/test_tool_selection.py::test_indirect_email_report[{model}]"
split = "train"       # train / holdout / scorecard
stratum = "tool_use"  # 分类标签

[[cases]]
case_id = "tests/evals/test_followup_quality.py::test_followup_question_quality[{model}-vague_send_report]"
split = "holdout"
stratum = "conversation"
```

用例分三组：

| Split | 说明 | 外部 Agent 是否可见 |
|-------|------|-------------------|
| `train` | 训练用例，指导优化方向 | ✅ 可见 |
| `holdout` | 保留用例，防止过拟合 | ❌ 不可见 |
| `scorecard` | 可选，只在基线和最终运行 | ❌ 不可见 |

`{model}` 占位符会被替换为 `[experiment]` 中配置的模型名。

### 4. 验证配置

```bash
uv run better-harness validate my_experiment.toml
```

检查配置格式、路径是否正确。

### 5. 运行优化循环

```bash
uv run better-harness run my_experiment.toml \
  --output-dir runs/my-harness \
  --max-iterations 3
```

### 6. 查看结果

结果保存在 `--output-dir` 指定的目录中，包含：
- 每次迭代的 traces
- 决策记录（keep / discard）
- 最终报告

### 7. 运行项目自带的测试

```bash
uv run pytest
```

## 外部 Agent 和内部 Agent

| 角色 | 说明 |
|------|------|
| **外部 Agent (outer)** | Deep Agent，读取可见 eval 数据并编辑 harness surfaces |
| **内部 Agent (inner)** | 你想要改进的目标 Agent |

外部 Agent 可以看到：

- 当前可编辑的 surface 文件
- 可见的 `train` 失败信息
- 对应的源代码文件
- 之前的优化历史和 keep/discard 决策

外部 Agent **不会**直接编辑目标仓库，而是编辑一个临时的 proposer workspace。better-harness 将这些修改应用到候选 harness 上，运行 eval，根据结果决定保留或丢弃。

## 配置文件完整示例

参考 [`examples/deepagents_example.toml`](../examples/deepagents_example.toml)，它展示了如何暴露 5 个可编辑表面：

1. **prompt** — 替换 `deepagents.graph:BASE_AGENT_PROMPT`
2. **tools** — 替换 `deepagents/custom_tools.py`
3. **skills** — 替换 `deepagents/skills/reporting.md`
4. **middleware_impl** — 替换 `deepagents/custom_middleware.py`
5. **middleware_registration** — 替换 `deepagents/agent_setup.py`

## 参考链接

- [Deep Agents 仓库](https://github.com/langchain-ai/deepagents)
- [LangChain 自定义 Middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- [Deep Agents Middleware 定制](https://docs.langchain.com/oss/python/deepagents/customization#middleware)
