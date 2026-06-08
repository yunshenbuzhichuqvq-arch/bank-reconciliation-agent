# ADR-007: 三级 Fallback 状态机与触发阈值

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: system-prd.md §3.3 / §9.6.1 / §11.4, t_error_ledger, t_agent_execution_log

## Context

PRD §3.3 / §9.6.1 / §11.4 定义 3 级 Fallback:L1 标准、L2 差错台账 few-shot、L3 TraceAgent 追溯,触发以 `confidence` 与 RAG 命中/分数为准。红线:RAG 无命中 → 直接转人工,不触发 Fallback(无依据不可判断)。这是 2a "让 Agent 更准" 的核心机制,需把状态机与阈值固化,避免实现层散落魔法数。

## Options

1. **严格按 PRD §9.6.1 表的 3 级状态机,阈值集中到 config** — PRD 对齐、阈值可调、每级信息增量明确,但阈值是经验值,Fake 环境测不出真实置信度分布,需 live 校准。
2. **单级:低置信直接转人工,不做 L2/L3** — 最简,但不满足 2a "Fallback 机制" 目标,丢掉 few-shot/追溯增量。
3. **把阈值/级数做成完全可配置的通用重试框架** — 灵活,但过度设计,违反 simplicity-first,2a 只需固定 3 级语义。

## Decision

采用 **Option 1**(阈值 0.85 / 0.5 待 2a 收尾 live-smoke 校准)。
- 状态机固定 3 级,语义按 §9.6.1;阈值 `CONFIDENCE_THRESHOLD=0.85`、`RAG_LOW_SCORE=0.5` 放 config 常量。
- **L1**:System Prompt + 当前异常项 + RAG 规则原文。
- **L2**:追加 2–3 条同类异常的历史人工确认案例(查 `t_error_ledger`,按 `exception_branch` 过滤、取已人工确认记录)。
- **L3**:TraceAgent 追加跨日切流水查询 + 冲正链路校验结果(2a-1 TraceAgent 为 LLM Agent;Tool 化留 V2)。
- 触发(§9.6.1):L1 `confidence<0.85` 或(RAG 命中且 `best_score<0.5`)→ L2;L2 `<0.85` → L3;L3 `<0.85` → 人工;任意级抛异常 → 直接人工,不跨级重试;RAG 无命中 → 编排层短路到人工,不进 Fallback。
- 落库:`fallback_level`(0/1/2/3)写 `ReconciliationState` 与 `t_agent_execution_log.fallback_level`;`fallback_path`(如 `L1->L2->HUMAN`)写 `t_error_ledger`;task 级累加 `fallback_l2_rows`/`fallback_l3_rows`。

## Consequences

- 正面:Agent 判断有逐级信息增量;全链路可观测(level/path 落库);阈值集中可调。
- 负向:阈值为经验值,Fake 环境无法验证真实分布,需 2a 收尾用 live-smoke 抽样校准(可能回头调阈值或 Prompt);L2 依赖差错台账历史数据,冷启动(台账空)时 L2 退化为 L1 + 空 few-shot,spec 须约定空集合行为。

## Live Calibration(2026-06-08,deepseek-v4-pro,4 异常行样本)

- 实测:BE-R002/04/05/06 各 1 行真实端到端跑通;成本 ~$0.0038/行(22274 token / 4 行 = $0.0151);单次 audit 真实耗时 15~25s。
- L2 100% 触发(4/4)、L3 50%(2/4):根因是 hash-embedding RAG 的相似度分数尺度偏低(best_score ~0.44)低于 `RAG_LOW_SCORE=0.5`,`score<0.5` 分支近乎恒真 → 只要 RAG 有命中就强制升 L2,三级 fallback 退化为"全员至少 L2"。非模型不自信,是 RAG 分数尺度与阈值不匹配。
- confidence 实测分布 [0.36, 0.5, 0.85, 0.9],`CONFIDENCE_THRESHOLD=0.85` 暂判定基本合理。
- 决定:4 行样本不足以重定阈值,阈值数值不动;根因(RAG 分数尺度)交 2a-2 增强 RAG(BM25/rerank 让分数有业务意义)根治。下调 `RAG_LOW_SCORE` 仅治标,本次未采纳。
- 关联:upload 同步路径下单次 audit 15~25s,行数一多必 HTTP 超时 → 2b 把 AI 改异步/后台的论据。
