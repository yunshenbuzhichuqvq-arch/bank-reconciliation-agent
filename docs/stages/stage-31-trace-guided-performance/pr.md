# Stage 31: Trace 驱动的测量门禁与条件式关键路径优化

## Outcome: `no_go`

**理论 warm P95 改善仅 0.353%**，远低于 20% 入口阈值。RAG 检索（~70ms）在端到端延迟（~20s）中占比微不足道，LLM 调用（ExtractionAgent + AuditAgent）主导了总延迟。工作流保持串行，与 ADR-032 一致。

---

## 做了什么

### Phase A — Benchmark & Baseline

1. **benchmark contract**（`scripts/bench_agent_latency.py`）：新增 `--scenario stage31-critical-path` 和 `--scenario stage31-comparison`，支持 cold/warmup/measured 分离、Trace eligibility 校验、predicted parallel 公式、fail-closed gate decision（`candidate_allowed | no_go | environment_gap`）

2. **real baseline**（`reports/performance_cost_benchmark_stage31_baseline.json`）：使用真实 DeepSeek（deepseek-v4-flash）+ 真实 bge_m3，固定 `BANK_ENTERPRISE / BE-R004 / NARRATIVE_NAME_MISMATCH` 输入，1 cold + 1 warmup + 20 measured runs

3. **contract 修复**（TASK-31.6–31.11）：
   - Runtime identity 从实际 provider/retriever 对象读取，非 CLI 回显
   - Canonical input hash 覆盖所有执行路径字段
   - environment gap 与 measured no_go 严格区分
   - Trace eligibility 校验 terminal span、sequence、parent、identity
   - Full-flow accounting（Extraction + Audit token 汇总）
   - Independence gate 标注 honest 来源（static_code_analysis / static_analysis_unverified）
   - CPU environment identity + schema validation
   - Comparison fail-closed contract（环境、调用数、成本、错误率全部逐项门禁）

---

## Benchmark 关键结果

| Metric | Value |
|--------|-------|
| Git revision | `7c4b0a7d` |
| input_sha256 | `1f4c2ccf...` |
| Provider | deepseek → deepseek |
| Embedding | bge_m3 → bge_m3 |
| Trace 完整率 | 20/20 (100%) |
| E2E P95 | 20,401ms |
| Predicted Parallel P95 | 20,329ms |
| **理论改善** | **0.353%** |
| Agent calls | 40 |
| Token 总量 | 74,253 |
| 估算成本 | $0.039 |
| 错误率 | 0% |

---

## Gate Decision

**`no_go`** — `theory_pct_0.353_lt_20.0`

20 次 measured run 全部 complete、trusted=true，但并行化收益几乎为零。RAG 节省的时间仅 ~70ms，而两个 LLM 调用（Extraction + Audit）合计约 20s。

---

## Not Implemented（Conditional Tasks Skipped）

- **TASK-31.3**：并发候选实现（`no_go` → 不允许）
- **TASK-31.4**：after/comparison 与保留/回滚（`no_go` → 无候选）

**无 runtime 候选被保留。** 工作流保持串行。

---

## 测试覆盖

| Suite | Result |
|-------|--------|
| Stage 31 focused (205 tests) | passed |
| Full pytest (1198 + 1 skipped) | passed |
| Ruff check | all clear |
| Ruff format (Stage 31 files) | 2 files formatted |
| Ruff format (repo) | 92 inherited baseline, 0 new regressions |

---

## 变更文件

```
decisions/ADR-31.1-measurement-gated-critical-path-concurrency.md  (+150)
docs/stages/stage-31-trace-guided-performance/spec.md               (+373)
docs/stages/stage-31-trace-guided-performance/tasks.md              (+490)
docs/stages/stage-31-trace-guided-performance/verification.md      (+132)
reports/performance_cost_benchmark_stage31_baseline.json            (+439)
reports/performance_cost_benchmark_stage31_baseline.md              (+492)
scripts/bench_agent_latency.py                                     (+1121)
tests/test_bench_agent_latency.py                                  (+1724)
─────────────────────────────────────────────────────────────────────────
8 files, +4590 / -331
```

---

## PR Checklist

- [x] 全量 pytest 通过（1198 passed, 1 skipped）
- [x] Ruff check 全量通过
- [x] Stage 31 changed-path Ruff format 通过（0 new regressions）
- [x] Git diff --check 通过
- [x] 无密钥、.env、cache、模型文件进入提交
- [x] 所有文件在 Stage 31 允许范围内
- [x] Verification.md 记录 branch、HEAD、日期、最终 outcome
- [x] Conditional tasks (TASK-31.3/31.4) 明确标记 skipped
- [x] 无 runtime candidate 被保留
