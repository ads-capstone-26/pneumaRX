# PneumaRX

PneumaRX 是基于 Pneuma-Seeker 的临床数据查询工作流：检索相关表 → 生成 IntentSpec → 生成并只读执行 SQL → 核查结果。默认使用 BM25 top-5 检索和 hybrid reviewer，支持 MIMIC-III 及显式配置的数据集。

## 安装与运行

需要 Python 3.12+ 和 uv。在仓库根目录执行：

```bash
uv sync --frozen --all-packages --extra live
cp .env.example .env
```

在 `.env` 中设置模型与 API key。离线示例使用虚构数据，不调用模型：

```bash
uv run python main.py demo --output runs/demo.json
```

准备本地 MIMIC-III 数据：

```bash
uv run python main.py data-processing all \
  --mimic-dir /path/to/MIMIC_III \
  --db data/mimic_iii/mimic_iii.db --output runs/preparation.json
```

使用已批准的数据处理端点运行真实查询：

```bash
uv run python main.py run \
  --question 'How many distinct hospital admissions are recorded?' \
  --db data/mimic_iii/mimic_iii.db \
  --allow-private-llm --output runs/answer.json
```

`--model` 指定模型；`--table-top-k` 调整检索数量；`--table-retrieval all` 使用全表；`--reviewer sanity|llm|hybrid|pending` 选择复核方式。各组件的参数见 `python main.py <组件> --help`。

## 代码结构

- `apps/data-processing/`：数据导入、质量检查和 schema。
- `apps/intent-understanding/`：表检索、术语解析与 IntentSpec。
- `apps/query-execution/`：SQL 规划、校验、只读执行及一次修复。
- `apps/result-validation/`：证据核查和结果展示策略。
- `apps/pipeline/`：组件编排与运行资源。
- `src/pneumarx/`：共享配置、数据库/模型适配器和数据契约。
- `docs/mimic3/*.json`：运行时读取的 schema 与查询规则。

面向用户的输出在 `presentation`；`execution_result` 保留原始执行证据。复核通过仅表示已执行的检查未发现矛盾，不保证答案普遍正确。接口见 [interfaces.md](docs/interfaces.md)。

## 实验结果

修复后的 24 题回归中，RX 正确回答 18/18，正确拒答 6/6；含复核消耗 449,401 token，比原版少 67.2%。Direct 同样全部答对且更便宜，尚无证据证明 IntentSpec 提高生成准确率。设计、口径和限制见 [实验摘要](docs/evaluation.md)。

本分支只交付运行代码、必要配置及简要文档。测试、评测脚本、完整过程报告、数据和运行产物留在本地，由 `.gitignore` 排除。

## 来源与许可

基于 [Pneuma-Seeker](https://github.com/TheDataStation/pneuma-seeker) 的组件重构和优化；原版聊天后端与基线不包含在此分支。保留原项目 MIT [LICENSE](LICENSE) 与版权声明。
