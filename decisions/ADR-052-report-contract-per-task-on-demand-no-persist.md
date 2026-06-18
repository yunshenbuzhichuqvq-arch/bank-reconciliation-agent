# ADR-052: 报告契约 —— per-task · 按需 · 实时生成不落库

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/api/v1/reconcile.py, src/bank_reconciliation_agent/services/report.py, decisions/ADR-014(task-ai-stats replace 语义)

## Context

报告以什么为单位、何时生成、是否落库,直接决定 API 形状、要不要新建表、页面交互。

## Options

**A. per-task · 按需 · 实时生成不落库(选定)** —— `GET /reconcile/{task_id}/report` 每次实时聚合 + 生成;不新建表、不缓存。
- Pros: 无新表、无 staleness、实现最小;数字永远最新;契合"按需生成"。
- Cons: 每次请求跑一次 LLM(成本/延迟);无历史报告留存;无缓存。

**B. per-task · 对账完成自动生成并落库** —— 每任务跑完自动生成存 DB,页面直读。
- Pros: 页面零等待。
- Cons: 每任务都烧 LLM;要处理幂等/重生成/历史版本;新增表与写入路径(回归面)。

**C. 全局/批次汇总报告** —— 跨任务聚合一份。
- Cons: 与现有 metrics dashboard 重叠;偏离 PRD §12.1 的 per-task 口径(任务编号/对账日期/处理用户)。

## Decision

选 A。`GET /api/v1/reconcile/{task_id}/report` 实时聚合 + 生成,不落库不缓存。数字本就实时来自 metrics,省掉 staleness/幂等/历史版本的复杂度。

## Consequences

正向:
- 无新表、实现面最小、数字最新。

负向 / 成本:
- 每次点击跑一次 LLM(fake 默认下不显著;真 LLM 下有成本/延迟)。
- 不留历史报告版本(列 future)。
- 高频请求无缓存 —— YAGNI,未来确有需要再加缓存层。
