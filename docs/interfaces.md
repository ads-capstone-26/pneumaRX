# 组件接口

| 组件 | Python 接口 | 输入与输出 |
|---|---|---|
| 数据准备 | `pneumarx_data.main.run(PreparationRequest)` | CSV/配置 → manifest、schema 与质量报告 |
| 任务理解 | `IntentPreparer.prepare(question, dataset_name, ...)` | 问题、目录、模型 → IntentSpec / ClarificationNeeded / Unanswerable |
| 查询执行 | `run_figure3(spec, db, planner, repair)` | 规划视图 → QueryPlan + ExecutionResult，或结构化失败 |
| 结果核查 | `Reviewer.review(ReviewInput)` | 原问题、完整 IntentSpec、计划和结果 → ReviewResult |
| 主流程 | `Pipeline.run(question, interactive=True)` | 问题 → 执行轨迹、核查结论与 presentation |

共享契约位于 `src/pneumarx/contracts/`，每个 app 的 `main.py` 提供 CLI/API。`run_figure3` 保留历史函数名；默认真实流程使用 hybrid reviewer，直接构造 Pipeline 未注入 reviewer 时为 pending。

## 表与规划契约

`IntentSpec.to_figure3_view()` 省略非规划字段，逐表保留物理路径、字段说明和限量样例，不合并结构相同的表。执行器兼容旧 `same_layout_tables`，在校验和规划前展开，仅继承字段名/类型，不借用其他表的说明或样例。路径、schema、映射及重复表名均须通过检查。

真实流程不发送样例行供任务理解；结果核查会使用必要的执行结果。BM25 默认取 5 张候选表，`retrieval_history` 记录检索过程。

## 状态与预算

- `needs_clarification` / `unanswerable`：任务理解停止，不进入 SQL 规划。
- `needs_information_adjustment`：请求上游调整，最多一次。
- `success`：SQL 执行成功；SQL 内部修复最多一次，与上游调整分开计数。
- `completed`：reviewer 的已实施检查通过。
- `validation_error` / `insufficient_evidence`：发现错误或证据不足。
- `executed_unvalidated`：使用 pending reviewer，仅完成执行。

复核不自动触发 SQL 修复。`presentation` 是交付对象：检测到错误时隐藏结果，证据不足时附疑点说明。`answer_validated` 需结合 `validation_scope` 和 `limitations` 理解；原始 `execution_result` 留作审计，不能替代 presentation。

完整结果保存在内存和本地 JSON；preview 最多 100 行。大结果流式存储与统一 SQL 超时尚未实现。
