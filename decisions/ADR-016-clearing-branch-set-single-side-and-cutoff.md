# ADR-016: 清算异常分支集合 —— 仅 BC-R001(清算单边)+ BC-R003(跨日切)

- Status: Accepted (2026-06-09)
- Deciders: 用户(拍板:Option A), Claude Code(提案)
- Related: rules/bank_clearing.yaml, services/exception_router.py, overall-architecture.md §5.2, system-prd.md §6.143 / 验收 prd:1694

## Context

架构 §5.2 定义清算 8 个分支(BC-R001..R008)。§5.2:769 与 PRD §6.143 提 MVP-2a 清算先接 `CLEARING_SINGLE_SIDE` / `CUTOFF_CROSS_DAY` / `REVERSAL_REFUND`(3 条);但 PRD 验收(prd:1694)只要求「清算单边、跨日切」(2 条)。PRD 内部口径不一,需定本 stage 实际收哪几条。

## Options

- **A. 两条(采纳)** — BC-R001 清算单边(清算端 B 有 / 核心 A 无 → `CLEARING_SINGLE_SIDE`)+ BC-R003 跨日切(交易时间在日切窗口 → `CUTOFF_CROSS_DAY`)。Pros: 对齐验收基线 prd:1694、YAGNI、集中跨日切旗舰分支。Cons: 不覆盖冲正退款,比架构 §5.2:769 列举少一条。
- **B. 三条** — 再加 BC-R005 冲正退款(`REVERSAL_REFUND`,ExtractionAgent→AuditAgent)。Pros: 对齐架构 §5.2:769 列举。Cons: 超验收基线,额外 scope;冲正语义已在银企侧验证,演示边际价值低。

## Decision

采用 **A**(用户拍板)。本 stage 清算只实现 BC-R001、BC-R003 两条规则与端到端。error_type 沿用架构既定 `CLEARING_SINGLE_SIDE` / `CUTOFF_CROSS_DAY`。BC-R002 核心单边按架构表明确留 V1;R004/R005/R006/R007/R008 留 V1+。

## Consequences

- 负向:清算侧不识别冲正退款,若样本含此类 → 落 `UNCLASSIFIED` 兜底转人工(符合「无依据转人工」红线,可接受)。
- 清算 YAML 仅 2 条规则 + 兜底(BC-R000 自动平账),确定性强、易演示、易测。
