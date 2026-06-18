# Smart Task Assistant Demo

一个完整覆盖 better-harness 所有功能的自包含演示。

## 主题

**智能任务助手** — 帮助用户创建、搜索、分类和优先排序任务。

基线版本功能极简：只有一个基础的 `create_task` 工具和一个空泛的 prompt。外部 Agent（outer agent）需要通过优化 5 个可编辑表面（prompt、tools、skills、middleware 实现、middleware 注册）来让 10 个 eval 测试全部通过。

## 功能覆盖

| Better-Harness 功能 | 本 Demo 覆盖方式 |
|---------------------|-----------------|
| `module_attr` surface | `prompt` → `task_bot:TASK_BOT_PROMPT` |
| `workspace_file` surface | `tools`, `skills`, `middleware_impl`, `middleware_registration` |
| `base_value` 初始值 | `prompt`, `tools`, `skills`, `middleware_registration` |
| `base_file` 初始值 | `middleware_impl` → `base_files/middleware.py` |
| `train` split | 4 cases（外部 Agent 可见） |
| `holdout` split | 4 cases（外部 Agent 不可见） |
| `scorecard` split | 2 cases（仅基线和最终运行） |
| pytest runner | 主运行器 |
| 基线全失败 → 迭代优化 | 所有 surface 初始值故意写弱 |

## 目录结构

```
demo/
├── README.md                    ← 你在这里
├── experiment.toml              ← better-harness 配置（入口）
├── workspace/                   ← 目标 Agent workspace
│   ├── task_bot.py             ← TASK_BOT_PROMPT（module_attr 目标）
│   ├── custom_tools.py         ← 工具定义（workspace_file）
│   ├── skills.md               ← 技能指南（workspace_file）
│   ├── middleware.py            ← 中间件实现（workspace_file）
│   └── bot_builder.py          ← Agent 构建（workspace_file）
├── evals/                       ← Evals 项目
│   ├── pyproject.toml          ← uv 项目配置
│   ├── conftest.py             ← pytest 配置
│   └── tests/
│       ├── test_tool_selection.py    ← 工具选择（3 cases）
│       ├── test_prompt_behavior.py   ← Prompt 行为（2 cases）
│       ├── test_skills_middleware.py ← Skills + 中间件（3 cases）
│       └── test_safety_format.py     ← 安全 + 格式（2 cases）
└── base_files/
    └── middleware.py            ← middleware_impl 的 base_file 来源
```

## 快速开始

### 前置条件

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- better-harness 已安装（在 `examples/better-harness/` 下运行 `uv sync --extra dev`）

### 1. 验证配置

```bash
cd examples/better-harness
uv run better-harness validate demo/experiment.toml
```

### 2. 直接运行 eval（验证基线全失败）

```bash
cd demo/evals
uv sync --group test
PYTHONPATH=../workspace uv run pytest tests/ -v
```

预期结果：**10 failed** — 所有 eval 在基线状态下都失败，因为 surface 初始值是故意写弱的。

### 3. 运行完整优化循环

```bash
cd examples/better-harness
uv run better-harness run demo/experiment.toml \
  --output-dir runs/task-assistant-demo \
  --max-iterations 4
```

### 4. 查看结果

```bash
uv run better-harness inspect runs/task-assistant-demo
```

## Eval 用例一览

| # | 测试 | Split | Stratum | 检查内容 |
|---|------|-------|---------|---------|
| 1 | `test_direct_create_task` | train | tools | `create_task` 接受 `priority` 参数 |
| 2 | `test_search_tasks_available` | train | tools_advanced | 包含 `search_tasks` 工具 |
| 3 | `test_followup_policy` | train | prompt | prompt 包含 followup/clarification 策略 |
| 4 | `test_escalation_rules` | train | guardrails | skills 包含升级规则 |
| 5 | `test_categorize_tool_exists` | holdout | tools | 包含 `categorize_task` 工具 |
| 6 | `test_priority_levels` | holdout | prompt | prompt 定义 high/medium/low 优先级 |
| 7 | `test_duplicate_detection` | holdout | tools_advanced | middleware 处理重复任务 |
| 8 | `test_safety_refusal` | holdout | guardrails | prompt 包含安全拒绝指令 |
| 9 | `test_combined_workflow` | scorecard | combined | prompt + tools + skills 三者协同 |
| 10 | `test_output_format` | scorecard | format | prompt 指定输出格式 |

## Surfaces 说明

### prompt（module_attr + base_value）

- **目标**: `task_bot:TASK_BOT_PROMPT`
- **基线**: `"You are a task management assistant. Help users with their tasks."`
- **需要改进**: 添加 followup 策略、优先级定义、安全规则、格式要求

### tools（workspace_file + base_value）

- **目标**: `custom_tools.py`
- **基线**: 只有 `create_task(title, description)`
- **需要改进**: 添加 `priority` 参数、`search_tasks`、`categorize_task`

### skills（workspace_file + base_value）

- **目标**: `skills.md`
- **基线**: `"# Task Assistant Skills\n\nBe helpful."`
- **需要改进**: 添加升级规则、任务管理最佳实践

### middleware_impl（workspace_file + base_file）

- **目标**: `middleware.py`
- **初始值来自**: `base_files/middleware.py`（演示 `base_file` 值来源）
- **基线**: `MIDDLEWARE = []`
- **需要改进**: 添加重复检测逻辑

### middleware_registration（workspace_file + base_value）

- **目标**: `bot_builder.py`
- **基线**: 只用了 `create_task`，没有 middleware
- **需要改进**: 接入 middleware、添加更多 tools

> **为什么 middleware 需要两个 surface？**
> 如果只暴露实现代码但不暴露注册/接入的文件，外部 Agent 就无法真正启用 middleware。
