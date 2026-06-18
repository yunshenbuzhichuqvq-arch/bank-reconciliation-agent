# ADR-053: ReportAgent 失败降级 —— 模板兜底 + schema 校验 + 单次尝试不重试

- Status: Accepted (2026-06-18)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/agents/report_agent.py, src/bank_reconciliation_agent/schemas/report.py, decisions/ADR-005(LLM provider 抽象 + fake 默认 + 测试契约), decisions/ADR-007(三级 fallback), decisions/ADR-022(硬约束 C1–C6 输出校验), decisions/ADR-008(structlog + prompt 版本)

## Context

LLM 超时/不可用/输出 schema 不符时,报告端点不能挂。项目已有 fake-default(ADR-005)、三级 fallback(ADR-007)、输出校验管线(ADR-022)、prompt 版本(ADR-008)等成熟模式,ReportAgent 应复用而非另造。

## Options

**A. 模板降级(选定)** —— ReportAgent 镜像 AuditAgent:provider 注入、fake 默认确定性、Pydantic schema 校验;校验失败 / LLM 不可用即降级为确定性模板叙述,`llm_used=false`(对齐 AuditAgent:单次尝试、不重试)。数字区块照常(代码渲染,不依赖 LLM)。
- Pros: 报告高可用、永远 200;与现有 agent 行为一致;可测(fake 确定性 + 降级路径)。
- Cons: 降级时叙述质量下降(以 `llm_used=false` 显式标注);多一套 report schema 维护。

**B. LLM 失败直接 5xx** —— Cons: 报告链路脆,违背项目"无命中/失败转兜底"基因。

**C. 无限重试** —— Cons: 阻塞请求、放大故障,无界重试是反模式。

## Decision

选 A。复用 ADR-005/007/022/008 既有管线:fake 默认 + schema 校验 + 失败即模板降级(对齐 AuditAgent:单次尝试、不重试) + structlog(带 `prompt_version`)。报告永远可出,降级时诚实标注。

> 初稿曾写"有界重试",stage review 校正:叙述路径与 AuditAgent 一致为单次尝试、失败即降级,不重试;未来若确需报告路径重试再单列 ADR。

## Consequences

正向:
- 报告链路高可用且可测;与 AuditAgent 行为/测试范式统一。

负向 / 成本:
- 降级叙述质量下降(显式 `llm_used=false`,诚实)。
- 新增一套 report 叙述 schema 与降级模板需维护。
