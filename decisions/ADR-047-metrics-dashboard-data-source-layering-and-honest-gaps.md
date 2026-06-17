# ADR-047: 指标仪表板数据源分层——线上聚合 + 离线评测快照 + 诚实缺口标注

- Status: Accepted (2026-06-16)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/services/metrics.py, src/bank_reconciliation_agent/api/v1/metrics.py, scripts/eval_rag.py, decisions/ADR-014(task-ai-stats replace 语义)

## Context

PRD §4.8 量化指标仪表板列 8 类指标。数据源盘点(已核对 schema.sql + scripts/):

| 档 | 指标 | 来源 |
|---|---|---|
| ① 线上可聚合 | 自动平账率、人工复核触发率、异常类型分布、Fallback 层级、Token 消耗 + 成本、置信度分布 | `t_reconciliation_task` / `t_*_ledger` / `t_human_review` 直接有字段 |
| ② 离线评测产物(静态) | RAG Recall@5/MRR/NDCG、Schema 符合率 | `scripts/eval_rag.py` / Schema 符合性测试输出 |
| ③ 无真实数据源 | 单笔时延 P50/P95/P99、Agent 审计准确率 | 无 latency 落库(仅疑似硬编码 fake 的 `bench_agent_latency`);准确率需 ground truth |

项目反复出现"有 UI/能力但数据是空壳/fake/静默降级"的坑(ADR-043 看板空壳、V1-1 SSE 回放降级、2b 静默退化)。指标板若摆 fake P99 会重蹈覆辙。

## Options

- **A. 线上聚合 + 离线快照,诚实标注缺口(采纳)** — 新增 `GET /metrics/dashboard` 聚合①的线上真实统计;②离线指标读最近一次评测产物快照并标注评测时间;③无数据源指标在 UI 显式标注"暂无线上埋点 / 数据缺口",不计算、不 fake。
  - Pros: 覆盖 PRD §4.8 大部分;数据真实可追溯;诚实边界是工程亮点。
  - Cons: 仪表板有显式"空位",不如全绿好看;离线快照有时效性(非实时)。
- **B. 只做线上聚合指标** — 仅展示①,②③一律不进仪表板。Pros: 最干净无争议。Cons: 丢失评测产物展示价值、PRD §4.8 覆盖度低。
- **C. 全指标 + 补 latency 埋点** — 为 P50/P95/P99 加 `t_agent_execution_log.duration_ms` 字段 + 执行路径埋点。Pros: 最全。Cons: 改 schema + 执行路径(回归面)、收官 stage 偏重;Agent 准确率仍无 ground truth,解决不了。

### 子决策:离线快照对接方式

评测脚本(`eval_rag` / schema)输出一份结构化 JSON(在现有 markdown 报告外旁路增加),`/metrics` 后端读该 JSON。避免解析 markdown(脆弱)。本 stage 加 JSON 输出旁路(小改,不动评测核心逻辑)。

## Decision

采用 A:线上真实聚合 + 离线评测 JSON 快照 + 无数据源指标诚实标注"暂无"。latency/准确率不在本 stage 补埋点(留 V2,对应 PRD §3.6 离线分析)。

## Consequences

- 正面:数据真实、覆盖度合理、诚实标注是可复用的工程 narrative。
- 负面:仪表板有显式"暂无"项;离线快照非实时(须标注 `@ 评测时间`);评测脚本需加 JSON 输出旁路(轻量改动)。
